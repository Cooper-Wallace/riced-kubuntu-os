#!/usr/bin/env python3
"""
Standalone PyQt6 desktop client for the self-hosted Waydroid DevTools endpoint.
Replaces Chromium tabs with a dedicated inspector window and a separate
Saved Ephemeral DM Media window.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import urllib.request

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


DARK_QSS = """
QMainWindow, QWidget {
  background-color: #1e1e2e;
  color: #cdd6f4;
  font-family: "JetBrains Mono", "Inter", monospace;
  font-size: 12px;
}
QLineEdit, QPlainTextEdit, QTableWidget, QListWidget {
  background-color: #181825;
  border: 1px solid #313244;
  border-radius: 4px;
  color: #cdd6f4;
  gridline-color: #262738;
}
QHeaderView::section {
  background-color: #181825;
  color: #a6adc8;
  border: none;
  border-bottom: 1px solid #313244;
  padding: 5px 6px;
  font-weight: bold;
}
QPushButton {
  background-color: #24273a;
  border: 1px solid #313244;
  border-radius: 4px;
  padding: 5px 10px;
  color: #cdd6f4;
}
QPushButton:hover { border-color: #89b4fa; }
QPushButton:checked {
  background-color: #89b4fa;
  color: #11111b;
  font-weight: bold;
}
QTabWidget::pane { border: 1px solid #313244; background-color: #181825; }
QTabBar::tab {
  background: #24273a;
  color: #a6adc8;
  padding: 6px 12px;
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}
QTabBar::tab:selected { color: #89b4fa; border-bottom: 2px solid #89b4fa; font-weight: bold; }
"""


class DevToolsApiClient:
    """Thin HTTP JSON/file client targeting the local DevTools server without proxies."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get_json(self, path: str, timeout: float = 3.0) -> Dict[str, Any]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        with self._opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_json(self, path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Dict[str, Any]:
        body = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_bytes(self, path: str, timeout: float = 5.0) -> bytes:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        with self._opener.open(req, timeout=timeout) as resp:
            return resp.read()


def fmt_size(num: Any) -> str:
    n = int(num or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def open_local_target(path_or_url: str, is_video: bool = False) -> None:
    """Launch saved local media in KDE/Linux native viewer without browser overhead."""
    players = ("haruna", "vlc", "ffplay") if is_video else ("gwenview", "haruna", "vlc")
    for player in players:
        bin_path = shutil.which(player)
        if bin_path:
            args = [bin_path, "-autoexit", path_or_url] if player == "ffplay" else [bin_path, path_or_url]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, path_or_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


class SavedEphemeralWindow(QMainWindow):
    """Separate dedicated window displaying automatically/manually saved ephemeral DM media."""

    def __init__(self, api: DevToolsApiClient, on_toggle_auto: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.on_toggle_auto = on_toggle_auto
        self._items_by_seq: Dict[int, Dict[str, Any]] = {}
        self._last_key = ""

        self.setWindowTitle("Saved Ephemeral DM Media — Waydroid DevTools")
        self.resize(860, 620)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.title_lbl = QLabel("Saved Ephemeral DM Media")
        self.title_lbl.setStyleSheet("font-weight: bold; color: #cba6f7; font-size: 13px;")
        self.count_lbl = QLabel("Saved: 0")
        self.count_lbl.setStyleSheet("color: #a6e3a1;")
        self.chk_auto = QCheckBox("Auto-Save Ephemeral")
        self.chk_auto.toggled.connect(self._handle_toggle)
        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.clicked.connect(self._open_media_folder)
        top.addWidget(self.title_lbl)
        top.addWidget(self.count_lbl)
        top.addStretch(1)
        top.addWidget(self.chk_auto)
        top.addWidget(self.btn_open_folder)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.item_list = QListWidget()
        self.item_list.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self.item_list)

        right = QWidget()
        rlayout = QVBoxLayout(right)
        self.preview_lbl = QLabel("Select a saved ephemeral item to inspect")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setMinimumSize(320, 320)
        self.preview_lbl.setStyleSheet("background-color: #11111b; border: 1px solid #313244; border-radius: 6px;")
        self.meta_lbl = QLabel("")
        self.meta_lbl.setWordWrap(True)
        self.meta_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_play = QPushButton("Open / Play Media")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._open_selected_media)
        rlayout.addWidget(self.preview_lbl, 1)
        rlayout.addWidget(self.meta_lbl)
        rlayout.addWidget(self.btn_play)
        splitter.addWidget(right)
        splitter.setSizes([380, 460])
        layout.addWidget(splitter, 1)

    def _handle_toggle(self, checked: bool) -> None:
        if self.chk_auto.signalsBlocked():
            return
        self.on_toggle_auto(bool(checked))

    def sync_auto_state(self, enabled: bool) -> None:
        self.chk_auto.blockSignals(True)
        self.chk_auto.setChecked(bool(enabled))
        self.chk_auto.blockSignals(False)

    def update_from_payload(self, items: List[Dict[str, Any]]) -> None:
        self.count_lbl.setText(f"Saved: {len(items)}")
        key = "|".join(f"{r.get('seq')}:{r.get('saved_rel')}:{r.get('resp_size')}" for r in items)
        if key == self._last_key:
            return
        self._last_key = key

        cur = self.item_list.currentItem()
        cur_seq = cur.data(Qt.ItemDataRole.UserRole) if cur else None
        self.item_list.clear()
        self._items_by_seq.clear()
        for r in reversed(items):
            seq = int(r.get("seq", 0))
            self._items_by_seq[seq] = r
            sender = (r.get("request_headers") or {}).get("Sender") or r.get("host") or "DM"
            ts = r.get("timestamp") or ""
            label = f"#{seq} [{sender}] {ts} — {Path(str(r.get('saved_rel') or '')).name} ({fmt_size(r.get('resp_size'))})"
            entry = QListWidgetItem(label)
            entry.setData(Qt.ItemDataRole.UserRole, seq)
            self.item_list.addItem(entry)
            if seq == cur_seq:
                self.item_list.setCurrentItem(entry)

    def _on_select(self, current: Optional[QListWidgetItem], _prev: Optional[QListWidgetItem]) -> None:
        if current is None:
            self.btn_play.setEnabled(False)
            self.meta_lbl.setText("")
            return
        seq = int(current.data(Qt.ItemDataRole.UserRole) or 0)
        row = self._items_by_seq.get(seq)
        if not row:
            return
        saved_file = str(row.get("saved_file") or "")
        saved_rel = str(row.get("saved_rel") or "")
        sender = (row.get("request_headers") or {}).get("Sender") or row.get("host") or "DM"
        self.meta_lbl.setText(
            f"Sender: {sender}\nType: {row.get('content_type', '')} ({fmt_size(row.get('resp_size'))})\nPath: {saved_file or saved_rel}"
        )
        self.btn_play.setEnabled(bool(saved_file or saved_rel))

        preview_rel = str(row.get("thumb_rel") or "")
        if str(row.get("content_type") or "").startswith("image/") and saved_rel:
            preview_rel = saved_rel
        if preview_rel:
            try:
                raw = self.api.get_bytes(f"/files/{quote(preview_rel)}")
                pix = QPixmap()
                if pix.loadFromData(raw):
                    scaled = pix.scaled(360, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.preview_lbl.setPixmap(scaled)
                    return
            except Exception:
                pass
        self.preview_lbl.setPixmap(QPixmap())
        self.preview_lbl.setText("Video / Audio ready — click 'Open / Play Media'")

    def _open_selected_media(self) -> None:
        cur = self.item_list.currentItem()
        if cur is None:
            return
        row = self._items_by_seq.get(int(cur.data(Qt.ItemDataRole.UserRole) or 0))
        if not row:
            return
        saved_file = str(row.get("saved_file") or "")
        saved_rel = str(row.get("saved_rel") or "")
        target = saved_file if (saved_file and Path(saved_file).exists()) else f"{self.api.base_url}/files/{quote(saved_rel)}"
        is_video = str(row.get("content_type") or "").startswith(("video/", "audio/")) or saved_rel.endswith(".mp4")
        open_local_target(target, is_video=is_video)

    def _open_media_folder(self) -> None:
        for row in self._items_by_seq.values():
            saved_file = str(row.get("saved_file") or "")
            if saved_file and Path(saved_file).exists():
                open_local_target(str(Path(saved_file).parent), is_video=False)
                return


class DevToolsMainWindow(QMainWindow):
    """Primary desktop Network Inspector window paired with a separate Saved Ephemeral window."""

    FILTER_TYPES = ("All", "DM", "Fetch/XHR", "Img", "Media", "WS", "TLS", "Doc", "Other")

    def __init__(self, api: DevToolsApiClient, open_saved: bool = False) -> None:
        super().__init__()
        self.api = api
        self._all_requests: List[Dict[str, Any]] = []
        self._websockets: List[Dict[str, Any]] = []
        self._cleared_before_seq = 0
        self._type_filter = "All"
        self._selected_seq: Optional[int] = None
        self._last_table_key = ""
        self._message_cache: Dict[str, Any] = {}

        self.saved_window = SavedEphemeralWindow(api=self.api, on_toggle_auto=self._set_auto_save_ephemeral)

        self.setWindowTitle("Waydroid DevTools — Local Inspector")
        self.resize(1260, 780)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Toolbar row 1
        bar1 = QHBoxLayout()
        brand = QLabel("Waydroid DevTools")
        brand.setStyleSheet("font-weight: bold; color: #cba6f7; font-size: 13px;")
        self.cap_lbl = QLabel("Captures: connecting...")
        self.stats_lbl = QLabel("Requests: 0 | Saved: 0")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter URL, domain, status...")
        self.filter_edit.textChanged.connect(lambda _t: self._render_table(force=True))
        self.chk_auto_eph = QCheckBox("Auto-Save Ephemeral DM")
        self.chk_auto_eph.toggled.connect(self._on_auto_eph_toggled)
        self.btn_saved_win = QPushButton("Saved Ephemeral (0)")
        self.btn_saved_win.clicked.connect(self._show_saved_window)
        self.btn_clear = QPushButton("Clear View")
        self.btn_clear.clicked.connect(self._clear_view)
        self.chk_follow = QCheckBox("Follow")
        self.chk_follow.setChecked(True)

        bar1.addWidget(brand)
        bar1.addWidget(self.cap_lbl, 1)
        bar1.addWidget(self.stats_lbl)
        bar1.addWidget(self.filter_edit)
        bar1.addWidget(self.chk_auto_eph)
        bar1.addWidget(self.btn_saved_win)
        bar1.addWidget(self.btn_clear)
        bar1.addWidget(self.chk_follow)
        root.addLayout(bar1)

        # Toolbar row 2: type pills
        bar2 = QHBoxLayout()
        self._pill_group = QButtonGroup(self)
        self._pill_group.setExclusive(True)
        for idx, tname in enumerate(self.FILTER_TYPES):
            btn = QPushButton(tname)
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda _chk, name=tname: self._set_type_filter(name))
            self._pill_group.addButton(btn)
            bar2.addWidget(btn)
        bar2.addStretch(1)
        root.addLayout(bar2)

        # Main splitter: table + inspector drawer
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Method", "Status", "Type", "Domain", "Path / URL", "Size", "Local Disk Copy"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 190)
        self.table.setColumnWidth(6, 200)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        self.tabs = QTabWidget()
        self.txt_headers = QPlainTextEdit()
        self.txt_headers.setReadOnly(True)
        self.txt_payload = QPlainTextEdit()
        self.txt_payload.setReadOnly(True)
        self.txt_response = QPlainTextEdit()
        self.txt_response.setReadOnly(True)
        self.txt_ws = QPlainTextEdit()
        self.txt_ws.setReadOnly(True)

        preview_pane = QWidget()
        pv_layout = QVBoxLayout(preview_pane)
        self.pv_status = QLabel("Select a media/image row to inspect or save")
        self.pv_status.setWordWrap(True)
        self.pv_image = QLabel("")
        self.pv_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv_image.setStyleSheet("background-color: #11111b; border: 1px solid #313244; border-radius: 6px;")
        self.btn_open_media = QPushButton("Open / Play Media Externally")
        self.btn_open_media.setEnabled(False)
        self.btn_open_media.clicked.connect(self._open_selected_external)
        pv_layout.addWidget(self.pv_status)
        pv_layout.addWidget(self.pv_image, 1)
        pv_layout.addWidget(self.btn_open_media)

        self.tabs.addTab(self.txt_headers, "Headers")
        self.tabs.addTab(self.txt_payload, "Payload")
        self.tabs.addTab(self.txt_response, "Response / Message")
        self.tabs.addTab(preview_pane, "Preview / Media")
        self.tabs.addTab(self.txt_ws, "WebSockets")
        splitter.addWidget(self.tabs)
        splitter.setSizes([760, 480])
        root.addWidget(splitter, 1)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(800)
        self._poll_timer.timeout.connect(self.poll)
        self._poll_timer.start()
        self.poll()

        if open_saved:
            self._show_saved_window()

    @staticmethod
    def _is_dm(r: Dict[str, Any]) -> bool:
        host = str(r.get("host") or "")
        path = str(r.get("path") or "")
        return bool(r.get("is_dm") or r.get("method") == "DM" or "[DM" in host or "/direct" in path)

    @staticmethod
    def _is_saved_ephemeral(r: Dict[str, Any]) -> bool:
        saved_rel = str(r.get("saved_rel") or "")
        if not saved_rel.startswith("media/"):
            return False
        if "is_ephemeral" in r:
            return bool(r.get("is_ephemeral"))
        return bool(r.get("is_dm")) and "/raven_media" in str(r.get("path") or "")

    def _matches_filter(self, r: Dict[str, Any]) -> bool:
        if int(r.get("seq", 0)) <= self._cleared_before_seq:
            return False
        if self._type_filter != "All":
            rtype = str(r.get("resource_type") or "")
            if self._type_filter == "DM":
                if not self._is_dm(r):
                    return False
            elif self._type_filter == "Other":
                if rtype in ("Fetch/XHR", "Img", "Media", "WS", "TLS", "Doc"):
                    return False
            elif rtype != self._type_filter:
                return False
        q = self.filter_edit.text().strip().lower()
        if q:
            hay = " ".join(
                str(r.get(k) or "")
                for k in ("method", "status_code", "host", "path", "content_type", "preview", "saved_rel")
            ).lower()
            if q not in hay:
                return False
        return True

    def _set_type_filter(self, name: str) -> None:
        self._type_filter = name
        self._render_table(force=True)

    def _clear_view(self) -> None:
        self._cleared_before_seq = max((int(r.get("seq", 0)) for r in self._all_requests), default=0)
        self._selected_seq = None
        self._render_table(force=True)

    def _on_auto_eph_toggled(self, checked: bool) -> None:
        if self.chk_auto_eph.signalsBlocked():
            return
        self._set_auto_save_ephemeral(bool(checked))

    def _set_auto_save_ephemeral(self, enabled: bool) -> None:
        try:
            self.api.post_json("/api/config", {"auto_save_ephemeral": bool(enabled)})
            self.poll()
        except Exception:
            pass

    def _show_saved_window(self) -> None:
        self.saved_window.show()
        self.saved_window.raise_()
        self.saved_window.activateWindow()

    def poll(self) -> None:
        try:
            data = self.api.get_json("/api/requests")
        except Exception:
            return
        self.cap_lbl.setText(f"Captures: {data.get('capture_dir', 'n/a')}")
        self._all_requests = data.get("requests") or []
        self._websockets = data.get("websockets") or []
        cfg = data.get("config") or {}
        auto_eph = bool(cfg.get("auto_save_ephemeral", False))
        self.chk_auto_eph.blockSignals(True)
        self.chk_auto_eph.setChecked(auto_eph)
        self.chk_auto_eph.blockSignals(False)
        self.saved_window.sync_auto_state(auto_eph)

        saved_eph_items = [r for r in self._all_requests if self._is_saved_ephemeral(r)]
        self.btn_saved_win.setText(f"Saved Ephemeral ({len(saved_eph_items)})")
        self.saved_window.update_from_payload(saved_eph_items)
        self._render_table(force=False)
        if self._selected_seq is not None:
            self._render_drawer()

    def _render_table(self, force: bool = False) -> None:
        filtered = [r for r in self._all_requests if self._matches_filter(r)]
        saved_count = sum(1 for r in filtered if str(r.get("saved_rel") or "").startswith("media/"))
        self.stats_lbl.setText(f"Requests: {len(filtered)} | Saved: {saved_count}")
        key = "|".join(f"{r.get('seq')}:{r.get('saved_rel')}:{r.get('resp_size')}" for r in filtered)
        if not force and key == self._last_table_key:
            return
        self._last_table_key = key

        self.table.blockSignals(True)
        self.table.setRowCount(len(filtered))
        selected_row_idx = -1
        for row_idx, r in enumerate(filtered):
            seq = int(r.get("seq", 0))
            if seq == self._selected_seq:
                selected_row_idx = row_idx
            saved_rel = str(r.get("saved_rel") or "")
            target_rel = str(r.get("target_media_rel") or "")
            disk_col = saved_rel if saved_rel else ("Thumbnail only (click row)" if target_rel else "-")
            vals = (
                str(r.get("method") or ""),
                str(r.get("status_code") or ""),
                str(r.get("resource_type") or ""),
                str(r.get("host") or ""),
                str(r.get("path") or ""),
                fmt_size(r.get("resp_size")),
                disk_col,
            )
            for col_idx, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, seq)
                if col_idx == 1:
                    code = int(r.get("status_code") or 0)
                    if 200 <= code < 300:
                        item.setForeground(QColor("#a6e3a1"))
                    elif code >= 400:
                        item.setForeground(QColor("#f38ba8"))
                self.table.setItem(row_idx, col_idx, item)
        if selected_row_idx >= 0:
            self.table.selectRow(selected_row_idx)
        self.table.blockSignals(False)
        if self.chk_follow.isChecked() and filtered:
            self.table.scrollToBottom()

    def _on_row_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        seq = int(items[0].data(Qt.ItemDataRole.UserRole) or 0)
        self._selected_seq = seq
        row = next((r for r in self._all_requests if int(r.get("seq", -1)) == seq), None)
        if row and row.get("target_media_rel") and not str(row.get("saved_rel") or "").startswith("media/"):
            try:
                res = self.api.post_json(f"/api/save/{seq}", {})
                if res.get("request"):
                    for i, r in enumerate(self._all_requests):
                        if int(r.get("seq", -1)) == seq:
                            self._all_requests[i] = res["request"]
                            break
                    self._render_table(force=True)
            except Exception:
                pass
        self._render_drawer()

    def _render_drawer(self) -> None:
        row = next((r for r in self._all_requests if int(r.get("seq", -1)) == self._selected_seq), None)
        if not row:
            return
        headers_txt = (
            f"URL: {row.get('url', '')}\n"
            f"Method: {row.get('method', '')} | Status: {row.get('status_code', '')} | Type: {row.get('resource_type', '')}\n"
            f"Content-Type: {row.get('content_type', '')}\n"
            f"Saved File: {row.get('saved_file') or '(none)'}\n\n"
            f"Response Headers:\n{json.dumps(row.get('response_headers') or {}, indent=2)}\n\n"
            f"Request Headers:\n{json.dumps(row.get('request_headers') or {}, indent=2)}"
        )
        self.txt_headers.setPlainText(headers_txt)

        msg_rel = str(row.get("msg_rel") or "")
        if not msg_rel and str(row.get("saved_rel") or "").startswith("messages/"):
            msg_rel = str(row.get("saved_rel") or "")
        msg_data = None
        if msg_rel.startswith("messages/"):
            if msg_rel in self._message_cache:
                msg_data = self._message_cache[msg_rel]
            else:
                try:
                    name = msg_rel[len("messages/") :]
                    msg_data = self.api.get_json(f"/api/message/{quote(name)}")
                    self._message_cache[msg_rel] = msg_data
                except Exception:
                    msg_data = None
        self.txt_payload.setPlainText(
            json.dumps(msg_data.get("request_body"), indent=2) if msg_data and msg_data.get("request_body") else "(empty)"
        )
        self.txt_response.setPlainText(
            json.dumps(msg_data.get("response_body"), indent=2)
            if msg_data and msg_data.get("response_body")
            else str(row.get("preview") or "(binary)")
        )
        self.txt_ws.setPlainText(
            "\n".join(
                f"{m.get('timestamp')} [{m.get('direction')}] {m.get('url')}\n{m.get('payload')}\n"
                for m in reversed(self._websockets[-80:])
            )
            or "(No WebSocket messages)"
        )

        saved_rel = str(row.get("saved_rel") or "")
        saved_file = str(row.get("saved_file") or "")
        thumb_rel = str(row.get("thumb_rel") or "")
        self.pv_status.setText(f"Saved copy: {saved_file or saved_rel or '(thumbnail / not saved)'}")
        self.btn_open_media.setEnabled(saved_rel.startswith("media/"))
        img_rel = saved_rel if (saved_rel.startswith("media/") and str(row.get("content_type") or "").startswith("image/")) else thumb_rel
        if img_rel:
            try:
                pix = QPixmap()
                if pix.loadFromData(self.api.get_bytes(f"/files/{quote(img_rel)}")):
                    self.pv_image.setPixmap(
                        pix.scaled(420, 420, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                    return
            except Exception:
                pass
        self.pv_image.setPixmap(QPixmap())
        self.pv_image.setText("No inline image preview (click 'Open / Play Media Externally' for video/audio)")

    def _open_selected_external(self) -> None:
        row = next((r for r in self._all_requests if int(r.get("seq", -1)) == self._selected_seq), None)
        if not row:
            return
        saved_file = str(row.get("saved_file") or "")
        saved_rel = str(row.get("saved_rel") or "")
        target = saved_file if (saved_file and Path(saved_file).exists()) else f"{self.api.base_url}/files/{quote(saved_rel)}"
        is_video = str(row.get("content_type") or "").startswith(("video/", "audio/")) or saved_rel.endswith(".mp4")
        open_local_target(target, is_video=is_video)


def main() -> None:
    parser = argparse.ArgumentParser(prog="devtools_app", description="Standalone Waydroid DevTools desktop GUI")
    parser.add_argument("--url", default="http://127.0.0.1:8081", help="Self-hosted DevTools HTTP endpoint URL")
    parser.add_argument("--open-saved", action="store_true", help="Open the separate Saved Ephemeral DM Media window on startup")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    win = DevToolsMainWindow(api=DevToolsApiClient(args.url), open_saved=args.open_saved)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

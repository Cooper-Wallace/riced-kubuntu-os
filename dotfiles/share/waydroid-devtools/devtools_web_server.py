#!/usr/bin/env python3
"""
Chromium DevTools-style Network Inspector Web UI for Waydroid.
Serves live HTTP/HTTPS/WS capture telemetry and saved media/messages from Linux disk.
Part of RKO (Riced Kubuntu OS).
"""

from __future__ import annotations

import argparse
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sys
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Waydroid DevTools — Network Inspector</title>
<style>
  :root {
    --bg: #1e1e2e;
    --surface: #181825;
    --surface2: #24273a;
    --border: #313244;
    --text: #cdd6f4;
    --subtext: #a6adc8;
    --accent: #89b4fa;
    --green: #a6e3a1;
    --yellow: #f9e2af;
    --red: #f38ba8;
    --mauve: #cba6f7;
    --teal: #94e2d5;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; height: 100%;
    background: var(--bg); color: var(--text);
    font-family: "JetBrains Mono", "Inter", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
  }
  body { display: flex; flex-direction: column; overflow: hidden; }
  .toolbar {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
    padding: 8px 12px; background: var(--surface); border-bottom: 1px solid var(--border);
  }
  .brand { font-weight: 700; color: var(--mauve); margin-right: 6px; }
  .badge {
    background: var(--surface2); border: 1px solid var(--border);
    padding: 3px 8px; border-radius: 4px; color: var(--subtext); font-size: 11px;
  }
  .badge strong { color: var(--teal); }
  .search {
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 5px 8px; border-radius: 4px; width: 220px; font-family: inherit; font-size: 12px;
  }
  .pills { display: flex; gap: 4px; flex-wrap: wrap; }
  .pill {
    background: var(--surface2); color: var(--subtext); border: 1px solid var(--border);
    padding: 4px 8px; border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 11px;
  }
  .pill.active { background: var(--accent); color: #11111b; border-color: var(--accent); font-weight: 700; }
  .btn {
    background: var(--surface2); color: var(--text); border: 1px solid var(--border);
    padding: 4px 9px; border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 11px;
  }
  .btn:hover { border-color: var(--accent); }
  .main { display: flex; flex: 1; min-height: 0; }
  .table-pane { flex: 1; overflow: auto; border-right: 1px solid var(--border); }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  thead th {
    position: sticky; top: 0; z-index: 2;
    background: var(--surface); color: var(--subtext); text-align: left;
    padding: 6px 8px; border-bottom: 1px solid var(--border); font-weight: 600;
  }
  tbody tr { border-bottom: 1px solid #262738; cursor: pointer; }
  tbody tr:hover { background: #26283c; }
  tbody tr.selected { background: #2d3352; }
  td {
    padding: 5px 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .st-2xx { color: var(--green); font-weight: 700; }
  .st-3xx { color: var(--yellow); font-weight: 700; }
  .st-4xx, .st-5xx { color: var(--red); font-weight: 700; }
  .st-ws { color: var(--mauve); font-weight: 700; }
  .drawer {
    width: 48%; max-width: 780px; min-width: 340px;
    display: flex; flex-direction: column; background: var(--surface);
  }
  .drawer.hidden { display: none; }
  .tabs {
    display: flex; align-items: center; gap: 2px;
    background: var(--surface2); border-bottom: 1px solid var(--border); padding: 4px 8px 0;
  }
  .tab {
    padding: 6px 10px; cursor: pointer; color: var(--subtext);
    border-bottom: 2px solid transparent;
  }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 700; }
  .tab-close { margin-left: auto; cursor: pointer; color: var(--subtext); padding: 4px 8px; }
  .drawer-body { flex: 1; overflow: auto; padding: 12px; }
  .kv-row { display: flex; gap: 8px; padding: 3px 0; border-bottom: 1px solid #232435; }
  .kv-k { min-width: 170px; color: var(--teal); word-break: break-word; }
  .kv-v { color: var(--text); word-break: break-all; flex: 1; }
  pre {
    margin: 0; white-space: pre-wrap; word-break: break-word;
    background: var(--bg); padding: 10px; border-radius: 6px; border: 1px solid var(--border);
  }
  .media-box { display: flex; flex-direction: column; gap: 10px; }
  .media-box img, .media-box video {
    max-width: 100%; max-height: 460px; border-radius: 6px; border: 1px solid var(--border);
    background: #000;
  }
  a.file-link { color: var(--accent); text-decoration: none; }
  a.file-link:hover { text-decoration: underline; }
  .path-cell { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .path-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row-thumb {
    width: 24px; height: 24px; object-fit: cover; border-radius: 3px;
    border: 1px solid var(--border); flex-shrink: 0; background: #11111b;
  }
  .dm-badge {
    background: var(--mauve); color: #11111b; font-weight: 700; font-size: 10px;
    padding: 1px 4px; border-radius: 3px; flex-shrink: 0;
  }
  .unsaved-pill { color: var(--subtext); font-style: italic; font-size: 11px; }
</style>
</head>
<body>
  <div class="toolbar">
    <span class="brand">Waydroid DevTools</span>
    <span class="badge">Captures: <strong id="capture-dir">loading...</strong></span>
    <span class="badge">Requests: <strong id="count-req">0</strong> | Saved Disk: <strong id="count-saved">0</strong></span>
    <input id="filter-text" class="search" type="search" placeholder="Filter URL, domain, status..." />
    <div class="pills" id="type-pills">
      <button class="pill active" data-type="All">All</button>
      <button class="pill" data-type="DM">DM</button>
      <button class="pill" data-type="Fetch/XHR">Fetch/XHR</button>
      <button class="pill" data-type="Img">Img</button>
      <button class="pill" data-type="Media">Media</button>
      <button class="pill" data-type="WS">WS</button>
      <button class="pill" data-type="TLS">TLS</button>
      <button class="pill" data-type="Doc">Doc</button>
      <button class="pill" data-type="Other">Other</button>
    </div>
    <button class="btn" id="btn-clear">Clear View</button>
    <label class="badge" style="cursor:pointer;">
      <input type="checkbox" id="chk-autoscroll" checked /> Follow
    </label>
  </div>

  <div class="main">
    <div class="table-pane" id="table-pane">
      <table>
        <thead>
          <tr>
            <th style="width:62px;">Method</th>
            <th style="width:58px;">Status</th>
            <th style="width:86px;">Type</th>
            <th style="width:200px;">Domain</th>
            <th>Path / URL</th>
            <th style="width:80px;">Size</th>
            <th style="width:74px;">Time</th>
            <th style="width:190px;">Local Disk Copy</th>
          </tr>
        </thead>
        <tbody id="req-tbody"></tbody>
      </table>
    </div>

    <div class="drawer hidden" id="drawer">
      <div class="tabs">
        <div class="tab active" data-tab="headers">Headers</div>
        <div class="tab" data-tab="payload">Payload</div>
        <div class="tab" data-tab="response">Response / Message</div>
        <div class="tab" data-tab="preview">Preview / Media</div>
        <div class="tab" data-tab="ws">WebSockets</div>
        <div class="tab-close" id="btn-close-drawer" title="Close">✕</div>
      </div>
      <div class="drawer-body" id="drawer-body"></div>
    </div>
  </div>

<script>
const state = {
  allRequests: [],
  websockets: [],
  clearedBeforeSeq: 0,
  typeFilter: "All",
  textFilter: "",
  selectedSeq: null,
  activeTab: "headers",
  lastDrawerKey: "",
  lastMaxSeqRendered: 0,
  messageCache: {}
};

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[c]));
}

function fmtSize(bytes) {
  const n = Number(bytes || 0);
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / (1024 * 1024)).toFixed(2) + " MB";
}

function statusClass(code, method) {
  if (code === 495) return "st-3xx";
  if (method === "TLS" && code === 200) return "st-ws";
  if (method === "WS" || code === 101) return "st-ws";
  if (method === "DM") return "st-2xx";
  if (code >= 200 && code < 300) return "st-2xx";
  if (code >= 300 && code < 400) return "st-3xx";
  if (code >= 400) return "st-4xx";
  return "";
}

function isDmEntry(r) {
  return Boolean(
    r.is_dm ||
    r.method === "DM" ||
    (r.host && (r.host.includes("[DM") || r.host.includes("[Direct Message]"))) ||
    (r.path && r.path.includes("/direct"))
  );
}

function matchesFilter(r) {
  if (r.seq <= state.clearedBeforeSeq) return false;
  if (state.typeFilter !== "All") {
    if (state.typeFilter === "DM") {
      if (!isDmEntry(r)) return false;
    } else if (state.typeFilter === "Other") {
      if (["Fetch/XHR", "Img", "Media", "WS", "TLS", "Doc"].includes(r.resource_type)) return false;
    } else if (r.resource_type !== state.typeFilter) {
      return false;
    }
  }
  if (state.textFilter) {
    const q = state.textFilter.toLowerCase();
    const hay = `${r.method} ${r.status_code} ${r.host} ${r.path} ${r.content_type} ${r.preview || ""} ${r.saved_rel || ""}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function renderTable() {
  const tbody = document.getElementById("req-tbody");
  const filtered = state.allRequests.filter(matchesFilter);
  document.getElementById("count-req").textContent = filtered.length;
  const savedCount = filtered.filter(r => r.saved_rel && r.saved_rel.startsWith("media/")).length;
  document.getElementById("count-saved").textContent = savedCount;

  const html = filtered.map(r => {
    const sel = r.seq === state.selectedSeq ? "selected" : "";
    const sc = statusClass(r.status_code, r.method);
    const thumbHtml = r.thumb_rel
      ? `<img class="row-thumb" src="/files/${encodeURI(r.thumb_rel)}" loading="lazy" alt="" />`
      : "";
    const dmHtml = isDmEntry(r) ? `<span class="dm-badge">DM</span>` : "";
    let saved = "-";
    if (r.saved_rel) {
      saved = `<a class="file-link" href="/files/${encodeURI(r.saved_rel)}" target="_blank">${escapeHtml(r.saved_rel)}</a>`;
    } else if (r.target_media_rel) {
      saved = `<span class="unsaved-pill">Thumbnail only (click row to save)</span>`;
    }
    return `<tr data-seq="${r.seq}" class="${sel}">
      <td>${escapeHtml(r.method)}</td>
      <td class="${sc}">${escapeHtml(r.status_code)}</td>
      <td>${escapeHtml(r.resource_type)}</td>
      <td title="${escapeHtml(r.host)}">${escapeHtml(r.host)}</td>
      <td title="${escapeHtml(r.url)}"><div class="path-cell">${thumbHtml}${dmHtml}<span class="path-text">${escapeHtml(r.path)}</span></div></td>
      <td>${fmtSize(r.resp_size)}</td>
      <td>${escapeHtml(r.duration_ms)} ms</td>
      <td>${saved}</td>
    </tr>`;
  }).join("");
  tbody.innerHTML = html;

  const maxSeq = filtered.length ? Number(filtered[filtered.length - 1].seq || 0) : 0;
  if (document.getElementById("chk-autoscroll").checked && maxSeq > state.lastMaxSeqRendered) {
    const pane = document.getElementById("table-pane");
    pane.scrollTop = pane.scrollHeight;
  }
  state.lastMaxSeqRendered = maxSeq;
}

async function fetchMessageFile(relPath) {
  if (!relPath || !relPath.startsWith("messages/")) return null;
  if (state.messageCache[relPath]) return state.messageCache[relPath];
  const name = relPath.slice("messages/".length);
  try {
    const res = await fetch("/api/message/" + encodeURIComponent(name));
    if (!res.ok) return null;
    const data = await res.json();
    state.messageCache[relPath] = data;
    return data;
  } catch {
    return null;
  }
}

function renderKvList(obj) {
  const entries = Object.entries(obj || {});
  if (!entries.length) return `<div style="color:var(--subtext);">None</div>`;
  return entries.map(([k, v]) => `<div class="kv-row"><div class="kv-k">${escapeHtml(k)}</div><div class="kv-v">${escapeHtml(v)}</div></div>`).join("");
}

function prettyBody(val) {
  if (val === undefined || val === null || val === "") return "(empty)";
  if (typeof val === "object") return JSON.stringify(val, null, 2);
  return String(val);
}

async function renderDrawer(force = false) {
  const drawer = document.getElementById("drawer");
  const body = document.getElementById("drawer-body");
  const req = state.allRequests.find(r => r.seq === state.selectedSeq);
  if (!req) {
    state.lastDrawerKey = "";
    drawer.classList.add("hidden");
    return;
  }
  drawer.classList.remove("hidden");

  const drawerKey = `${state.selectedSeq}:${state.activeTab}:${req.resp_size}:${req.saved_rel || ""}`;
  if (!force && state.activeTab !== "ws" && state.lastDrawerKey === drawerKey) {
    return;
  }
  state.lastDrawerKey = drawerKey;

  if (state.activeTab === "ws") {
    const wsItems = state.websockets.slice(-100).reverse();
    body.innerHTML = wsItems.length
      ? wsItems.map(m => `<div style="margin-bottom:8px;"><div style="color:var(--teal);">${escapeHtml(m.timestamp)} [${escapeHtml(m.direction)}] ${escapeHtml(m.url)}</div><pre>${escapeHtml(m.payload)}</pre></div>`).join("")
      : `<div style="color:var(--subtext);">No WebSocket messages captured yet.</div>`;
    return;
  }

  if (state.activeTab === "headers") {
    body.innerHTML = `
      <h4 style="margin:0 0 6px;color:var(--accent);">General</h4>
      ${renderKvList({
        "Request URL": req.url,
        "Request Method": req.method,
        "Status Code": req.status_code,
        "Resource Type": req.resource_type,
        "Content-Type": req.content_type,
        "Local Saved Copy": req.saved_file || "(not persisted)"
      })}
      <h4 style="margin:14px 0 6px;color:var(--accent);">Response Headers</h4>
      ${renderKvList(req.response_headers)}
      <h4 style="margin:14px 0 6px;color:var(--accent);">Request Headers</h4>
      ${renderKvList(req.request_headers)}
    `;
    return;
  }

  let msgData = null;
  if (req.saved_rel && req.saved_rel.startsWith("messages/")) {
    msgData = await fetchMessageFile(req.saved_rel);
  }

  if (state.activeTab === "payload") {
    body.innerHTML = `<pre>${escapeHtml(prettyBody(msgData ? msgData.request_body : "(No text/JSON request payload saved)"))}</pre>`;
    return;
  }

  if (state.activeTab === "response") {
    const content = msgData ? prettyBody(msgData.response_body) : (req.preview || "(Binary or empty response)");
    body.innerHTML = `<pre>${escapeHtml(content)}</pre>`;
    return;
  }

  if (state.activeTab === "preview") {
    const rel = req.saved_rel || "";
    const fileUrl = rel ? "/files/" + encodeURI(rel) : "";
    const thumbUrl = req.thumb_rel ? "/files/" + encodeURI(req.thumb_rel) : "";
    const streamUrl = "/api/stream/" + encodeURIComponent(req.seq);
    if (req.resource_type === "Img") {
      const src = fileUrl || thumbUrl || streamUrl;
      const statusHtml = fileUrl
        ? `<a class="file-link" href="${fileUrl}" target="_blank">Open saved image: ${escapeHtml(req.saved_file || rel)}</a>`
        : `<span class="unsaved-pill">Thumbnail preview — saving full image to ${escapeHtml(req.target_media_rel || "media/")}...</span>`;
      body.innerHTML = `<div class="media-box">${statusHtml}<img src="${src}" alt="Captured image" /></div>`;
    } else if (req.resource_type === "Media") {
      const isAudio = (req.content_type || "").startsWith("audio/");
      const tag = isAudio ? "audio" : "video";
      const src = fileUrl || streamUrl;
      const poster = !isAudio && thumbUrl ? ` poster="${thumbUrl}"` : "";
      const statusHtml = fileUrl
        ? `<a class="file-link" href="${fileUrl}" target="_blank">Open saved media: ${escapeHtml(req.saved_file || rel)}</a>`
        : `<span class="unsaved-pill">Streaming on demand — saving full media to ${escapeHtml(req.target_media_rel || "media/")}...</span>`;
      body.innerHTML = `<div class="media-box">${statusHtml}<${tag} controls${poster} src="${src}"></${tag}></div>`;
    } else if (msgData) {
      const thumbBlock = thumbUrl ? `<div class="media-box" style="margin-bottom:10px;"><img src="${thumbUrl}" alt="Thumbnail" style="max-height:200px;" /></div>` : "";
      body.innerHTML = `${thumbBlock}<pre>${escapeHtml(prettyBody(msgData.response_body || msgData.request_body))}</pre>`;
    } else if (fileUrl) {
      body.innerHTML = `<a class="file-link" href="${fileUrl}" target="_blank">Download saved file: ${escapeHtml(req.saved_file || rel)}</a>`;
    } else if (thumbUrl) {
      body.innerHTML = `<div class="media-box"><img src="${thumbUrl}" alt="Thumbnail preview" /></div>`;
    } else {
      body.innerHTML = `<pre>${escapeHtml(req.preview || "(No preview available)")}</pre>`;
    }
  }
}

function setActiveTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".tab[data-tab]").forEach(x => {
    x.classList.toggle("active", x.dataset.tab === tabName);
  });
}

async function selectRequest(seq) {
  state.selectedSeq = seq;
  const req = state.allRequests.find(r => r.seq === seq);
  if (req && (req.resource_type === "Img" || req.resource_type === "Media" || req.thumb_rel) && state.activeTab === "headers") {
    setActiveTab("preview");
  }
  renderTable();
  renderDrawer(true);

  if (req && (req.resource_type === "Img" || req.resource_type === "Media" || req.target_media_rel) && !req.saved_rel && req.target_media_rel) {
    try {
      const res = await fetch("/api/save/" + encodeURIComponent(seq), { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data && data.request) {
          const idx = state.allRequests.findIndex(r => r.seq === seq);
          if (idx >= 0) {
            state.allRequests[idx] = data.request;
          }
          renderTable();
          if (state.selectedSeq === seq) {
            renderDrawer(true);
          }
        }
      }
    } catch {}
  }
}

async function poll() {
  try {
    const res = await fetch("/api/requests");
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("capture-dir").textContent = data.capture_dir || "n/a";
    state.allRequests = data.requests || [];
    state.websockets = data.websockets || [];
    renderTable();
    if (state.selectedSeq !== null) renderDrawer(false);
  } catch {}
}

document.getElementById("type-pills").addEventListener("click", (e) => {
  const btn = e.target.closest(".pill");
  if (!btn) return;
  document.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
  btn.classList.add("active");
  state.typeFilter = btn.dataset.type;
  renderTable();
});

document.getElementById("filter-text").addEventListener("input", (e) => {
  state.textFilter = e.target.value.trim();
  renderTable();
});

document.getElementById("btn-clear").addEventListener("click", () => {
  const maxSeq = state.allRequests.reduce((acc, r) => Math.max(acc, r.seq || 0), 0);
  state.clearedBeforeSeq = maxSeq;
  state.selectedSeq = null;
  renderTable();
  renderDrawer(true);
});

document.getElementById("req-tbody").addEventListener("click", (e) => {
  if (e.target.closest("a.file-link")) return;
  const tr = e.target.closest("tr[data-seq]");
  if (!tr) return;
  selectRequest(Number(tr.dataset.seq));
});

document.querySelectorAll(".tab[data-tab]").forEach(t => {
  t.addEventListener("click", () => {
    setActiveTab(t.dataset.tab);
    renderDrawer(true);
  });
});

document.getElementById("btn-close-drawer").addEventListener("click", () => {
  state.selectedSeq = null;
  renderTable();
  renderDrawer(true);
});

poll();
setInterval(poll, 750);
</script>
</body>
</html>
"""


def read_jsonl(path: Path, limit: int = 1000) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


class DevToolsRequestHandler(BaseHTTPRequestHandler):
    """Serves the Chromium DevTools UI and captured Android request/media artifacts."""

    def __init__(self, *args: Any, capture_dir: Path, capture_addon: Any = None, **kwargs: Any) -> None:
        self.capture_dir = capture_dir
        self.capture_addon = capture_addon
        super().__init__(*args, **kwargs)

    def _get_addon(self) -> Any:
        if self.capture_addon is not None:
            return self.capture_addon
        addon_dir = str(Path(__file__).resolve().parent)
        if addon_dir not in sys.path:
            sys.path.insert(0, addon_dir)
        from devtools_capture_addon import WaydroidDevToolsCapture

        return WaydroidDevToolsCapture(capture_dir=self.capture_dir)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(self, data: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _resolve_safe_path(self, rel_path: str) -> Path | None:
        root = self.capture_dir.resolve()
        candidate = (root / unquote(rel_path).lstrip("/")).resolve()
        try:
            if not candidate.is_relative_to(root):
                return None
        except AttributeError:
            if str(root) not in str(candidate):
                return None
        return candidate

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        req_path = parsed.path

        if req_path in ("/", "/index.html"):
            self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if req_path == "/api/requests":
            qs = parse_qs(parsed.query)
            since = int(qs.get("since", ["0"])[0] or 0)
            all_reqs = read_jsonl(self.capture_dir / "requests.jsonl")
            if since > 0:
                all_reqs = [r for r in all_reqs if int(r.get("seq", 0)) > since]
            ws_msgs = read_jsonl(self.capture_dir / "websocket_messages.jsonl")
            self._send_json(
                {
                    "capture_dir": str(self.capture_dir),
                    "requests": all_reqs,
                    "websockets": ws_msgs,
                }
            )
            return

        if req_path.startswith("/api/message/"):
            fname = req_path[len("/api/message/") :]
            target = self._resolve_safe_path(f"messages/{fname}")
            if target is None:
                self._send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return
            if not target.is_file():
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                data = {"raw": target.read_text(encoding="utf-8", errors="replace")}
            self._send_json(data)
            return

        if req_path.startswith("/api/stream/"):
            seq_str = req_path[len("/api/stream/") :]
            try:
                seq = int(seq_str)
            except ValueError:
                self._send_json({"error": "Invalid sequence id"}, status=HTTPStatus.BAD_REQUEST)
                return
            result = self._get_addon().read_media_bytes_for_seq(seq)
            if result is None:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            raw_bytes, ctype = result
            self._send_bytes(raw_bytes, ctype or "application/octet-stream")
            return

        if req_path.startswith("/files/"):
            rel = req_path[len("/files/") :]
            if not (rel.startswith("media/") or rel.startswith("messages/") or rel.startswith("thumbs/")):
                self._send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return
            target = self._resolve_safe_path(rel)
            if target is None:
                self._send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return
            if not target.is_file():
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            ctype, _ = mimetypes.guess_type(str(target))
            self._send_bytes(target.read_bytes(), ctype or "application/octet-stream")
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 0:
            _ = self.rfile.read(min(length, 65536))
        parsed = urlparse(self.path)
        req_path = parsed.path

        if req_path.startswith("/api/save/"):
            seq_str = req_path[len("/api/save/") :]
            try:
                seq = int(seq_str)
            except ValueError:
                self._send_json({"error": "Invalid sequence id"}, status=HTTPStatus.BAD_REQUEST)
                return
            updated = self._get_addon().save_media_for_seq(seq)
            if updated is None:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json({"ok": True, "request": updated})
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="devtools_web_server",
        description="Serve Chromium DevTools-style Network Inspector UI from Waydroid capture directory",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8081, help="Bind port (default: 8081)")
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=None,
        help="Capture directory path (default: $WAYDROID_CAPTURE_DIR or ~/Waydroid/captures/latest)",
    )
    parser.add_argument(
        "--no-harvest",
        action="store_true",
        help="Disable background Android cache harvesting",
    )
    args = parser.parse_args()

    default_dir = Path(
        os.environ.get("WAYDROID_CAPTURE_DIR")
        or (Path.home() / "Waydroid" / "captures" / "latest")
    )
    capture_dir = (args.capture_dir or default_dir).expanduser().resolve()
    capture_dir.mkdir(parents=True, exist_ok=True)

    harvester = None
    if not args.no_harvest:
        try:
            addon_dir = str(Path(__file__).resolve().parent)
            if addon_dir not in sys.path:
                sys.path.insert(0, addon_dir)
            from devtools_capture_addon import WaydroidDevToolsCapture

            harvester = WaydroidDevToolsCapture(capture_dir=capture_dir)
            harvester.start_harvester(interval=2.0, refresh_acl=True)
        except Exception:
            harvester = None

    handler = partial(DevToolsRequestHandler, capture_dir=capture_dir, capture_addon=harvester)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    bound_host, bound_port = server.server_address[:2]
    print(f"Waydroid DevTools Web UI listening at http://{bound_host}:{bound_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if harvester is not None:
            harvester.done()
        server.server_close()


if __name__ == "__main__":
    main()

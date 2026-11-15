#!/usr/bin/env python3
"""
mitmproxy addon for Chromium DevTools-style inspection and automatic local capture
of Waydroid HTTP/HTTPS requests, JSON/API/WebSocket messages, and loaded media.
"""

from __future__ import annotations

import base64
from datetime import datetime
import json
import mimetypes
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse


def classify_resource_type(content_type: str, path: str, is_ws: bool = False) -> str:
    if is_ws:
        return "WS"
    ct = (content_type or "").lower()
    low_path = (path or "").lower()

    if ct.startswith("image/") or low_path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".avif")):
        return "Img"
    if ct.startswith(("video/", "audio/")) or "mpegurl" in ct or "dash+xml" in ct or low_path.endswith((".mp4", ".m4s", ".mp3", ".aac", ".webm", ".m3u8", ".mpd")):
        return "Media"
    if "json" in ct or "graphql" in ct or "xml" in ct or "x-www-form-urlencoded" in ct or "/api/" in low_path or "/graphql" in low_path:
        return "Fetch/XHR"
    if "html" in ct:
        return "Doc"
    if "javascript" in ct or low_path.endswith(".js"):
        return "Script"
    if "css" in ct or low_path.endswith(".css"):
        return "Stylesheet"
    if "font" in ct or low_path.endswith((".woff", ".woff2", ".ttf", ".otf")):
        return "Font"
    return "Other"


def sanitize_filename(name: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "item").strip("._")
    if not cleaned:
        cleaned = "item"
    return cleaned[:max_len]


def is_text_or_message(content_type: str, body: bytes) -> bool:
    ct = (content_type or "").lower()
    if any(tok in ct for tok in ("json", "graphql", "xml", "text/", "x-www-form-urlencoded", "javascript")):
        return True
    if not ct and body:
        stripped = body[:128].lstrip()
        if stripped.startswith((b"{", b"[", b"<")):
            return True
    return False


def is_media_or_binary(content_type: str, resource_type: str, body: bytes) -> bool:
    if not body:
        return False
    ct = (content_type or "").lower()
    if resource_type in ("Img", "Media"):
        return True
    if ct.startswith(("image/", "video/", "audio/")):
        return True
    if any(tok in ct for tok in ("octet-stream", "pdf", "zip", "android.package-archive")):
        return True
    return False


class WaydroidDevToolsCapture:
    """Saves HTTP/HTTPS requests, messages, WebSocket frames, and media to Linux disk."""

    def __init__(self, capture_dir: Optional[Path] = None) -> None:
        env_dir = os.environ.get("WAYDROID_CAPTURE_DIR")
        if capture_dir is not None:
            self.capture_dir = Path(capture_dir)
        elif env_dir:
            self.capture_dir = Path(env_dir)
        else:
            ts = datetime.now().strftime("session-%Y%m%d-%H%M%S")
            self.capture_dir = Path.home() / "Waydroid" / "captures" / ts

        self.messages_dir = self.capture_dir / "messages"
        self.media_dir = self.capture_dir / "media"
        self.requests_log = self.capture_dir / "requests.jsonl"
        self.ws_log = self.capture_dir / "websocket_messages.jsonl"

        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.messages_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self._update_latest_symlink()

        self._seq = 0
        self._lock = threading.Lock()

    def _update_latest_symlink(self) -> None:
        latest = self.capture_dir.parent / "latest"
        try:
            if latest.is_symlink() or latest.exists():
                if latest.is_symlink() or latest.is_file():
                    latest.unlink()
                else:
                    return
            latest.symlink_to(self.capture_dir)
        except OSError:
            pass

    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _decode_text(raw: bytes, max_chars: int = 200_000) -> str:
        if not raw:
            return ""
        text = raw.decode("utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + "\n...[truncated]"
        return text

    @staticmethod
    def _headers_to_dict(headers: Any) -> Dict[str, str]:
        if not headers:
            return {}
        try:
            return {str(k): str(v) for k, v in headers.items()}
        except Exception:
            return dict(headers) if isinstance(headers, dict) else {}

    def response(self, flow: Any) -> None:
        try:
            req = flow.request
            resp = flow.response
            if req is None or resp is None:
                return

            seq = self._next_seq()
            url = getattr(req, "pretty_url", None) or getattr(req, "url", "")
            parsed = urlparse(url)
            host = getattr(req, "pretty_host", None) or parsed.hostname or "unknown"
            path = parsed.path or "/"
            method = getattr(req, "method", "GET")
            status_code = int(getattr(resp, "status_code", 0) or 0)

            req_headers = self._headers_to_dict(getattr(req, "headers", None))
            resp_headers = self._headers_to_dict(getattr(resp, "headers", None))

            req_ct = req_headers.get("content-type", req_headers.get("Content-Type", ""))
            resp_ct = resp_headers.get("content-type", resp_headers.get("Content-Type", ""))
            mime_only = resp_ct.split(";", 1)[0].strip().lower()

            req_body: bytes = getattr(req, "content", None) or getattr(req, "raw_content", None) or b""
            resp_body: bytes = getattr(resp, "content", None) or getattr(resp, "raw_content", None) or b""

            ts_start = getattr(req, "timestamp_start", None)
            ts_end = getattr(resp, "timestamp_end", None)
            duration_ms = round(max(0.0, (ts_end - ts_start) * 1000.0), 1) if (ts_start and ts_end) else 0.0

            resource_type = classify_resource_type(mime_only, path)
            saved_file: Optional[str] = None
            preview = ""

            # Save JSON / GraphQL / text / API messages locally
            if is_text_or_message(req_ct, req_body) or is_text_or_message(resp_ct, resp_body):
                slug = sanitize_filename(Path(path).name or "root", max_len=40)
                host_slug = sanitize_filename(host, max_len=40)
                msg_path = self.messages_dir / f"{seq:05d}_{method}_{host_slug}_{slug}.json"

                req_text = self._decode_text(req_body) if is_text_or_message(req_ct, req_body) else ""
                resp_text = self._decode_text(resp_body) if is_text_or_message(resp_ct, resp_body) else ""

                msg_payload: Dict[str, Any] = {
                    "seq": seq,
                    "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                    "method": method,
                    "url": url,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "request_headers": req_headers,
                    "response_headers": resp_headers,
                    "request_body": self._try_json(req_text),
                    "response_body": self._try_json(resp_text),
                }
                msg_path.write_text(json.dumps(msg_payload, indent=2, ensure_ascii=False), encoding="utf-8")
                saved_file = str(msg_path)
                preview = (resp_text or req_text).replace("\n", " ")[:140]

            # Save loaded media/images/videos/downloads locally
            elif is_media_or_binary(mime_only, resource_type, resp_body):
                orig_name = Path(path).name
                ext = Path(orig_name).suffix if orig_name else ""
                if not ext and mime_only:
                    ext = mimetypes.guess_extension(mime_only) or ".bin"
                base_name = sanitize_filename(Path(orig_name).stem if orig_name else "asset", max_len=40)
                host_slug = sanitize_filename(host, max_len=32)
                media_path = self.media_dir / f"{seq:05d}_{host_slug}_{base_name}{ext}"
                media_path.write_bytes(resp_body)
                saved_file = str(media_path)
                preview = f"{mime_only or 'binary'} ({len(resp_body)} bytes)"

            entry = {
                "seq": seq,
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "method": method,
                "url": url,
                "host": host,
                "path": path + (f"?{parsed.query}" if parsed.query else ""),
                "status_code": status_code,
                "resource_type": resource_type,
                "content_type": mime_only or "-",
                "req_size": len(req_body),
                "resp_size": len(resp_body),
                "duration_ms": duration_ms,
                "request_headers": req_headers,
                "response_headers": resp_headers,
                "preview": preview,
                "saved_file": saved_file,
                "saved_rel": str(Path(saved_file).relative_to(self.capture_dir)) if saved_file else None,
            }
            self._append_jsonl(self.requests_log, entry)
        except Exception:
            pass

    def websocket_message(self, flow: Any) -> None:
        try:
            ws = getattr(flow, "websocket", None)
            if ws is None or not getattr(ws, "messages", None):
                return
            msg = ws.messages[-1]
            url = getattr(flow.request, "pretty_url", None) or getattr(flow.request, "url", "")
            parsed = urlparse(url)
            host = getattr(flow.request, "pretty_host", None) or parsed.hostname or "unknown"
            direction = "client->server" if getattr(msg, "from_client", False) else "server->client"
            content = getattr(msg, "content", b"")
            is_text = bool(getattr(msg, "is_text", False))
            if isinstance(content, bytes):
                payload = self._decode_text(content, max_chars=50_000) if is_text else base64.b64encode(content).decode("ascii")
                size = len(content)
            else:
                payload = str(content)
                size = len(payload)

            ws_record = {
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "url": url,
                "host": host,
                "direction": direction,
                "is_text": is_text,
                "size": size,
                "payload": payload,
            }
            self._append_jsonl(self.ws_log, ws_record)

            seq = self._next_seq()
            self._append_jsonl(
                self.requests_log,
                {
                    "seq": seq,
                    "timestamp": ws_record["timestamp"],
                    "method": "WS",
                    "url": url,
                    "host": host,
                    "path": parsed.path or "/",
                    "status_code": 101,
                    "resource_type": "WS",
                    "content_type": f"ws/{direction}",
                    "req_size": size if getattr(msg, "from_client", False) else 0,
                    "resp_size": 0 if getattr(msg, "from_client", False) else size,
                    "duration_ms": 0.0,
                    "preview": payload.replace("\n", " ")[:140],
                    "saved_file": str(self.ws_log),
                    "saved_rel": "websocket_messages.jsonl",
                },
            )
        except Exception:
            pass

    @staticmethod
    def _try_json(text: str) -> Any:
        if not text:
            return ""
        try:
            return json.loads(text)
        except Exception:
            return text


addons = [WaydroidDevToolsCapture()]

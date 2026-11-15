#!/usr/bin/env python3
"""
mitmproxy addon for Chromium DevTools-style inspection and automatic local capture
of Waydroid HTTP/HTTPS requests, JSON/API/WebSocket messages, and loaded media.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime
import fcntl
import getpass
import gzip
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None  # type: ignore[assignment]


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
            raw_dir = Path(capture_dir)
        elif env_dir:
            raw_dir = Path(env_dir)
        else:
            ts = datetime.now().strftime("session-%Y%m%d-%H%M%S")
            raw_dir = Path.home() / "Waydroid" / "captures" / ts
        self.capture_dir = raw_dir.expanduser().resolve()

        self.messages_dir = self.capture_dir / "messages"
        self.media_dir = self.capture_dir / "media"
        self.thumbs_dir = self.capture_dir / "thumbs"
        self.staging_dir = self.capture_dir / ".staging"
        self.requests_log = self.capture_dir / "requests.jsonl"
        self.ws_log = self.capture_dir / "websocket_messages.jsonl"
        self._harvest_state_file = self.capture_dir / ".harvest_state_v2.json"
        self._legacy_harvest_state_file = self.capture_dir / ".harvest_state.json"
        self._lock_file = self.capture_dir / ".capture.lock"

        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.messages_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self._update_latest_symlink()

        self._lock = threading.Lock()
        self._seq = self._read_max_seq()
        self._harvested_files: Dict[str, Any] = self._load_harvest_state()
        self._harvester_started = False
        self._harvester_stop = threading.Event()
        self._pinned_hosts: Dict[str, float] = {}
        self.strict_mitm = os.environ.get("WAYDROID_STRICT_MITM", "0") == "1"

    @contextmanager
    def _locked_session(self) -> Iterator[None]:
        with self._lock:
            self._lock_file.parent.mkdir(parents=True, exist_ok=True)
            with self._lock_file.open("a+", encoding="utf-8") as lock_fh:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)

    def _read_max_seq(self) -> int:
        if not self.requests_log.exists():
            return 0
        max_seq = 0
        try:
            with self.requests_log.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        seq = int(json.loads(line).get("seq", 0))
                        if seq > max_seq:
                            max_seq = seq
                    except Exception:
                        continue
        except OSError:
            pass
        return max_seq

    def _load_harvest_state(self) -> Dict[str, Any]:
        if not self._harvest_state_file.exists():
            return {}
        try:
            data = json.loads(self._harvest_state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): v for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save_harvest_state(self) -> None:
        tmp = self._harvest_state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._harvested_files, indent=2), encoding="utf-8")
        tmp.replace(self._harvest_state_file)

        legacy: Dict[str, int] = {}
        for k, v in self._harvested_files.items():
            if k.startswith("dm_msg:"):
                continue
            if isinstance(v, int):
                legacy[k] = v
            elif isinstance(v, str) and ":" in v:
                try:
                    legacy[k] = int(v.rsplit(":", 1)[-1])
                except ValueError:
                    continue
        if legacy:
            tmp_legacy = self._legacy_harvest_state_file.with_suffix(".json.tmp")
            tmp_legacy.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
            tmp_legacy.replace(self._legacy_harvest_state_file)

    def _generate_image_thumbnail(self, raw: bytes, thumb_path: Path) -> bool:
        if not raw:
            return False
        if PILImage is not None:
            try:
                im = PILImage.open(io.BytesIO(raw))
                im.thumbnail((200, 200))
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=70, optimize=True)
                thumb_path.write_bytes(buf.getvalue())
                return True
            except Exception:
                pass
        if len(raw) <= 65536 and self._detect_image_magic(raw[:16]) is not None:
            try:
                thumb_path.write_bytes(raw)
                return True
            except OSError:
                pass
        return False

    def _generate_video_thumbnail(
        self,
        first_chunk_path: Path,
        thumb_path: Path,
        cover_img_path: Optional[Path] = None,
    ) -> bool:
        if cover_img_path is not None and cover_img_path.is_file():
            try:
                if self._generate_image_thumbnail(cover_img_path.read_bytes(), thumb_path):
                    return True
            except OSError:
                pass
        if not shutil.which("ffmpeg") or not first_chunk_path.is_file():
            return False
        try:
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-i",
                    str(first_chunk_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=min(200\\,iw):-2",
                    "-q:v",
                    "6",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "mjpeg",
                    "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=4,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                thumb_path.write_bytes(proc.stdout)
                return True
        except Exception:
            pass
        return False

    def read_media_bytes_for_seq(self, seq: int) -> Optional[tuple[bytes, str]]:
        if not self.requests_log.exists():
            return None
        target_row: Optional[Dict[str, Any]] = None
        with self.requests_log.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(row.get("seq", -1)) == seq:
                    target_row = row
                    break
        if target_row is None:
            return None
        ctype = str(target_row.get("content_type") or "application/octet-stream")
        saved_rel = target_row.get("saved_rel")
        if saved_rel:
            saved_path = (self.capture_dir / saved_rel).resolve()
            if saved_path.is_file():
                return (saved_path.read_bytes(), ctype)
        source_files = target_row.get("source_files") or []
        if not source_files:
            return None
        parts: List[bytes] = []
        for sf in source_files:
            p = Path(sf)
            if not p.is_file():
                return None
            parts.append(p.read_bytes())
        return (b"".join(parts), ctype)

    def save_media_for_seq(self, seq: int) -> Optional[Dict[str, Any]]:
        if not self.requests_log.exists():
            return None
        with self._locked_session():
            lines = self.requests_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            rows: List[Dict[str, Any]] = []
            target_idx = -1
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(row.get("seq", -1)) == seq:
                    target_idx = len(rows)
                rows.append(row)

            if target_idx < 0:
                return None
            row = rows[target_idx]

            existing_rel = row.get("saved_rel")
            if existing_rel:
                existing_path = (self.capture_dir / str(existing_rel)).resolve()
                if existing_path.is_file():
                    return row

            target_rel = row.get("target_media_rel")
            if not target_rel:
                return row

            dest = (self.capture_dir / str(target_rel)).resolve()
            cap_root = self.capture_dir.resolve()
            if not dest.is_relative_to(cap_root):
                return None

            source_files = [Path(sf) for sf in (row.get("source_files") or [])]
            if not source_files:
                return None
            parts: List[bytes] = []
            for p in source_files:
                if not p.is_file():
                    return None
                parts.append(p.read_bytes())

            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp_dest = dest.with_name(dest.name + ".tmp")
            tmp_dest.write_bytes(b"".join(parts))
            tmp_dest.replace(dest)

            row["saved_rel"] = str(dest.relative_to(cap_root))
            row["saved_file"] = str(dest)

            staging_root = self.staging_dir.resolve()
            for p in source_files:
                try:
                    if p.resolve().is_relative_to(staging_root) and p.is_file():
                        p.unlink()
                except OSError:
                    pass

            tmp_log = self.requests_log.with_suffix(".jsonl.tmp")
            tmp_log.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                encoding="utf-8",
            )
            tmp_log.replace(self.requests_log)
            return row

    def _update_latest_symlink(self) -> None:
        latest = self.capture_dir.parent / "latest"
        try:
            if latest == self.capture_dir or latest.resolve(strict=False) == self.capture_dir:
                return
            if latest.is_symlink() or latest.exists():
                if latest.is_symlink() or latest.is_file():
                    latest.unlink()
                else:
                    return
            latest.symlink_to(self.capture_dir)
        except OSError:
            pass

    def _next_seq_unlocked(self) -> int:
        disk_max = self._read_max_seq()
        if disk_max > self._seq:
            self._seq = disk_max
        self._seq += 1
        return self._seq

    def _next_seq(self) -> int:
        with self._locked_session():
            return self._next_seq_unlocked()

    @staticmethod
    def _append_jsonl_unlocked(path: Path, record: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        with self._locked_session():
            self._append_jsonl_unlocked(path, record)

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
            thumb_rel: Optional[str] = None
            target_media_rel: Optional[str] = None
            source_files: Optional[List[str]] = None
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

            # Cache thumbnails for media/images/downloads; persist full file only when selected
            elif is_media_or_binary(mime_only, resource_type, resp_body):
                orig_name = Path(path).name
                ext = Path(orig_name).suffix if orig_name else ""
                if not ext and mime_only:
                    ext = mimetypes.guess_extension(mime_only) or ".bin"
                base_name = sanitize_filename(Path(orig_name).stem if orig_name else "asset", max_len=40)
                host_slug = sanitize_filename(host, max_len=32)
                filename = f"{seq:05d}_{host_slug}_{base_name}{ext}"
                staging_path = self.staging_dir / filename
                staging_path.write_bytes(resp_body)
                source_files = [str(staging_path)]
                target_media_rel = f"media/{filename}"

                thumb_path = self.thumbs_dir / f"{seq:05d}_thumb.jpg"
                thumb_ok = False
                if resource_type == "Img" or mime_only.startswith("image/"):
                    thumb_ok = self._generate_image_thumbnail(resp_body, thumb_path)
                elif resource_type == "Media" or mime_only.startswith(("video/", "audio/")):
                    thumb_ok = self._generate_video_thumbnail(staging_path, thumb_path)
                if thumb_ok:
                    thumb_rel = f"thumbs/{thumb_path.name}"
                preview = f"{mime_only or 'binary'} ({len(resp_body)} bytes)"

            entry: Dict[str, Any] = {
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
            if thumb_rel:
                entry["thumb_rel"] = thumb_rel
            if target_media_rel:
                entry["target_media_rel"] = target_media_rel
            if source_files:
                entry["source_files"] = source_files
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
    def _decode_alpn(alpn_list: Any) -> list[str]:
        out: list[str] = []
        for item in (alpn_list or []):
            if isinstance(item, (bytes, bytearray)):
                out.append(item.decode("ascii", errors="replace"))
            else:
                out.append(str(item))
        return out

    def _record_tls_event(
        self,
        *,
        host: str,
        port: int,
        status_code: int,
        content_type: str,
        path: str,
        preview: str,
        file_tag: str,
        details: Dict[str, Any],
    ) -> None:
        seq = self._next_seq()
        host_slug = sanitize_filename(host, max_len=40)
        msg_path = self.messages_dir / f"{seq:05d}_TLS_{host_slug}_{file_tag}.json"
        url = f"https://{host}:{port}/"
        payload: Dict[str, Any] = {
            "seq": seq,
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "method": "TLS",
            "url": url,
            "status_code": status_code,
            "duration_ms": 0.0,
            "request_headers": {"SNI": host, "Port": str(port)},
            "response_headers": {"Mode": content_type},
            "request_body": details,
            "response_body": preview,
        }
        msg_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self._append_jsonl(
            self.requests_log,
            {
                "seq": seq,
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "method": "TLS",
                "url": url,
                "host": host,
                "path": path,
                "status_code": status_code,
                "resource_type": "TLS",
                "content_type": content_type,
                "req_size": 0,
                "resp_size": 0,
                "duration_ms": 0.0,
                "request_headers": {"SNI": host, "Port": str(port)},
                "response_headers": {"Mode": content_type},
                "preview": preview,
                "saved_file": str(msg_path),
                "saved_rel": str(msg_path.relative_to(self.capture_dir)),
            },
        )

    def tls_failed_client(self, data: Any) -> None:
        try:
            conn = getattr(data, "conn", None)
            ctx = getattr(data, "context", None)
            sni = getattr(conn, "sni", None)
            server_addr = getattr(getattr(ctx, "server", None), "address", None)
            alpn_offers = self._decode_alpn(getattr(conn, "alpn_offers", None))
            err = str(getattr(conn, "error", "") or "Client rejected proxy certificate (TLS pinning)")
            host = sni or (server_addr[0] if server_addr else "unknown")
            port = int(server_addr[1]) if (server_addr and len(server_addr) > 1) else 443

            passthrough_enabled = False
            if not self.strict_mitm and host not in ("unknown", "www.instagram.com"):
                self._pinned_hosts[host] = time.time() + 600.0
                passthrough_enabled = True

            preview = (
                f"Client rejected proxy CA for {host}:{port} ({err})"
                + ("; auto-passthrough enabled for 600s" if passthrough_enabled else "")
            )
            self._record_tls_event(
                host=host,
                port=port,
                status_code=495,
                content_type="tls/cert-pinned",
                path="/ [TLS Cert-Pinned -> Auto-Passthrough]",
                preview=preview,
                file_tag="pinned",
                details={
                    "sni": sni,
                    "server_address": f"{server_addr[0]}:{port}" if server_addr else None,
                    "alpn_offers": alpn_offers,
                    "error": err,
                    "auto_passthrough_enabled": passthrough_enabled,
                },
            )
        except Exception:
            pass

    def tls_clienthello(self, data: Any) -> None:
        try:
            ch = getattr(data, "client_hello", None)
            ctx = getattr(data, "context", None)
            sni = getattr(ch, "sni", None)
            alpn_protocols = self._decode_alpn(getattr(ch, "alpn_protocols", None))
            server_addr = getattr(getattr(ctx, "server", None), "address", None)
            host = sni or (server_addr[0] if server_addr else "unknown")
            port = int(server_addr[1]) if (server_addr and len(server_addr) > 1) else 443

            if not self.strict_mitm and self._pinned_hosts.get(host, 0.0) > time.time():
                data.ignore_connection = True
                target_ip = server_addr[0] if server_addr else host
                self._record_tls_event(
                    host=host,
                    port=port,
                    status_code=200,
                    content_type="tls/passthrough",
                    path=f"/ [TLS Passthrough -> {target_ip}:{port}]",
                    preview=f"Forwarded pinned TLS connection directly to {target_ip}:{port}",
                    file_tag="passthrough",
                    details={
                        "sni": sni,
                        "server_address": f"{target_ip}:{port}",
                        "alpn_protocols": alpn_protocols,
                        "passthrough": True,
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

    @staticmethod
    def _decompress_maybe(raw: bytes) -> bytes:
        if len(raw) >= 2 and raw[:2] == b"\x1f\x8b":
            return gzip.decompress(raw)
        return raw

    @staticmethod
    def _detect_image_magic(data: bytes) -> Optional[tuple[str, str]]:
        if data.startswith(b"\xff\xd8\xff"):
            return ("image/jpeg", ".jpg")
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ("image/png", ".png")
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ("image/webp", ".webp")
        if data.startswith((b"GIF87a", b"GIF89a")):
            return ("image/gif", ".gif")
        if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis", b"heic", b"heix", b"mif1"):
            return ("image/avif", ".avif")
        return None

    @staticmethod
    def _infer_ig_cache_endpoint(body: Any, prefix: str) -> str:
        if isinstance(body, dict):
            if "sectional_items" in body:
                return "/api/v1/discover/topical_explore/"
            if "items_with_ads" in body:
                return "/api/v1/clips/home/"
            if "friend_request_stories" in body or "priority_stories" in body:
                return "/api/v1/news/inbox/"
            if "tray" in body:
                return "/api/v1/feed/reels_tray/"
            if "user" in body:
                return "/api/v1/users/info/"
            if "friending_unit" in body or "empty_state_item" in body:
                return "/api/v1/discover/ayml/"
        return f"/api/v1/cache/{prefix}"

    @staticmethod
    def _decode_ig_stash_media_id(filename: str) -> Optional[str]:
        b64_part = filename.split(".", 1)[0].strip()
        if not b64_part:
            return None
        pad_len = (-len(b64_part)) % 4
        padded = b64_part + ("=" * pad_len)
        for decoder in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                decoded = decoder(padded).decode("ascii", errors="strict")
                if decoded.isdigit() and len(decoded) >= 8:
                    return decoded
            except Exception:
                continue
        return None

    def _build_ig_stash_cover_index(self, cache_dir: Path) -> Dict[str, Path]:
        index: Dict[str, Path] = {}
        stash_clean = cache_dir / "images.stash" / "clean"
        if not stash_clean.is_dir():
            return index
        try:
            for p in stash_clean.iterdir():
                if not p.is_file():
                    continue
                b64_prefix = p.name.split(".", 1)[0].rstrip("=")
                if b64_prefix:
                    index.setdefault(b64_prefix, p)
        except OSError:
            pass
        return index

    def _find_cover_for_media_pk(self, media_pk: str, cover_index: Dict[str, Path]) -> Optional[Path]:
        if not media_pk or not cover_index:
            return None
        b64_pk = base64.b64encode(media_pk.encode("ascii")).decode("ascii").rstrip("=")
        if b64_pk in cover_index:
            return cover_index[b64_pk]
        for key, path in cover_index.items():
            if key.startswith(b64_pk):
                return path
        return None

    def _refresh_app_cache_acls(self, app_data_root: Path) -> None:
        if not app_data_root.exists():
            return
        user = getpass.getuser()
        acl_spec = f"u:{user}:rX"
        try:
            subprocess.run(
                ["sudo", "-n", "setfacl", "-m", acl_spec, str(app_data_root)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            shallow_targets: list[str] = []
            deep_targets: list[str] = []
            for pkg_dir in app_data_root.iterdir():
                if not pkg_dir.name or pkg_dir.name.startswith("."):
                    continue
                if "instagram" in pkg_dir.name or (pkg_dir / "cache").exists() or (pkg_dir / "databases").exists():
                    shallow_targets.append(str(pkg_dir))
                    for sub_name in ("cache", "databases", "files", "app_msi_metadata_store"):
                        sub_path = pkg_dir / sub_name
                        if sub_path.exists():
                            shallow_targets.append(str(sub_path))
                            deep_targets.append(str(sub_path))
            if shallow_targets:
                subprocess.run(
                    ["sudo", "-n", "setfacl", "-m", acl_spec, *shallow_targets],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            if deep_targets:
                subprocess.run(
                    ["sudo", "-n", "setfacl", "-R", "-m", acl_spec, *deep_targets],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
        except Exception:
            pass

    @staticmethod
    def _extract_dm_media_info(msg_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidates_objs = [
            msg_obj.get("media"),
            (msg_obj.get("visual_media") or {}).get("media") if isinstance(msg_obj.get("visual_media"), dict) else None,
            msg_obj.get("media_share"),
            (msg_obj.get("clip") or {}).get("clip") if isinstance(msg_obj.get("clip"), dict) else None,
            (msg_obj.get("voice_media") or {}).get("media") if isinstance(msg_obj.get("voice_media"), dict) else None,
        ]
        for m in candidates_objs:
            if not isinstance(m, dict):
                continue
            raw_id = str(m.get("id") or m.get("pk") or "")
            media_pk = raw_id.split("_", 1)[0]
            img_cands = (m.get("image_versions2") or {}).get("candidates") or []
            vid_vers = m.get("video_versions") or []
            audio_src = (m.get("audio") or {}).get("audio_src") if isinstance(m.get("audio"), dict) else None
            cdn_url = ""
            width = m.get("original_width") or ""
            height = m.get("original_height") or ""
            if img_cands and isinstance(img_cands[0], dict):
                cdn_url = str(img_cands[0].get("url") or "")
                width = width or img_cands[0].get("width") or ""
                height = height or img_cands[0].get("height") or ""
            elif vid_vers and isinstance(vid_vers[0], dict):
                cdn_url = str(vid_vers[0].get("url") or "")
                width = width or vid_vers[0].get("width") or ""
                height = height or vid_vers[0].get("height") or ""
            elif audio_src:
                cdn_url = str(audio_src)
            if media_pk or cdn_url:
                return {
                    "media_id": media_pk or raw_id,
                    "full_id": raw_id or media_pk,
                    "media_type": m.get("media_type"),
                    "width": width,
                    "height": height,
                    "cdn_url": cdn_url,
                }
        return None

    def _harvest_direct_messages(
        self,
        pkg: str,
        pkg_slug: str,
        pkg_dir: Path,
    ) -> tuple[int, Dict[str, Dict[str, Any]]]:
        db_path = pkg_dir / "databases" / "direct.db"
        dm_media_map: Dict[str, Dict[str, Any]] = {}
        if not db_path.is_file():
            return 0, dm_media_map

        conn: Optional[sqlite3.Connection] = None
        tmp_dir: Optional[Path] = None
        try:
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
            except sqlite3.Error:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                import tempfile

                tmp_dir = Path(tempfile.mkdtemp(prefix="rko-dm-"))
                tmp_db = tmp_dir / "direct.db"
                shutil.copy2(db_path, tmp_db)
                for suffix in ("-wal", "-shm", "-journal"):
                    side = db_path.with_name(db_path.name + suffix)
                    if side.is_file():
                        shutil.copy2(side, tmp_dir / side.name)
                conn = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)

            cur = conn.cursor()
            user_map: Dict[str, str] = {}
            try:
                for (tinfo_raw,) in cur.execute("SELECT thread_info FROM threads"):
                    if not tinfo_raw:
                        continue
                    t_str = tinfo_raw.decode("utf-8", errors="replace") if isinstance(tinfo_raw, (bytes, bytearray)) else str(tinfo_raw)
                    t_obj = json.loads(t_str)
                    participants = list(t_obj.get("recipients") or [])
                    if isinstance(t_obj.get("inviter"), dict):
                        participants.append(t_obj["inviter"])
                    for u in participants:
                        if not isinstance(u, dict):
                            continue
                        uid = str(u.get("id") or "")
                        uname = u.get("username") or u.get("short_name") or u.get("full_name") or ""
                        if uid and uname:
                            user_map[uid] = f"@{uname}"
            except Exception:
                pass

            count = 0
            cover_index = self._build_ig_stash_cover_index(pkg_dir / "cache")
            rows = cur.execute(
                "SELECT _id, user_id, server_item_id, thread_id, timestamp, message_type, text, message "
                "FROM messages ORDER BY timestamp ASC"
            ).fetchall()

            for row_id, row_uid, server_item_id, thread_id, ts, msg_type, col_text, msg_raw in rows:
                msg_str = (
                    msg_raw.decode("utf-8", errors="replace")
                    if isinstance(msg_raw, (bytes, bytearray))
                    else str(msg_raw or "")
                )
                msg_obj = self._try_json(msg_str)
                if not isinstance(msg_obj, dict):
                    msg_obj = {"raw": msg_str}

                sender_id = str(msg_obj.get("user_id") or row_uid or "")
                sender = user_map.get(sender_id) or ("You" if msg_obj.get("is_sent_by_viewer") else f"user:{sender_id}")
                item_type = str(msg_obj.get("item_type") or msg_type or "message")
                text_val = str(msg_obj.get("text") or col_text or "").strip()
                item_key = str(server_item_id or msg_obj.get("item_id") or row_id)
                view_ts = msg_obj.get("ephemeral_view_timestamp_ms") or 0
                seen_count = msg_obj.get("seen_count") or 0

                media_info = self._extract_dm_media_info(msg_obj)
                if media_info is not None:
                    media_info["sender"] = sender
                    media_info["thread_id"] = str(thread_id or "")
                    media_info["item_id"] = item_key
                    media_info["is_disappearing"] = bool(msg_obj.get("is_disappearing"))
                    media_info["view_ts"] = view_ts
                    if media_info.get("media_id"):
                        dm_media_map[str(media_info["media_id"])] = media_info
                    if media_info.get("full_id"):
                        dm_media_map[str(media_info["full_id"])] = media_info

                state_key = f"dm_msg:{pkg}:{item_key}"
                marker = f"{ts}:{view_ts}:{seen_count}:{len(msg_str)}"
                if self._harvested_files.get(state_key) == marker:
                    continue

                seq = self._next_seq_unlocked()
                msg_path = self.messages_dir / f"{seq:05d}_DM_{pkg_slug}_{sanitize_filename(item_key, 24)}.json"
                url = f"https://{pkg}.cache/direct_v2/threads/{sanitize_filename(str(thread_id or 'thread'), 32)}/items/{sanitize_filename(item_key, 32)}"
                summary = (
                    f'"{text_val[:40]}"'
                    if text_val
                    else (f"media:{media_info['media_id']}" if media_info else item_type)
                )
                req_path = f"/direct_v2/threads/{sender}/{item_type} ({summary})"
                payload = {
                    "seq": seq,
                    "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                    "method": "DM",
                    "url": url,
                    "status_code": 200,
                    "duration_ms": 0.0,
                    "request_headers": {
                        "Host": f"{pkg} [Direct Message]",
                        "Sender": sender,
                        "Thread-ID": str(thread_id or ""),
                        "Item-Type": item_type,
                    },
                    "response_headers": {
                        "Content-Type": "application/json",
                        "X-Source": f"{pkg} direct.db",
                    },
                    "request_body": {
                        "sender": sender,
                        "thread_id": str(thread_id or ""),
                        "is_disappearing": bool(msg_obj.get("is_disappearing")),
                        "viewed_at_ms": view_ts or None,
                    },
                    "response_body": msg_obj,
                }
                msg_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

                thumb_rel: Optional[str] = None
                if media_info and media_info.get("media_id"):
                    cover_path = self._find_cover_for_media_pk(str(media_info["media_id"]), cover_index)
                    if cover_path is not None:
                        try:
                            thumb_path = self.thumbs_dir / f"{seq:05d}_thumb.jpg"
                            if self._generate_image_thumbnail(cover_path.read_bytes(), thumb_path):
                                thumb_rel = f"thumbs/{thumb_path.name}"
                        except OSError:
                            pass

                dm_entry: Dict[str, Any] = {
                    "seq": seq,
                    "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "method": "DM",
                    "url": url,
                    "host": f"{pkg} [Direct Message]",
                    "path": req_path,
                    "status_code": 200,
                    "resource_type": "Fetch/XHR",
                    "content_type": "application/json",
                    "req_size": 0,
                    "resp_size": len(msg_str.encode("utf-8", errors="ignore")),
                    "duration_ms": 0.0,
                    "is_dm": True,
                    "request_headers": {"Sender": sender, "Item-Type": item_type, "Thread-ID": str(thread_id or "")},
                    "response_headers": {"Content-Type": "application/json", "X-Source": f"{pkg} direct.db"},
                    "preview": f"[{sender}] {item_type}: {text_val or (media_info['media_id'] if media_info else msg_str[:100])}"[:140],
                    "saved_file": str(msg_path),
                    "saved_rel": str(msg_path.relative_to(self.capture_dir)),
                }
                if thumb_rel:
                    dm_entry["thumb_rel"] = thumb_rel
                self._append_jsonl_unlocked(self.requests_log, dm_entry)
                self._harvested_files[state_key] = marker
                count += 1
            return count, dm_media_map
        except Exception:
            return 0, dm_media_map
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def _harvest_http_responses(self, pkg: str, pkg_slug: str, cache_dir: Path) -> int:
        http_dir = cache_dir / "http_responses"
        if not http_dir.is_dir():
            return 0
        candidates: list[tuple[int, Path]] = []
        for body_path in http_dir.iterdir():
            name = body_path.name
            if not name.endswith("-body_gzip.clean") or "-copy" in name:
                continue
            try:
                st = body_path.stat()
                if st.st_size > 0:
                    candidates.append((int(st.st_mtime_ns), body_path))
            except OSError:
                continue
        candidates.sort(key=lambda item: (item[0], str(item[1])))

        count = 0
        for mtime_ns, body_path in candidates:
            name = body_path.name
            prefix = name[: -len("-body_gzip.clean")]
            state_key = f"http:{pkg}:{prefix}"
            if self._harvested_files.get(state_key) == mtime_ns:
                continue
            try:
                raw_body = self._decompress_maybe(body_path.read_bytes())
            except Exception:
                continue

            body_text = self._decode_text(raw_body)
            parsed_body = self._try_json(body_text)
            status_code = 200
            resp_headers: Dict[str, str] = {"X-Source": f"{pkg} http_responses cache"}

            info_path = http_dir / f"{prefix}-resp_info_gzip.clean"
            if info_path.is_file():
                try:
                    info_raw = self._decompress_maybe(info_path.read_bytes())
                    info_obj = json.loads(info_raw.decode("utf-8", errors="replace"))
                    if isinstance(info_obj, dict):
                        status_code = int(info_obj.get("status_code") or 200)
                        for hdr in info_obj.get("headers") or []:
                            if isinstance(hdr, dict) and "name" in hdr and "value" in hdr:
                                resp_headers[str(hdr["name"])] = str(hdr["value"])
                except Exception:
                    pass

            seq = self._next_seq_unlocked()
            endpoint = self._infer_ig_cache_endpoint(parsed_body, prefix)
            msg_path = self.messages_dir / f"{seq:05d}_GET_{pkg_slug}_{sanitize_filename(prefix, 24)}.json"
            url = f"https://{pkg}.cache{endpoint}"
            msg_payload: Dict[str, Any] = {
                "seq": seq,
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "method": "GET",
                "url": url,
                "status_code": status_code,
                "duration_ms": 0.0,
                "request_headers": {"Host": f"{pkg} [App Cache]", "Source": str(body_path)},
                "response_headers": resp_headers,
                "request_body": "",
                "response_body": parsed_body,
            }
            msg_path.write_text(json.dumps(msg_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self._append_jsonl_unlocked(
                self.requests_log,
                {
                    "seq": seq,
                    "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "method": "GET",
                    "url": url,
                    "host": f"{pkg} [App Cache]",
                    "path": endpoint,
                    "status_code": status_code,
                    "resource_type": "Fetch/XHR",
                    "content_type": "application/json",
                    "req_size": 0,
                    "resp_size": len(raw_body),
                    "duration_ms": 0.0,
                    "request_headers": {"Source": body_path.name},
                    "response_headers": resp_headers,
                    "preview": body_text.replace("\n", " ")[:140],
                    "saved_file": str(msg_path),
                    "saved_rel": str(msg_path.relative_to(self.capture_dir)),
                },
            )
            self._harvested_files[state_key] = mtime_ns
            count += 1
        return count

    def _harvest_image_caches(
        self,
        pkg: str,
        pkg_slug: str,
        cache_dir: Path,
        pkg_dir: Optional[Path] = None,
        dm_media_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> int:
        count = 0
        dm_map = dm_media_map or {}
        base_root = pkg_dir or cache_dir.parent
        subdirs = (
            cache_dir / "images.stash" / "clean",
            cache_dir / "image_manager_disk_cache",
            cache_dir / "original_images",
            cache_dir / "original_media",
            cache_dir / "tmp_photo",
            base_root / "files" / "ig_original_images",
            base_root / "files" / "pending_media_images",
        )
        items: list[tuple[int, Path, Path]] = []
        for sub in subdirs:
            if not sub.is_dir():
                continue
            rel_base = cache_dir if cache_dir in sub.parents or sub == cache_dir else base_root
            try:
                for p in sub.rglob("*"):
                    if not p.is_file():
                        continue
                    try:
                        st = p.stat()
                        items.append((int(st.st_mtime_ns), rel_base, p))
                    except OSError:
                        continue
            except OSError:
                continue

        items.sort(key=lambda item: (item[0], str(item[2])))
        for mtime_ns, rel_base, img_path in items:
            rel = str(img_path.relative_to(rel_base))
            state_key = f"img:{pkg}:{rel}"
            try:
                raw = img_path.read_bytes()
            except OSError:
                continue
            if not raw:
                continue
            marker = f"{mtime_ns}:{len(raw)}"
            if self._harvested_files.get(state_key) == marker:
                continue
            magic = self._detect_image_magic(raw[:16])
            if magic is None:
                continue
            mime_type, ext = magic

            decoded_id = self._decode_ig_stash_media_id(img_path.name)
            dm_info = dm_map.get(decoded_id) if decoded_id else None
            if dm_info is None and dm_map:
                stem_b64 = img_path.name.split(".", 1)[0].rstrip("=")
                for mid, info in dm_map.items():
                    mid_b64 = base64.b64encode(mid.encode("ascii")).decode("ascii").rstrip("=")
                    if stem_b64 and mid_b64 and stem_b64.startswith(mid_b64):
                        dm_info = info
                        decoded_id = mid
                        break

            seq = self._next_seq_unlocked()
            short_name = sanitize_filename(img_path.stem or "image", max_len=36)
            target_rel = f"media/{seq:05d}_{pkg_slug}_{short_name}{ext}"
            thumb_path = self.thumbs_dir / f"{seq:05d}_thumb.jpg"
            thumb_rel = f"thumbs/{thumb_path.name}" if self._generate_image_thumbnail(raw, thumb_path) else None

            url = f"https://{pkg}.cache/{rel}"
            req_headers: Dict[str, str] = {"Source": rel}
            is_dm = dm_info is not None
            if is_dm and dm_info is not None:
                sender = dm_info.get("sender") or "DM"
                dims = f"{dm_info.get('width')}x{dm_info.get('height')}" if dm_info.get("width") else "image"
                host_label = f"{pkg} [DM Media {sender}]"
                path_label = f"/direct/media/{decoded_id or short_name} ({dims}) [from {sender}]"
                req_headers["DM-Sender"] = str(sender)
                req_headers["DM-Media-ID"] = str(decoded_id or "")
                if dm_info.get("cdn_url"):
                    req_headers["CDN-URL"] = str(dm_info["cdn_url"])[:300]
                preview_text = f"DM {mime_type} from {sender} ({len(raw)} bytes)"
            else:
                host_label = f"{pkg} [App Cache]"
                path_label = f"/{rel}"
                preview_text = f"{mime_type} ({len(raw)} bytes)"

            entry: Dict[str, Any] = {
                "seq": seq,
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "method": "GET",
                "url": url,
                "host": host_label,
                "path": path_label,
                "status_code": 200,
                "resource_type": "Img",
                "content_type": mime_type,
                "req_size": 0,
                "resp_size": len(raw),
                "duration_ms": 0.0,
                "request_headers": req_headers,
                "response_headers": {"Content-Type": mime_type, "X-Source": "Android Disk Cache"},
                "preview": preview_text,
                "saved_file": None,
                "saved_rel": None,
                "target_media_rel": target_rel,
                "source_files": [str(img_path)],
            }
            if thumb_rel:
                entry["thumb_rel"] = thumb_rel
            if is_dm:
                entry["is_dm"] = True
            self._append_jsonl_unlocked(self.requests_log, entry)
            self._harvested_files[state_key] = marker
            count += 1
        return count

    def _harvest_exoplayer_caches(
        self,
        pkg: str,
        pkg_slug: str,
        cache_dir: Path,
        dm_media_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> int:
        exo_root = cache_dir / "ExoPlayerCacheDir" / "videocache"
        if not exo_root.is_dir():
            return 0
        streams: Dict[str, list[tuple[int, Path, int]]] = {}
        try:
            exo_files = sorted(exo_root.rglob("*.v2.exo"))
        except OSError:
            return 0

        for exo_path in exo_files:
            if not exo_path.is_file():
                continue
            m = re.match(r"^(.+)\.(\d+)\.(\d+)\.v2\.exo$", exo_path.name)
            if not m:
                continue
            stream_prefix = m.group(1)
            offset = int(m.group(2))
            try:
                mtime_ns = int(exo_path.stat().st_mtime_ns)
            except OSError:
                mtime_ns = 0
            streams.setdefault(stream_prefix, []).append((offset, exo_path, mtime_ns))

        stream_items: list[tuple[int, str, list[tuple[int, Path, int]]]] = []
        for stream_prefix, chunk_list in streams.items():
            latest_mtime = max(item[2] for item in chunk_list)
            stream_items.append((latest_mtime, stream_prefix, chunk_list))
        stream_items.sort(key=lambda item: (item[0], item[1]))

        dm_map = dm_media_map or {}
        cover_index = self._build_ig_stash_cover_index(cache_dir)
        count = 0
        for _, stream_prefix, chunk_list in stream_items:
            chunk_list.sort(key=lambda item: item[0])
            if not chunk_list or chunk_list[0][0] != 0:
                continue
            try:
                first_bytes = chunk_list[0][1].read_bytes()
            except OSError:
                continue
            if len(first_bytes) < 8 or first_bytes[4:8] != b"ftyp":
                continue

            total_size = 0
            failed = False
            for _, p, _ in chunk_list:
                try:
                    total_size += int(p.stat().st_size)
                except OSError:
                    failed = True
                    break
            if failed or total_size <= 0:
                continue

            stream_key = f"exo:{pkg}:{stream_prefix}"
            prev_len = int(self._harvested_files.get(stream_key) or 0)
            if total_size <= prev_len:
                continue

            is_audio = "a.-1." in stream_prefix
            ctype = "audio/mp4" if is_audio else "video/mp4"
            tag = "audio" if is_audio else "video"
            short_id = sanitize_filename(stream_prefix.split(".")[0], max_len=36)
            media_pk = stream_prefix.split("_", 1)[0]
            dm_info = dm_map.get(media_pk) or dm_map.get(short_id)

            seq = self._next_seq_unlocked()
            target_rel = f"media/{seq:05d}_{pkg_slug}_{short_id}_{tag}.mp4"
            thumb_rel: Optional[str] = None
            if not is_audio:
                cover_path = self._find_cover_for_media_pk(media_pk, cover_index)
                thumb_path = self.thumbs_dir / f"{seq:05d}_thumb.jpg"
                if self._generate_video_thumbnail(chunk_list[0][1], thumb_path, cover_img_path=cover_path):
                    thumb_rel = f"thumbs/{thumb_path.name}"

            url = f"https://{pkg}.cache/videocache/{short_id}_{tag}.mp4"
            req_headers: Dict[str, str] = {"Chunks": str(len(chunk_list)), "Stream": stream_prefix[:64]}
            is_dm = dm_info is not None
            if is_dm and dm_info is not None:
                sender = dm_info.get("sender") or "DM"
                host_label = f"{pkg} [DM Media {sender}]"
                path_label = f"/direct/media/{short_id}_{tag}.mp4 ({len(chunk_list)} chunk(s)) [from {sender}]"
                req_headers["DM-Sender"] = str(sender)
            else:
                host_label = f"{pkg} [App Cache]"
                path_label = f"/videocache/{short_id}_{tag}.mp4 ({len(chunk_list)} chunk(s))"

            entry: Dict[str, Any] = {
                "seq": seq,
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "method": "GET",
                "url": url,
                "host": host_label,
                "path": path_label,
                "status_code": 200,
                "resource_type": "Media",
                "content_type": ctype,
                "req_size": 0,
                "resp_size": total_size,
                "duration_ms": 0.0,
                "request_headers": req_headers,
                "response_headers": {"Content-Type": ctype, "X-Source": "ExoPlayer Disk Cache"},
                "preview": f"{ctype} ({total_size} bytes)",
                "saved_file": None,
                "saved_rel": None,
                "target_media_rel": target_rel,
                "source_files": [str(p) for _, p, _ in chunk_list],
            }
            if thumb_rel:
                entry["thumb_rel"] = thumb_rel
            if is_dm:
                entry["is_dm"] = True
            self._append_jsonl_unlocked(self.requests_log, entry)
            self._harvested_files[stream_key] = total_size
            count += 1
        return count

    def harvest_app_caches_once(
        self,
        app_data_root: Optional[Path] = None,
        refresh_acl: bool = False,
    ) -> int:
        root = app_data_root or Path(
            os.environ.get("WAYDROID_APP_DATA_DIR")
            or (Path.home() / ".local" / "share" / "waydroid" / "data" / "data")
        )
        if not root.exists():
            return 0
        if refresh_acl:
            self._refresh_app_cache_acls(root)

        harvested = 0
        with self._locked_session():
            self._harvested_files = self._load_harvest_state()
            try:
                pkg_dirs = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
            except OSError:
                return 0
            for pkg_dir in pkg_dirs:
                cache_dir = pkg_dir / "cache"
                has_db = (pkg_dir / "databases").is_dir()
                if not cache_dir.is_dir() and not has_db:
                    continue
                pkg = pkg_dir.name
                pkg_slug = sanitize_filename(pkg, max_len=30)
                dm_count, dm_media_map = self._harvest_direct_messages(pkg, pkg_slug, pkg_dir)
                harvested += dm_count
                if cache_dir.is_dir():
                    harvested += self._harvest_http_responses(pkg, pkg_slug, cache_dir)
                    harvested += self._harvest_image_caches(pkg, pkg_slug, cache_dir, pkg_dir=pkg_dir, dm_media_map=dm_media_map)
                    harvested += self._harvest_exoplayer_caches(pkg, pkg_slug, cache_dir, dm_media_map=dm_media_map)
            if harvested > 0 or not self._harvest_state_file.exists():
                self._save_harvest_state()
        return harvested

    def _harvester_loop(self, interval: float, refresh_acl: bool) -> None:
        while not self._harvester_stop.is_set():
            try:
                self.harvest_app_caches_once(refresh_acl=refresh_acl)
            except Exception:
                pass
            self._harvester_stop.wait(interval)

    def start_harvester(self, interval: float = 2.0, refresh_acl: bool = True) -> None:
        if self._harvester_started:
            return
        prev_stop = getattr(sys, "_waydroid_active_harvester_stop", None)
        if prev_stop is not None and prev_stop is not self._harvester_stop:
            try:
                prev_stop.set()
            except Exception:
                pass
        setattr(sys, "_waydroid_active_harvester_stop", self._harvester_stop)
        self._harvester_started = True
        thread = threading.Thread(
            target=self._harvester_loop,
            args=(interval, refresh_acl),
            name="waydroid-cache-harvester",
            daemon=True,
        )
        thread.start()

    def running(self) -> None:
        self.start_harvester(interval=2.0, refresh_acl=True)

    def done(self) -> None:
        self._harvester_stop.set()


if __name__ != "__main__" and "mitmproxy" in sys.modules:
    addons = [WaydroidDevToolsCapture()]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="devtools_capture_addon",
        description="Waydroid DevTools capture addon and Android app cache harvester",
    )
    parser.add_argument(
        "--harvest-once",
        action="store_true",
        help="Harvest decrypted media and JSON caches once from Android app data into capture-dir",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=None,
        help="Capture directory path (default: $WAYDROID_CAPTURE_DIR or ~/Waydroid/captures/latest)",
    )
    parser.add_argument(
        "--app-data-dir",
        type=Path,
        default=None,
        help="Android /data/data root (default: ~/.local/share/waydroid/data/data)",
    )
    parser.add_argument(
        "--refresh-acl",
        action="store_true",
        help="Run non-interactive setfacl before scanning caches",
    )
    args = parser.parse_args()

    default_dir = Path(
        os.environ.get("WAYDROID_CAPTURE_DIR")
        or (Path.home() / "Waydroid" / "captures" / "latest")
    ).resolve()
    addon = WaydroidDevToolsCapture(capture_dir=(args.capture_dir or default_dir))
    if args.harvest_once:
        n = addon.harvest_app_caches_once(app_data_root=args.app_data_dir, refresh_acl=args.refresh_acl)
        print(f"Harvested {n} new cache item(s) into {addon.capture_dir}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

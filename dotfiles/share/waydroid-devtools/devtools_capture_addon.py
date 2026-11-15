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
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Iterator, Optional
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
            raw_dir = Path(capture_dir)
        elif env_dir:
            raw_dir = Path(env_dir)
        else:
            ts = datetime.now().strftime("session-%Y%m%d-%H%M%S")
            raw_dir = Path.home() / "Waydroid" / "captures" / ts
        self.capture_dir = raw_dir.expanduser().resolve()

        self.messages_dir = self.capture_dir / "messages"
        self.media_dir = self.capture_dir / "media"
        self.requests_log = self.capture_dir / "requests.jsonl"
        self.ws_log = self.capture_dir / "websocket_messages.jsonl"
        self._harvest_state_file = self.capture_dir / ".harvest_state.json"
        self._lock_file = self.capture_dir / ".capture.lock"

        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.messages_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self._update_latest_symlink()

        self._lock = threading.Lock()
        self._seq = self._read_max_seq()
        self._harvested_files: Dict[str, int] = self._load_harvest_state()
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

    def _load_harvest_state(self) -> Dict[str, int]:
        if not self._harvest_state_file.exists():
            return {}
        try:
            data = json.loads(self._harvest_state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): int(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save_harvest_state(self) -> None:
        tmp = self._harvest_state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._harvested_files, indent=2), encoding="utf-8")
        tmp.replace(self._harvest_state_file)

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
            cache_targets: list[str] = []
            for pkg_dir in app_data_root.iterdir():
                if not pkg_dir.name or pkg_dir.name.startswith("."):
                    continue
                if "instagram" in pkg_dir.name or (pkg_dir / "cache").exists():
                    cache_targets.append(str(pkg_dir))
                    cache_dir = pkg_dir / "cache"
                    if cache_dir.exists():
                        for sub in ("http_responses", "images.stash", "ExoPlayerCacheDir", "image_manager_disk_cache", "original_images"):
                            sub_path = cache_dir / sub
                            if sub_path.exists():
                                cache_targets.append(str(sub_path))
            if cache_targets:
                subprocess.run(
                    ["sudo", "-n", "setfacl", "-m", acl_spec, *cache_targets],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
                deep_targets = [
                    p for p in cache_targets
                    if Path(p).name in ("http_responses", "images.stash", "ExoPlayerCacheDir", "image_manager_disk_cache", "original_images")
                ]
                if deep_targets:
                    subprocess.run(
                        ["sudo", "-n", "setfacl", "-R", "-m", acl_spec, *deep_targets],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=8,
                        check=False,
                    )
        except Exception:
            pass

    def _harvest_http_responses(self, pkg: str, pkg_slug: str, cache_dir: Path) -> int:
        http_dir = cache_dir / "http_responses"
        if not http_dir.is_dir():
            return 0
        count = 0
        for body_path in sorted(http_dir.iterdir()):
            name = body_path.name
            if not name.endswith("-body_gzip.clean") or "-copy" in name:
                continue
            prefix = name[: -len("-body_gzip.clean")]
            state_key = f"http:{pkg}:{prefix}"
            try:
                st = body_path.stat()
                if st.st_size <= 0:
                    continue
                marker = int(st.st_mtime_ns)
                if self._harvested_files.get(state_key) == marker:
                    continue
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
            self._harvested_files[state_key] = marker
            count += 1
        return count

    def _harvest_image_caches(self, pkg: str, pkg_slug: str, cache_dir: Path) -> int:
        count = 0
        subdirs = (
            cache_dir / "images.stash" / "clean",
            cache_dir / "image_manager_disk_cache",
            cache_dir / "original_images",
        )
        for sub in subdirs:
            if not sub.is_dir():
                continue
            try:
                candidates = sorted(p for p in sub.rglob("*") if p.is_file())
            except OSError:
                continue
            for img_path in candidates:
                rel = str(img_path.relative_to(cache_dir))
                state_key = f"img:{pkg}:{rel}"
                try:
                    raw = img_path.read_bytes()
                except OSError:
                    continue
                if not raw:
                    continue
                if self._harvested_files.get(state_key) == len(raw):
                    continue
                magic = self._detect_image_magic(raw[:16])
                if magic is None:
                    continue
                mime_type, ext = magic
                seq = self._next_seq_unlocked()
                short_name = sanitize_filename(img_path.stem or "image", max_len=36)
                dest = self.media_dir / f"{seq:05d}_{pkg_slug}_{short_name}{ext}"
                dest.write_bytes(raw)
                url = f"https://{pkg}.cache/{rel}"
                self._append_jsonl_unlocked(
                    self.requests_log,
                    {
                        "seq": seq,
                        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                        "method": "GET",
                        "url": url,
                        "host": f"{pkg} [App Cache]",
                        "path": f"/{rel}",
                        "status_code": 200,
                        "resource_type": "Img",
                        "content_type": mime_type,
                        "req_size": 0,
                        "resp_size": len(raw),
                        "duration_ms": 0.0,
                        "request_headers": {"Source": rel},
                        "response_headers": {"Content-Type": mime_type, "X-Source": "Android Disk Cache"},
                        "preview": f"{mime_type} ({len(raw)} bytes)",
                        "saved_file": str(dest),
                        "saved_rel": str(dest.relative_to(self.capture_dir)),
                    },
                )
                self._harvested_files[state_key] = len(raw)
                count += 1
        return count

    def _harvest_exoplayer_caches(self, pkg: str, pkg_slug: str, cache_dir: Path) -> int:
        exo_root = cache_dir / "ExoPlayerCacheDir" / "videocache"
        if not exo_root.is_dir():
            return 0
        streams: Dict[str, list[tuple[int, Path]]] = {}
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
            streams.setdefault(stream_prefix, []).append((offset, exo_path))

        count = 0
        for stream_prefix, chunk_list in sorted(streams.items()):
            chunk_list.sort(key=lambda item: item[0])
            if not chunk_list or chunk_list[0][0] != 0:
                continue
            try:
                first_bytes = chunk_list[0][1].read_bytes()
            except OSError:
                continue
            if len(first_bytes) < 8 or first_bytes[4:8] != b"ftyp":
                continue

            parts: list[bytes] = [first_bytes]
            failed = False
            for _, p in chunk_list[1:]:
                try:
                    parts.append(p.read_bytes())
                except OSError:
                    failed = True
                    break
            if failed:
                continue

            full_bytes = b"".join(parts)
            stream_key = f"exo:{pkg}:{stream_prefix}"
            prev_len = self._harvested_files.get(stream_key, 0)
            if len(full_bytes) <= prev_len:
                continue

            is_audio = "a.-1." in stream_prefix
            ctype = "audio/mp4" if is_audio else "video/mp4"
            tag = "audio" if is_audio else "video"
            short_id = sanitize_filename(stream_prefix.split(".")[0], max_len=36)
            seq = self._next_seq_unlocked()
            dest = self.media_dir / f"{seq:05d}_{pkg_slug}_{short_id}_{tag}.mp4"
            dest.write_bytes(full_bytes)
            url = f"https://{pkg}.cache/videocache/{short_id}_{tag}.mp4"
            self._append_jsonl_unlocked(
                self.requests_log,
                {
                    "seq": seq,
                    "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "method": "GET",
                    "url": url,
                    "host": f"{pkg} [App Cache]",
                    "path": f"/videocache/{short_id}_{tag}.mp4 ({len(chunk_list)} chunk(s))",
                    "status_code": 200,
                    "resource_type": "Media",
                    "content_type": ctype,
                    "req_size": 0,
                    "resp_size": len(full_bytes),
                    "duration_ms": 0.0,
                    "request_headers": {"Chunks": str(len(chunk_list)), "Stream": stream_prefix[:64]},
                    "response_headers": {"Content-Type": ctype, "X-Source": "ExoPlayer Disk Cache"},
                    "preview": f"{ctype} ({len(full_bytes)} bytes)",
                    "saved_file": str(dest),
                    "saved_rel": str(dest.relative_to(self.capture_dir)),
                },
            )
            self._harvested_files[stream_key] = len(full_bytes)
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
                if not cache_dir.is_dir():
                    continue
                pkg = pkg_dir.name
                pkg_slug = sanitize_filename(pkg, max_len=30)
                harvested += self._harvest_http_responses(pkg, pkg_slug, cache_dir)
                harvested += self._harvest_image_caches(pkg, pkg_slug, cache_dir)
                harvested += self._harvest_exoplayer_caches(pkg, pkg_slug, cache_dir)
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

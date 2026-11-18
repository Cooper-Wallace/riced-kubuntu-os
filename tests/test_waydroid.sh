#!/usr/bin/env bash
# ==============================================================================
# test_waydroid.sh - Automated & Guarded-Failure Tests for RKO Waydroid Stack
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
    echo "PASS: $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
    echo "FAIL: $1" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

assert_zero() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        pass "${desc}"
    else
        fail "${desc} (expected exit 0, got $?)"
    fi
}

assert_nonzero() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        fail "${desc} (expected non-zero exit code, got 0)"
    else
        pass "${desc}"
    fi
}

echo "=== Running RKO Waydroid Test Suite ==="

# 1. Dry-run checks on bootstrap.sh and Stage 05
assert_zero "bootstrap.sh --dry-run exits 0" bash "${REPO_ROOT}/bootstrap.sh" --dry-run
assert_zero "scripts/05-waydroid.sh --dry-run exits 0" bash "${REPO_ROOT}/scripts/05-waydroid.sh" --dry-run

# 2. waydroid-stats JSON schema validation
json_out=""
if json_out="$(python3 "${REPO_ROOT}/dotfiles/bin/waydroid-stats" --once --json)"; then
    if python3 -c '
import json, sys
data = json.loads(sys.stdin.read())
required = ("timestamp", "container", "network", "connections", "downloads", "captured_requests")
missing = [k for k in required if k not in data]
assert not missing, f"Missing keys: {missing}"
assert isinstance(data["container"], dict)
assert isinstance(data["network"], dict)
assert isinstance(data["connections"], list)
assert isinstance(data["downloads"], list)
assert isinstance(data["captured_requests"], list)
' <<< "${json_out}"; then
        pass "waydroid-stats --once --json produces valid JSON with required schema keys"
    else
        fail "waydroid-stats --once --json failed schema validation"
    fi
else
    fail "waydroid-stats --once --json exited non-zero"
fi

# 3. waydroid-ctl & waydroid-devtools help and dry-run checks
assert_zero "waydroid-ctl --help exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" --help
assert_zero "waydroid-ctl --dry-run status exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" --dry-run status
assert_zero "waydroid-ctl --dry-run web exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" --dry-run web https://www.instagram.com
assert_zero "waydroid-ctl --dry-run listen exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" --dry-run listen
assert_zero "waydroid-devtools --help exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --help
assert_zero "waydroid-devtools --dry-run exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --dry-run
assert_zero "waydroid-netmon symlink resolves to waydroid-stats" test -L "${REPO_ROOT}/dotfiles/bin/waydroid-netmon"

# 4. devtools_capture_addon.py unit test (mock request/message/media/TLS/cache harvest/websocket persistence)
tmp_capture_dir="$(mktemp -d)"
tmp_mock_app_data="$(mktemp -d)"
if python3 - "${REPO_ROOT}/dotfiles/share/waydroid-devtools/devtools_capture_addon.py" "${tmp_capture_dir}" "${tmp_mock_app_data}" <<'PYEOF'
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

addon_file = Path(sys.argv[1])
cap_dir = Path(sys.argv[2])
mock_data_root = Path(sys.argv[3])
os.environ["WAYDROID_CAPTURE_DIR"] = str(cap_dir)

spec = importlib.util.spec_from_file_location("devtools_capture_addon", addon_file)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

addon = mod.WaydroidDevToolsCapture(capture_dir=cap_dir)

# Mock JSON API response
flow_api = SimpleNamespace(
    request=SimpleNamespace(
        pretty_url="https://api.example.test/v1/feed?limit=5",
        pretty_host="api.example.test",
        method="POST",
        headers={"Content-Type": "application/json"},
        content=b'{"cursor":"abc"}',
        timestamp_start=100.0,
    ),
    response=SimpleNamespace(
        status_code=200,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content=b'{"items":[1,2,3]}',
        timestamp_end=100.045,
    ),
)
addon.response(flow_api)

# Mock Image media response
flow_img = SimpleNamespace(
    request=SimpleNamespace(
        pretty_url="https://cdn.example.test/media/photo.jpg",
        pretty_host="cdn.example.test",
        method="GET",
        headers={},
        content=b"",
        timestamp_start=101.0,
    ),
    response=SimpleNamespace(
        status_code=200,
        headers={"Content-Type": "image/jpeg"},
        content=b"\xff\xd8\xff\xe0MOCKJPEG",
        timestamp_end=101.012,
    ),
)
addon.response(flow_img)

# Mock WebSocket message
flow_ws = SimpleNamespace(
    request=SimpleNamespace(
        pretty_url="wss://chat.example.test/ws",
        pretty_host="chat.example.test",
    ),
    websocket=SimpleNamespace(
        messages=[SimpleNamespace(from_client=False, is_text=True, content=b'{"dm":"hello"}')]
    ),
)
addon.websocket_message(flow_ws)

# Mock TLS certificate pinning failure & subsequent passthrough ClientHello
flow_tls_fail = SimpleNamespace(
    conn=SimpleNamespace(
        sni="i.instagram.com",
        alpn_offers=[b"h2", b"http/1.1"],
        error="unable to get local issuer certificate",
    ),
    context=SimpleNamespace(server=SimpleNamespace(address=("157.240.8.40", 443))),
)
addon.tls_failed_client(flow_tls_fail)

ch_data = SimpleNamespace(
    client_hello=SimpleNamespace(sni="i.instagram.com", alpn_protocols=[b"h2"]),
    context=SimpleNamespace(server=SimpleNamespace(address=("157.240.8.40", 443))),
    ignore_connection=False,
)
addon.tls_clienthello(ch_data)
assert ch_data.ignore_connection is True, "Expected ignore_connection=True for pinned SNI host"

import time

assert addon._is_pinned_host("instagram.fbne7-1.fna.fbcdn.net") is True, "Expected proactive CDN suffix pinning"
addon._last_passthrough_log["instagram.fbne7-1.fna.fbcdn.net:443"] = time.time()
ch_cdn = SimpleNamespace(
    client_hello=SimpleNamespace(sni="instagram.fbne7-1.fna.fbcdn.net", alpn_protocols=[b"h2"]),
    context=SimpleNamespace(server=SimpleNamespace(address=("157.240.8.41", 443))),
    ignore_connection=False,
)
addon.tls_clienthello(ch_cdn)
assert ch_cdn.ignore_connection is True, "Expected immediate passthrough for .fbcdn.net"

# Mock Android app disk caches (Instagram direct.db + http_responses + images.stash + ExoPlayer videocache)
import base64
import sqlite3

ig_root = mock_data_root / "com.instagram.android"
ig_cache = ig_root / "cache"
ig_db_dir = ig_root / "databases"
(ig_cache / "http_responses").mkdir(parents=True)
(ig_cache / "images.stash" / "clean").mkdir(parents=True)
(ig_cache / "ExoPlayerCacheDir" / "videocache" / "0").mkdir(parents=True)
ig_db_dir.mkdir(parents=True)

conn = sqlite3.connect(str(ig_db_dir / "direct.db"))
conn.execute("CREATE TABLE threads (_id INTEGER, thread_info BLOB)")
conn.execute("CREATE TABLE messages (_id INTEGER, user_id TEXT, server_item_id TEXT, thread_id TEXT, timestamp INTEGER, message_type TEXT, text TEXT, message BLOB)")
conn.execute(
    "INSERT INTO threads VALUES (1, ?)",
    (json.dumps({"recipients": [{"id": "7898", "username": "tester"}]}).encode("utf-8"),),
)
dm_msg_payload = {
    "item_id": "item_dm_1",
    "user_id": "7898",
    "item_type": "media",
    "is_disappearing": True,
    "ephemeral_view_timestamp_ms": 1794756781969,
    "media": {
        "id": "1165652832651531",
        "media_type": 1,
        "original_width": 864,
        "original_height": 1920,
        "image_versions2": {"candidates": [{"url": "https://cdn.example.test/dm.jpg", "width": 864, "height": 1920}]},
    },
}
dm_vid_payload = {
    "item_id": "item_dm_vid",
    "user_id": "7898",
    "item_type": "raven_media",
    "is_disappearing": True,
    "visual_media": {
        "media": {
            "id": "9876543210987",
            "media_type": 2,
            "original_width": 540,
            "original_height": 960,
            "image_versions2": {"candidates": [{"url": "https://cdn.example.test/vid_poster.jpg", "width": 540, "height": 960}]},
            "video_dash_manifest": (
                '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Period><AdaptationSet contentType="video">'
                '<Representation bandwidth="400000" width="360" height="640" mimeType="video/mp4">'
                '<BaseURL>https://cdn.example.test/v360.mp4</BaseURL></Representation>'
                '<Representation bandwidth="2400000" width="720" height="1280" mimeType="video/mp4">'
                '<BaseURL>https://cdn.example.test/v720.mp4</BaseURL></Representation>'
                '</AdaptationSet></Period></MPD>'
            ),
        }
    },
}
conn.execute(
    "INSERT INTO messages VALUES (1, '7898', 'item_dm_1', 'thread_1', 1794714898623779, 'media', NULL, ?)",
    (json.dumps(dm_msg_payload).encode("utf-8"),),
)
conn.execute(
    "INSERT INTO messages VALUES (2, '7898', 'item_dm_vid', 'thread_1', 1794714899000000, 'raven_media', NULL, ?)",
    (json.dumps(dm_vid_payload).encode("utf-8"),),
)
conn.commit()
conn.close()

(ig_cache / "http_responses" / "abcd1234-resp_info_gzip.clean").write_bytes(
    gzip.compress(json.dumps({"status_code": 200, "headers": [{"name": "x-test", "value": "1"}]}).encode("utf-8"))
)
(ig_cache / "http_responses" / "abcd1234-body_gzip.clean").write_bytes(
    gzip.compress(b'{"tray":[]}')
)
dm_b64 = base64.b64encode(b"1165652832651531").decode("ascii")
vid_b64 = base64.b64encode(b"9876543210987").decode("ascii")
(ig_cache / "images.stash" / "clean" / f"{dm_b64}.2-ccb7-5").write_bytes(b"\xff\xd8\xff\xe0MOCK_CACHE_JPEG")
(ig_cache / "images.stash" / "clean" / f"{vid_b64}.2-ccb7-5").write_bytes(b"\xff\xd8\xff\xe0MOCK_POSTER_JPEG")
(ig_cache / "ExoPlayerCacheDir" / "videocache" / "0" / "9876543210987.null.111v.-1.hash.0.999.v2.exo").write_bytes(
    b"\x00\x00\x00\x18ftypmp42MOCK_DM_VIDEO"
)
(ig_cache / "ExoPlayerCacheDir" / "videocache" / "0" / "9876543210987.null.111a.-1.hash.0.999.v2.exo").write_bytes(
    b"\x00\x00\x00\x18ftypmp42MOCK_DM_AUDIO"
)
(ig_cache / "ExoPlayerCacheDir" / "videocache" / "0" / "12345_67890.null.111v.-1.hash.0.999.v2.exo").write_bytes(
    b"\x00\x00\x00\x18ftypmp42MOCK_MP4_VIDEO"
)
harvested = addon.harvest_app_caches_once(app_data_root=mock_data_root)
assert harvested == 4, f"Expected 4 harvested items (2 DM media + 1 http + 1 video), got {harvested}"

reqs = [json.loads(line) for line in (cap_dir / "requests.jsonl").read_text().splitlines() if line.strip()]
assert len(reqs) == 9, f"Expected 9 requests, got {len(reqs)}"
assert reqs[0]["resource_type"] == "Fetch/XHR"
assert reqs[1]["resource_type"] == "Img" and reqs[1]["saved_rel"] is None and reqs[1].get("thumb_rel")
assert reqs[2]["resource_type"] == "WS"
assert reqs[3]["resource_type"] == "TLS" and reqs[3]["status_code"] == 495
assert reqs[4]["resource_type"] == "TLS" and reqs[4]["status_code"] == 200
assert reqs[5]["method"] == "DM" and reqs[5]["resource_type"] == "Img" and reqs[5]["saved_rel"] is None
assert reqs[5]["target_media_rel"].endswith(".jpg") and reqs[5]["msg_rel"].startswith("messages/")
assert reqs[6]["method"] == "DM" and reqs[6]["resource_type"] == "Media" and reqs[6]["saved_rel"] is None
assert reqs[6]["target_media_rel"].endswith(".mp4") and reqs[6].get("thumb_rel") and reqs[6].get("audio_source_files")
assert reqs[6].get("dash_video_url") == "https://cdn.example.test/v720.mp4"
assert reqs[7]["resource_type"] == "Fetch/XHR"
assert reqs[8]["resource_type"] == "Media" and reqs[8]["saved_rel"] is None
assert len(list((cap_dir / "messages").glob("*.json"))) == 6
assert len(list((cap_dir / "media").glob("*"))) == 0, "Expected 0 full media files saved before UI selection"
assert len(list((cap_dir / "thumbs").glob("*.jpg"))) >= 3
assert (cap_dir / "websocket_messages.jsonl").exists()

# Guarded failure: untrusted CDN URLs must be rejected before network fetch
assert mod.WaydroidDevToolsCapture._is_trusted_cdn_url("https://evil.test/video.mp4") is False
assert mod.WaydroidDevToolsCapture._download_cdn_bytes("http://instagram.fbne7-1.fna.fbcdn.net/video.mp4") == b""

# Live harvester settle delay defers fresh DM images.stash thumbnails so direct.db / ExoPlayer land first
dm_wait_b64 = base64.b64encode(b"5555666677778888").decode("ascii")
wait_img = ig_cache / "images.stash" / "clean" / f"{dm_wait_b64}.2-ccb7-5"
wait_img.write_bytes(b"\xff\xd8\xff\xe0MOCK_FRESH_DM_COVER")
addon._harvester_started = True
try:
    deferred_count = addon.harvest_app_caches_once(app_data_root=mock_data_root)
finally:
    addon._harvester_started = False
assert deferred_count == 0, f"Expected fresh DM thumbnail to be deferred in live mode, got {deferred_count}"
PYEOF
then
    pass "devtools_capture_addon.py saves requests.jsonl, messages/*.json, thumbnails, DM image/video media, TLS pinning events, and defers full media until selected"
else
    fail "devtools_capture_addon.py unit test failed"
fi

# 4a. ACL mask preservation, Codec2, launcher isolation & performance assertions
if grep -q 'u:\${USER}:rX,m::rwx' "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" \
   && grep -q 'u:\${TARGET_USER}:rX,m::rwx' "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" \
   && grep -q '"debug.stagefright.ccodec": "4"' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q '"persist.waydroid.multi_windows": "false"' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q '"dalvik.vm.heapsize": "512m"' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q '99-rko-waydroid-inotify.conf' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q 'waydroid upgrade -o' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q 'waydroidplatform' "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" \
   && grep -q '90-waydroid-audio.conf' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q 'waydroid-hide-apps.path' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q 'waydroid-devtools.desktop' "${REPO_ROOT}/scripts/05-waydroid.sh" \
   && grep -q 'waydroid-devtools.desktop' "${REPO_ROOT}/scripts/03-dotfiles.sh"; then
    pass "waydroid scripts preserve ACL masks, configure Codec2/inotify/prop-sync/audio, and isolate launcher entries"
else
    fail "waydroid scripts missing ACL mask, Codec2/inotify/prop-sync/audio, or launcher isolation configuration"
fi

# 4c. waydroid-ctl hide-apps & new devtools flags + launcher entry preservation tests
assert_zero "waydroid-ctl --dry-run hide-apps exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" --dry-run hide-apps
assert_zero "waydroid-devtools --dry-run --auto-save-ephemeral exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --dry-run --auto-save-ephemeral
assert_zero "waydroid-devtools --dry-run --web exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --dry-run --web

tmp_xdg_data="$(mktemp -d)"
mkdir -p "${tmp_xdg_data}/applications"
cat > "${tmp_xdg_data}/applications/waydroid.com.aurora.store.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Aurora Store
Exec=waydroid app launch com.aurora.store
EOF
sed "s|@BIN_DIR@|/usr/local/bin|g" "${REPO_ROOT}/dotfiles/share/waydroid-devtools/waydroid-devtools.desktop.in" > "${tmp_xdg_data}/applications/waydroid-devtools.desktop"
if XDG_DATA_HOME="${tmp_xdg_data}" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" hide-apps >/dev/null 2>&1 \
   && grep -qx "NoDisplay=true" "${tmp_xdg_data}/applications/waydroid.com.aurora.store.desktop" \
   && ! grep -q "NoDisplay=true" "${tmp_xdg_data}/applications/waydroid-devtools.desktop" \
   && grep -q "^Exec=/usr/local/bin/waydroid-devtools --auto-save-ephemeral" "${tmp_xdg_data}/applications/waydroid-devtools.desktop"; then
    pass "waydroid-ctl hide-apps hides Android app entries while preserving waydroid-devtools.desktop"
else
    fail "waydroid-ctl hide-apps failed on Android entries or altered waydroid-devtools.desktop"
fi
rm -rf "${tmp_xdg_data}"

# 4b. devtools_web_server.py live HTTP endpoint, on-demand save, & path-traversal guard test
if python3 - "${REPO_ROOT}/dotfiles/share/waydroid-devtools/devtools_web_server.py" "${tmp_capture_dir}" <<'PYEOF'
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

server_script = sys.argv[1]
cap_dir = Path(sys.argv[2])
proc_env = {**os.environ, "WAYDROID_APP_DATA_DIR": str(cap_dir / "_empty_data")}

proc = subprocess.Popen(
    [sys.executable, server_script, "--host", "127.0.0.1", "--port", "0", "--capture-dir", str(cap_dir)],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=proc_env,
)
try:
    line = proc.stdout.readline().strip()
    m = re.search(r"http://127\.0\.0\.1:(\d+)", line)
    assert m, f"Unexpected server banner: {line!r}"
    base = f"http://127.0.0.1:{m.group(1)}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    with opener.open(f"{base}/", timeout=3) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "Waydroid DevTools" in html

    with opener.open(f"{base}/api/requests", timeout=3) as resp:
        assert resp.status == 200
        payload = json.loads(resp.read().decode("utf-8"))
        assert len(payload["requests"]) == 9
        assert len(payload["websockets"]) == 1

    msg_name = sorted((cap_dir / "messages").glob("*.json"))[0].name
    with opener.open(f"{base}/api/message/{msg_name}", timeout=3) as resp:
        assert resp.status == 200
        msg = json.loads(resp.read().decode("utf-8"))
        assert msg["response_body"] == {"items": [1, 2, 3]}

    thumb_name = sorted((cap_dir / "thumbs").glob("*.jpg"))[0].name
    with opener.open(f"{base}/files/thumbs/{thumb_name}", timeout=3) as resp:
        assert resp.status == 200
        assert resp.read().startswith(b"\xff\xd8\xff\xe0MOCK")

    # Stream before persist
    with opener.open(f"{base}/api/stream/2", timeout=3) as resp:
        assert resp.status == 200
        assert resp.read().startswith(b"\xff\xd8\xff\xe0MOCKJPEG")

    # Separate /saved view and /api/config ephemeral auto-save toggle
    with opener.open(f"{base}/saved", timeout=3) as resp:
        assert resp.status == 200
        assert "Saved Ephemeral DM Media" in resp.read().decode("utf-8")

    with opener.open(f"{base}/api/config", timeout=3) as resp:
        cfg_data = json.loads(resp.read().decode("utf-8"))
        assert cfg_data["config"]["auto_save_ephemeral"] is False

    # Guarded failure: non-boolean auto_save_ephemeral must return 400
    try:
        bad_cfg = urllib.request.Request(
            f"{base}/api/config",
            data=json.dumps({"auto_save_ephemeral": "yes"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener.open(bad_cfg, timeout=3)
        raise AssertionError("Expected 400 Bad Request for non-boolean auto_save_ephemeral")
    except urllib.error.HTTPError as err:
        assert err.code == 400, f"Expected 400, got {err.code}"

    # Toggling auto_save_ephemeral ON saves only ephemeral DM rows (seq 6 & 7), not seq 2 & 9
    req_cfg = urllib.request.Request(
        f"{base}/api/config",
        data=json.dumps({"auto_save_ephemeral": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(req_cfg, timeout=5) as resp:
        cfg_resp = json.loads(resp.read().decode("utf-8"))
        assert cfg_resp["ok"] is True and cfg_resp["config"]["auto_save_ephemeral"] is True

    with opener.open(f"{base}/api/requests?saved_ephemeral=1", timeout=3) as resp:
        eph_payload = json.loads(resp.read().decode("utf-8"))
        assert len(eph_payload["requests"]) == 2, f"Expected 2 auto-saved ephemeral DM items, got {len(eph_payload['requests'])}"
        assert eph_payload["saved_ephemeral_count"] == 2
        assert {r["seq"] for r in eph_payload["requests"]} == {6, 7}
    assert len(list((cap_dir / "media").glob("*"))) == 2, "Expected non-ephemeral media (2 & 9) to remain unsaved"

    # Standalone PyQt6 desktop app client test (syntax check everywhere; widget test when PyQt6 is installed)
    app_script = Path(server_script).with_name("devtools_app.py")
    if app_script.is_file():
        import py_compile

        py_compile.compile(str(app_script), doraise=True)
        has_pyqt6 = subprocess.run(
            [sys.executable, "-c", "import PyQt6.QtWidgets"],
            capture_output=True,
            timeout=5,
        ).returncode == 0
        if has_pyqt6:
            app_check = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import importlib.util, sys; "
                        "from PyQt6.QtWidgets import QApplication; "
                        "spec = importlib.util.spec_from_file_location('devtools_app', sys.argv[1]); "
                        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
                        "app = QApplication([]); "
                        "win = mod.DevToolsMainWindow(mod.DevToolsApiClient(sys.argv[2]), open_saved=True); "
                        "assert win.chk_auto_eph.isChecked() is True; "
                        "assert win.saved_window.item_list.count() == 2; "
                        "win.saved_window.close(); win.close(); app.quit()"
                    ),
                    str(app_script),
                    base,
                ],
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert app_check.returncode == 0, f"devtools_app.py check failed: {app_check.stderr}"

    # Persist remaining non-ephemeral image & video on demand via POST /api/save/<seq>
    for seq_id, ext in ((2, ".jpg"), (6, ".jpg"), (7, ".mp4"), (9, ".mp4")):
        req_save = urllib.request.Request(f"{base}/api/save/{seq_id}", data=b"{}", method="POST")
        with opener.open(req_save, timeout=3) as resp:
            assert resp.status == 200
            save_data = json.loads(resp.read().decode("utf-8"))
            assert save_data["ok"] is True
            assert save_data["request"]["saved_rel"].startswith("media/")
            assert save_data["request"]["saved_rel"].endswith(ext)

    media_name = sorted((cap_dir / "media").glob("*.jpg"))[0].name
    with opener.open(f"{base}/files/media/{media_name}", timeout=3) as resp:
        assert resp.status == 200
        assert resp.read().startswith(b"\xff\xd8\xff\xe0MOCKJPEG")

    req_range = urllib.request.Request(f"{base}/files/media/{media_name}", headers={"Range": "bytes=0-3"})
    with opener.open(req_range, timeout=3) as resp:
        assert resp.status == 206
        assert resp.headers.get("Accept-Ranges") == "bytes"
        assert (resp.headers.get("Content-Range") or "").startswith("bytes 0-3/")
        assert resp.read() == b"\xff\xd8\xff\xe0"

    # Guarded failure: out-of-bounds byte range must return 416
    try:
        req_oob = urllib.request.Request(f"{base}/files/media/{media_name}", headers={"Range": "bytes=999999-"})
        opener.open(req_oob, timeout=3)
        raise AssertionError("Expected 416 Range Not Satisfiable for out-of-bounds Range")
    except urllib.error.HTTPError as err:
        assert err.code == 416, f"Expected 416, got {err.code}"

    # Guarded failure: path traversal / disallowed root file must return 403
    try:
        opener.open(f"{base}/files/requests.jsonl", timeout=3)
        raise AssertionError("Expected 403 Forbidden for /files/requests.jsonl")
    except urllib.error.HTTPError as err:
        assert err.code == 403, f"Expected 403, got {err.code}"

    # Guarded failure: unknown sequence id on save must return 404
    try:
        req_missing = urllib.request.Request(f"{base}/api/save/999999", data=b"{}", method="POST")
        opener.open(req_missing, timeout=3)
        raise AssertionError("Expected 404 Not Found for /api/save/999999")
    except urllib.error.HTTPError as err:
        assert err.code == 404, f"Expected 404, got {err.code}"
finally:
    proc.terminate()
    proc.wait(timeout=3)
PYEOF
then
    pass "devtools_web_server.py serves UI, thumbnails, streams, saves media on selection, and guards paths"
else
    fail "devtools_web_server.py HTTP test failed"
fi
rm -rf "${tmp_capture_dir}" "${tmp_mock_app_data}"

# 5. Guarded failure / safe degrade coverage
assert_nonzero "bootstrap.sh --invalid-flag exits non-zero" bash "${REPO_ROOT}/bootstrap.sh" --invalid-flag
assert_nonzero "waydroid-ctl invalid-subcommand exits non-zero" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" invalid-subcommand
assert_nonzero "waydroid-stats --invalid-flag exits non-zero" python3 "${REPO_ROOT}/dotfiles/bin/waydroid-stats" --invalid-flag
assert_nonzero "waydroid-devtools --invalid-flag exits non-zero" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --invalid-flag

echo "=== Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi

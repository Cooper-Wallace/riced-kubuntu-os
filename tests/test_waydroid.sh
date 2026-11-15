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
assert_zero "waydroid-ctl --dry-run listen exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" --dry-run listen
assert_zero "waydroid-devtools --help exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --help
assert_zero "waydroid-devtools --dry-run exits 0" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --dry-run
assert_zero "waydroid-netmon symlink resolves to waydroid-stats" test -L "${REPO_ROOT}/dotfiles/bin/waydroid-netmon"

# 4. devtools_capture_addon.py unit test (mock request/message/media/websocket persistence)
tmp_capture_dir="$(mktemp -d)"
if python3 - "${REPO_ROOT}/dotfiles/share/waydroid-devtools/devtools_capture_addon.py" "${tmp_capture_dir}" <<'PYEOF'
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

addon_file = Path(sys.argv[1])
cap_dir = Path(sys.argv[2])
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

reqs = [json.loads(line) for line in (cap_dir / "requests.jsonl").read_text().splitlines() if line.strip()]
assert len(reqs) == 3, f"Expected 3 requests, got {len(reqs)}"
assert reqs[0]["resource_type"] == "Fetch/XHR"
assert reqs[1]["resource_type"] == "Img"
assert reqs[2]["resource_type"] == "WS"
assert len(list((cap_dir / "messages").glob("*.json"))) == 1
assert len(list((cap_dir / "media").glob("*.jpg"))) == 1
assert (cap_dir / "websocket_messages.jsonl").exists()
PYEOF
then
    pass "devtools_capture_addon.py saves requests.jsonl, messages/*.json, media/*, and websocket_messages.jsonl"
else
    fail "devtools_capture_addon.py unit test failed"
fi
rm -rf "${tmp_capture_dir}"

# 5. Guarded failure / safe degrade coverage
assert_nonzero "bootstrap.sh --invalid-flag exits non-zero" bash "${REPO_ROOT}/bootstrap.sh" --invalid-flag
assert_nonzero "waydroid-ctl invalid-subcommand exits non-zero" bash "${REPO_ROOT}/dotfiles/bin/waydroid-ctl" invalid-subcommand
assert_nonzero "waydroid-stats --invalid-flag exits non-zero" python3 "${REPO_ROOT}/dotfiles/bin/waydroid-stats" --invalid-flag
assert_nonzero "waydroid-devtools --invalid-flag exits non-zero" bash "${REPO_ROOT}/dotfiles/bin/waydroid-devtools" --invalid-flag

echo "=== Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi

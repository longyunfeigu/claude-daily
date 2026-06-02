#!/usr/bin/env bash
# Quick CI-suitable smoke test: prepare → emit → upload using minimal fixture.
# Exit 0 on success; non-zero with diagnostic on failure.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
SKILL_DIR=$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)
FIXTURE="${SKILL_DIR}/tests/fixtures/sample_minimal"
TMP=$(mktemp -d)
SERVER_PID=""

cleanup() {
  [[ -n "${SERVER_PID}" ]] && kill "${SERVER_PID}" 2>/dev/null || true
  rm -rf "${TMP}"
}
trap cleanup EXIT

# Mock server: echo back outcome=ok
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
python3 - "${PORT}" <<'PYEOF' &
import sys
import http.server, json, socketserver
PORT = int(sys.argv[1])
class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"outcome":"ok","request_id":"req_smoke"}).encode())
    def log_message(*a, **k): pass
with ReusableTCPServer(("127.0.0.1", PORT), H) as httpd:
    httpd.serve_forever()
PYEOF
SERVER_PID=$!

# Wait for port to be ready (max 2s)
for _ in $(seq 1 20); do
  python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.1); sys.exit(0 if s.connect_ex(('127.0.0.1',${PORT}))==0 else 1)" && break
  sleep 0.1
done

# Config
cat > "${TMP}/config.json" <<EOF
{
  "member_id": "wanhua.gu",
  "endpoint_base": "http://127.0.0.1:${PORT}",
  "endpoint_paths": {"daily_report":"/api/v1/ingest/daily-reports","session_card":"/api/v1/ingest/session-cards"},
  "outbox_dir": "${TMP}/outbox",
  "projects_root": "${FIXTURE}/projects"
}
EOF

# Stage 1
python3 "${SCRIPT_DIR}/prepare.py" --config "${TMP}/config.json" --date 2026-05-10

# Stage 2 — copy fixture LLM output (simulate Claude Code)
OUTBOX="${TMP}/outbox/2026-05-10/wanhua.gu"
cp "${FIXTURE}/llm_output/_output.personal.md" "${OUTBOX}/"
cp "${FIXTURE}/llm_output/_output.team.md" "${OUTBOX}/"
cp "${FIXTURE}/llm_output/_output.boss.md" "${OUTBOX}/"
cp "${FIXTURE}/llm_output/_session_meta.json" "${OUTBOX}/"

# Stage 3
python3 "${SCRIPT_DIR}/emit.py" --config "${TMP}/config.json" --date 2026-05-10

# Stage 4
python3 "${SCRIPT_DIR}/upload.py" --config "${TMP}/config.json" --date 2026-05-10 --backoff-seconds 0,0,0

# Verify
test -f "${OUTBOX}/daily_report.personal.ack.json"
test -f "${OUTBOX}/daily_report.team.ack.json"
test -f "${OUTBOX}/daily_report.boss.ack.json"
test -f "${OUTBOX}/session_card.f66e2252.ack.json"

echo "smoke_quick OK"

#!/usr/bin/env sh
set -e

export CAVEMAN_MODE="${CAVEMAN_MODE:-compress}"
export CAVEMAN_LISTEN="${CAVEMAN_LISTEN:-127.0.0.1:8788}"
export CAVEMAN_UPSTREAM_NAME="${CAVEMAN_UPSTREAM_NAME:-openrouter}"
export CAVEMAN_UPSTREAM_BASE_URL="${CAVEMAN_UPSTREAM_BASE_URL:-https://openrouter.ai/api/v1}"
export CAVEMAN_API_KEY_ENV="${CAVEMAN_API_KEY_ENV:-OPENROUTER_API_KEY}"

python3 - <<'EOF'
import os
src = open("/etc/caveman/caveman.yaml.tmpl").read()
open("/etc/caveman/caveman.yaml","w").write(os.path.expandvars(src))
print("rendered /etc/caveman/caveman.yaml")
EOF

/usr/local/bin/caveman-proxy &
PROXY_PID=$!
echo "caveman-proxy started pid=$PROXY_PID"

python3 /usr/local/bin/wrapper.py &
WRAP_PID=$!
echo "wrapper started pid=$WRAP_PID"

trap "kill $WRAP_PID $PROXY_PID 2>/dev/null" TERM INT
wait

#!/usr/bin/env sh
set -e

# 1) Render caveman.yaml from env (python expandvars; safe for missing vars)
python3 - <<'EOF'
import os
src = open("/etc/caveman/caveman.yaml.tmpl").read()
out = os.path.expandvars(src)
open("/etc/caveman/caveman.yaml","w").write(out)
print("rendered /etc/caveman/caveman.yaml")
EOF

# 2) Start caveman-proxy (compressor) on loopback
/usr/local/bin/caveman-proxy &
PROXY_PID=$!
echo "caveman-proxy started pid=$PROXY_PID"

# 3) Start public wrapper on 0.0.0.0:8787 (/models + forwards to proxy)
python3 /usr/local/bin/wrapper.py &
WRAP_PID=$!
echo "wrapper started pid=$WRAP_PID"

# 4) Die together on shutdown
trap "kill $WRAP_PID $PROXY_PID 2>/dev/null" TERM INT
wait

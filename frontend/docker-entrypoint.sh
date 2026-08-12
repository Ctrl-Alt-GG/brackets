#!/bin/sh
set -eu

cat <<EOF >/usr/share/nginx/html/runtime-config.js
window.__BRACKET_RUNTIME_CONFIG__ = {
  apiBaseUrl: "${API_BASE_URL}"
};
EOF

exec "$@"
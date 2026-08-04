#!/bin/sh
set -eu
# Ensure upload volume is writable by the non-root app user (uid 10001).
# Named volumes created by earlier root-running images may still be root-owned.
if [ "$(id -u)" = "0" ]; then
  mkdir -p /var/pii-uploads /var/pii-uploads/ocr-work
  chown -R app:app /var/pii-uploads || true
  exec gosu app "$@"
fi
exec "$@"

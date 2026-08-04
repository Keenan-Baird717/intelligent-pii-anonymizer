#!/bin/sh
set -eu
# Ensure upload volume is writable by the non-root app user (uid 10001).
# Named volumes created by earlier root-running images may still be root-owned.
# After cap_drop:ALL, DAC_OVERRIDE is required to traverse/repair mode-0700 mounts.
if [ "$(id -u)" = "0" ]; then
  mkdir -p /var/pii-uploads /var/pii-uploads/ocr-work
  chown -R app:app /var/pii-uploads || true
  chmod 755 /var/pii-uploads || true
  chmod 755 /var/pii-uploads/ocr-work || true
  exec gosu app "$@"
fi
exec "$@"

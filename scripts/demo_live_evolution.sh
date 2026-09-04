#!/usr/bin/env bash
# Live proof of BACKWARD compatibility: evolve the running contract with a compatible
# change, and show that the frozen-schema legacy consumer keeps working -- untouched,
# unrebuilt, no error -- while the dynamic consumer picks up the new field. Restores
# the original v1 contract on exit, success or failure, so the repo is left clean.
set -euo pipefail
cd "$(dirname "$0")/.."

SCHEMA_PATH="schemas/order-created/schema.avsc"
BACKUP_PATH="$(mktemp)"
cp "$SCHEMA_PATH" "$BACKUP_PATH"

restore() {
  echo
  echo "=== Restoring the live contract to its original v1 content ==="
  cp "$BACKUP_PATH" "$SCHEMA_PATH"
  rm -f "$BACKUP_PATH"
  docker compose build producer -q
  docker compose up -d producer >/dev/null
  echo "Restored. Confirming no diff against git HEAD:"
  git diff --stat -- "$SCHEMA_PATH" || true
}
trap restore EXIT

echo "=== Evolving the live contract: adding optional 'discount_code' (BACKWARD compatible) ==="
cp demo/schema-compatible-v2.avsc "$SCHEMA_PATH"

echo "=== Rebuilding and restarting only the producer with the new schema ==="
docker compose build producer -q
docker compose up -d producer >/dev/null

echo "=== Waiting for v2-shaped messages to flow... ==="
sleep 8

echo
echo "--- consumer (dynamic reader schema): should now show 'discount_code' in fields ---"
docker compose logs consumer --tail 3

echo
echo "--- consumer-legacy (frozen v1 reader schema): should NOT show 'discount_code', no errors ---"
docker compose logs consumer-legacy --tail 3

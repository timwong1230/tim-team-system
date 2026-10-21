#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"
PIN="${POLAR_STAFF_PIN:-polar2026}"

curl -sf "$BASE/health" >/dev/null
curl -sf "$BASE/t/T02" >/dev/null
ORDER=$(curl -sf -X POST "$BASE/api/t/T02/orders" \
  -H 'Content-Type: application/json' \
  -d '{"party_size":2,"items":[{"item_id":"fries","qty":1},{"item_id":"coke","qty":2}]}')
echo "$ORDER" | grep -q '"ok":true'
curl -sf "$BASE/api/staff/orders?pin=$PIN" | grep -q T02
curl -sf "$BASE/staff/bill/T02?pin=$PIN" | grep -q 'Amount due'
curl -sf "$BASE/qr/T02.png" >/dev/null
echo "SMOKE OK"

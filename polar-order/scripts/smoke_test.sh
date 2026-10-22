#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"
PIN="${POLAR_STAFF_PIN:-polar2026}"
SEAT="${SMOKE_SEAT:-TABLE5}"

curl -sf "$BASE/health" >/dev/null

# Close any leftover open session on the smoke seat
curl -sf -X POST "$BASE/api/staff/bill/${SEAT}/close" \
  -F "pin=$PIN" -F "discount_percent=0" >/dev/null || true

PAGE=$(curl -sf "$BASE/t/${SEAT}")
grep -q 'What should we call you' <<<"$PAGE"

WELCOME=$(curl -sf -X POST "$BASE/api/t/${SEAT}/welcome" \
  -H 'Content-Type: application/json' \
  -d '{"guest_name":"Alex","party_size":3}')
grep -q '"ok":true' <<<"$WELCOME"

PAGE=$(curl -sf "$BASE/t/${SEAT}")
grep -q 'Hi Alex' <<<"$PAGE"

ORDER=$(curl -sf -X POST "$BASE/api/t/${SEAT}/orders" \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"item_id":"fries","qty":1},{"item_id":"coke","qty":2}]}')
grep -q '"ok":true' <<<"$ORDER"

ORDERS=$(curl -sf "$BASE/api/staff/orders?pin=$PIN")
grep -q "$SEAT" <<<"$ORDERS"
grep -q Alex <<<"$ORDERS"

BILL=$(curl -sf "$BASE/staff/bill/${SEAT}?pin=$PIN")
grep -q 'Alex' <<<"$BILL"

curl -sf "$BASE/qr/${SEAT}.png" -o /tmp/polar-qr-smoke.png

BOSS_HOME=$(curl -sf "$BASE/boss")
grep -q Jon <<<"$BOSS_HOME"
for b in jon barry tim ziv; do
  NAME=$(python3 -c "print('$b'.title())")
  PAGE=$(curl -sf "$BASE/boss/$b")
  grep -q "${NAME}'s station" <<<"$PAGE"
done

BOSS=$(curl -sf -X POST "$BASE/api/boss/barry/orders" \
  -H 'Content-Type: application/json' \
  -d '{"table_code":"BAR3","guest_name":"Sam","party_size":2,"items":[{"item_id":"coke","qty":1}]}')
grep -q '"ok":true' <<<"$BOSS"
grep -q Barry <<<"$BOSS"

CLOSE=$(curl -sf -X POST "$BASE/api/staff/bill/${SEAT}/close" \
  -F "pin=$PIN" -F "discount_percent=0")
grep -q '"ok":true' <<<"$CLOSE"
SID=$(python3 -c 'import sys,json; print(json.loads(sys.argv[1])["session_id"])' "$CLOSE")

.venv/bin/python - "$SID" <<'PY'
import sys
from pathlib import Path
from pypdf import PdfReader
sid = sys.argv[1]
path = Path("data/receipts") / f"receipt-S{sid}.pdf"
text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
assert "Guest: Alex" in text, f"guest name missing from receipt:\n{text}"
print("receipt ok", path)
PY

QRS=$(curl -sf "$BASE/staff/qrs?pin=$PIN")
test "$(grep -c '>Terrace ' <<<"$QRS")" -eq 8
test "$(grep -c '>Bar ' <<<"$QRS")" -eq 5
test "$(grep -c '>Table ' <<<"$QRS")" -eq 5

echo "SMOKE OK"

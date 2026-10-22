#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"
PIN="${POLAR_STAFF_PIN:-polar2026}"
SEAT="${SMOKE_SEAT:-TABLE5}"

curl -sf "$BASE/health" >/dev/null

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

# Boss: direct order, no seat/guest fields
for b in jon barry tim ziv; do
  NAME=$(python3 -c "print('$b'.title())")
  PAGE=$(curl -sf "$BASE/boss/$b")
  grep -q "${NAME}" <<<"$PAGE"
  grep -q 'Personal tab' <<<"$PAGE"
  # should NOT ask for seat
  ! grep -q 'Select seat' <<<"$PAGE"
done

BOSS=$(curl -sf -X POST "$BASE/api/boss/barry/orders" \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"item_id":"coke","qty":1}]}')
grep -q '"ok":true' <<<"$BOSS"
grep -q Barry <<<"$BOSS"

# Guest close — sales
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

# Boss order must NOT inflate daily guest sales; must appear in boss report
.venv/bin/python <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db import connect, init_db
from app.pricing import business_date
from app.reports import daily_sales_report, monthly_boss_report

init_db()
conn = connect()
biz = business_date(datetime.now(ZoneInfo("Asia/Hong_Kong")))
daily = daily_sales_report(conn, biz)
# closed guest session should be present; boss tab sessions excluded
assert all("Boss" not in (s["table"] or "") for s in daily["sessions"]), daily
boss = monthly_boss_report(conn, biz.year, biz.month)
barry = next(b for b in boss["bosses"] if b["boss_name"] == "Barry")
assert barry["order_count"] >= 1, barry
assert barry["total"] > 0, barry
print("boss report ok", barry["total"], "daily guest sessions", daily["session_count"])
conn.close()
PY

QRS=$(curl -sf "$BASE/staff/qrs?pin=$PIN")
test "$(grep -c '>Terrace ' <<<"$QRS")" -eq 8
test "$(grep -c '>Bar ' <<<"$QRS")" -eq 5
test "$(grep -c '>Table ' <<<"$QRS")" -eq 5
# boss seats must not appear as guest QRs
! grep -q 'Boss ·' <<<"$QRS"
grep -q '/boss/jon' <<<"$QRS"

REPORTS=$(curl -sf "$BASE/staff/reports?pin=$PIN")
grep -q 'Monthly Boss Report' <<<"$REPORTS"
grep -q 'Barry' <<<"$REPORTS"

echo "SMOKE OK"

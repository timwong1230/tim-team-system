#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"
PIN="${POLAR_STAFF_PIN:-polar2026}"
SEAT="${SMOKE_SEAT:-TABLE5}"
if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON="${PYTHON:-python3}"
fi

curl -sf "$BASE/health" >/dev/null

curl -sf -X POST "$BASE/api/staff/bill/${SEAT}/close" \
  -F "pin=$PIN" -F "discount_percent=0" -F "payment_method=Cash" >/dev/null || true

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
grep -q 'Payment method' <<<"$BILL"
grep -q 'AlipayHK' <<<"$BILL"
grep -q 'WeChat pay' <<<"$BILL"

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
# Ask AI + Order for HIM/HER (while guest session still open)
curl -sf -X POST "$BASE/api/staff/bill/TABLE3/close" \
  -F "pin=$PIN" -F "discount_percent=0" -F "payment_method=Cash" >/dev/null || true
curl -sf -X POST "$BASE/api/t/TABLE3/welcome" -H 'Content-Type: application/json' \
  -d '{"guest_name":"Sam","party_size":1}' >/dev/null
AI=$(curl -sf -X POST "$BASE/api/t/${SEAT}/ask-ai" -H 'Content-Type: application/json' \
  -d '{"message":"Something sweet please"}')
grep -q '"ok":true' <<<"$AI"
grep -q 'suggestions' <<<"$AI"
GIFT=$(curl -sf -X POST "$BASE/api/t/${SEAT}/orders" -H 'Content-Type: application/json' \
  -d '{"items":[{"item_id":"coke","qty":1}],"deliver_to":"TABLE3","gift_message":"nice to meet you"}')
grep -q '"ok":true' <<<"$GIFT"
STAFF=$(curl -sf "$BASE/api/staff/orders?pin=$PIN")
grep -q 'nice to meet you' <<<"$STAFF"
grep -q 'TABLE3' <<<"$STAFF"

# Reject close without payment method
BAD_CLOSE=$(curl -s -o /tmp/polar-close-bad.json -w '%{http_code}' -X POST "$BASE/api/staff/bill/${SEAT}/close" \
  -F "pin=$PIN" -F "discount_percent=0")
test "$BAD_CLOSE" != "200"

CLOSE=$(curl -sf -X POST "$BASE/api/staff/bill/${SEAT}/close" \
  -F "pin=$PIN" -F "discount_percent=0" -F "payment_method=Visa")
grep -q '"ok":true' <<<"$CLOSE"
SID=$(python3 -c 'import sys,json; print(json.loads(sys.argv[1])["session_id"])' "$CLOSE")

"$PYTHON" - "$SID" <<'PY'
import sys
from pathlib import Path
from pypdf import PdfReader
sid = sys.argv[1]
path = Path("data/receipts") / f"receipt-S{sid}.pdf"
text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
assert "Guest: Alex" in text, f"guest name missing from receipt:\n{text}"
assert "Visa" in text, f"payment method missing from receipt:\n{text}"
print("receipt ok", path)
PY

# Nightly claims — use Polar business day from reports page
REPORTS=$(curl -sf "$BASE/staff/reports?pin=$PIN")
DAY=$(python3 -c 'import re,sys; m=re.search(r'"'"'name="day" value="([0-9-]+)"'"'"', sys.stdin.read()); print(m.group(1) if m else "")' <<<"$REPORTS")
test -n "$DAY"
CLAIM=$(curl -sf -X POST "$BASE/api/staff/claims" \
  -H 'Content-Type: application/json' \
  -d "{\"pin\":\"$PIN\",\"business_date\":\"$DAY\",\"category\":\"Ice\",\"amount\":80}")
grep -q '"ok":true' <<<"$CLAIM"
CLAIM2=$(curl -sf -X POST "$BASE/api/staff/claims" \
  -H 'Content-Type: application/json' \
  -d "{\"pin\":\"$PIN\",\"business_date\":\"$DAY\",\"custom_name\":\"Extra bags\",\"amount\":25}")
grep -q '"ok":true' <<<"$CLAIM2"
grep -q 'Extra bags' <<<"$CLAIM2"
REPORTS=$(curl -sf "$BASE/staff/reports?pin=$PIN&day=$DAY")
grep -q 'Claims' <<<"$REPORTS"
grep -q 'Ice' <<<"$REPORTS"
grep -q 'Extra bags' <<<"$REPORTS"
grep -q 'Visa' <<<"$REPORTS"

# Boss order must NOT inflate daily guest sales; must appear in boss report
"$PYTHON" <<'PY'
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
test "$(grep -c '>Terrace ' <<<"$QRS")" -eq 9
test "$(grep -c '>Bar ' <<<"$QRS")" -eq 6
test "$(grep -c '>Table ' <<<"$QRS")" -eq 5
# 3×3 print sheets (batch of 9) — guest seats fill 3 pages
test "$(grep -c 'class="qr-sheet' <<<"$QRS")" -ge 3
# boss seats must not appear as guest QRs
! grep -q 'Boss ·' <<<"$QRS"
grep -q '/boss/jon' <<<"$QRS"

REPORTS=$(curl -sf "$BASE/staff/reports?pin=$PIN")
grep -q 'Monthly Boss Report' <<<"$REPORTS"
grep -q 'Barry' <<<"$REPORTS"

echo "SMOKE OK"

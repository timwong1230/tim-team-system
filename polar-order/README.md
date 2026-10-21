# Polar Lounge — QR Table Ordering

Guest scans a table QR → orders on phone → staff get a live alert → at checkout staff open the table bill to see **amount due** (payment stays on your third-party POS).

## Quick start

```bash
cd polar-order
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open:

- Guest demo: http://localhost:8080/t/T01
- Staff: http://localhost:8080/staff  
  Default PIN: `polar2026`
- Table QR print sheet: Staff → Table QR codes

## Flow

1. Print QR for each table (`/staff/qrs`)
2. Guest scans → `/t/T01` … `/t/T20`
3. Guest adds items → **Send to bar**
4. Staff board beeps + shows new order
5. Staff marks Preparing → Ready → Served
6. Checkout: Staff → Tables → tap table → see amount due → collect payment elsewhere → **Mark paid & close table**

## Bill rules (from Polar menu)

- 10% service charge
- Snack charge HKD 10 / head (from party size)
- Meditation Hour (2–5pm HK): shisha $250, drinks 30% off
- Happy Hour (5–8pm HK): drinks 20% off

Menu seeded from `data/menu.json` (Polar Menu Final Version).

## Staff extras

- **Discount on bill:** enter `10` for 10% off (blank/0 = full price)
- **PDF receipt:** generated when you mark paid (`/staff/receipt/{session_id}`)
- **Reports:** `/staff/reports` — nightly close (2pm–2am), monthly sales, purchase by category / by item
- **Menu photos:** see `docs/ADD-MENU-PHOTOS.md`

## Notes

- This system does **not** process payments.
- Change staff PIN via env `POLAR_STAFF_PIN` (default `polar2026`).
- SQLite DB file: `data/polar_order.db` (created on first run).
- Receipt PDFs: `data/receipts/` (gitignored).

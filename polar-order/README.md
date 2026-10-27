# Polar Lounge — QR Table Ordering

Guest scans a table QR → orders on phone → staff get a live alert → at checkout staff open the table bill to see **amount due** (payment stays on your third-party POS).

## Quick start (local)

```bash
cd polar-order
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open:

- Staff: http://localhost:8080/staff — PIN `polar2026`
- Practice guest (separate Demo seat, not Table 1): http://localhost:8080/t/DEMO
- Real seats: scan printed QR → `/t/TABLE1` …
- Table QR print sheet: Staff → Seat QR codes

## Deploy to cloud (Render) — recommended

1. Open: **https://render.com/deploy?repo=https://github.com/timwong1230/tim-team-system**
2. Fill the form:
   - **Blueprint Name:** `polar-order` (any unique name)
   - **Branch:** `main`
   - **Blueprint Path:** leave as `render.yaml`
3. When prompted, set **`POLAR_STAFF_PIN`** (your staff login PIN).
4. Confirm service **polar-order** (Singapore + 1GB disk) → **Apply**.
5. Wait until Live, then use:
   - Staff: `https://YOUR-SERVICE.onrender.com/staff`
   - Practice guest: `https://YOUR-SERVICE.onrender.com/t/DEMO` (never use Table 1 for demos)
6. Staff → **Table QR codes** → print & stick on each seat.

Optional: Render → Settings → **Custom Domain** (e.g. `order.polarlounge.hk`).

Docker local smoke test:

```bash
cd polar-order
docker build -t polar-order .
docker run --rm -p 8080:8080 -e POLAR_STAFF_PIN=polar2026 -v polar-data:/data polar-order
```

## Flow

1. Print QR for each table (`/staff/qrs`)
2. Guest scans → `/t/TABLE1` …
3. Guest adds items → **Send to bar**
4. Staff board beeps + shows new order
5. Staff marks Preparing → Ready → Served
6. Checkout: Staff → Tables → confirm party size → collect payment elsewhere → **Mark paid**

## Bill rules (from Polar menu)

- 10% service charge
- Snack charge HKD 10 / head (from party size)
- Meditation Hour (2–5pm HK): shisha $250, drinks 30% off
- Happy Hour (5–8pm HK): drinks 20% off

Menu seeded from `data/menu.json`.

## Staff extras

- **Order for table:** Staff → Seats → **Order for table** (or Bill → **Order for this table**) — place full menu orders for a guest even if they are not using the QR phone
- **Discount on bill:** enter `10` for 10% off (blank/0 = full price)
- **PDF receipt:** generated when you mark paid
- **Reports:** `/staff/reports` — nightly close, monthly sales, boss report, WhatsApp sales text, **Sync to Google Sheet**
- **Ask AI** mood chips on guest menu

## Daily_Sales → Google Sheets → P&L / Balance Sheet

Nightly close upserts one row (payment mix, Claim, Daily Sales, Cash Tilt, Monthly Total).

**Sync target (Finance workbook):**  
https://docs.google.com/spreadsheets/d/1WRTjFrzLXvL0OTWv-FE8uPF-UWBSFJe6gNuFnB9cF-I/edit  

See [`finance/README.md`](finance/README.md) for tabs and Bank_Entries rules.

| Who | Does |
| --- | --- |
| Staff | Reports → Sync to Google Sheet → writes `Daily_Sales` tab |
| Tim | Only `Bank_Entries` (bank lines + Nature) |
| Sheet formulas | `P&L_Monthly`, `Balance_Sheet`, `KPI` |

**Render env**

| Key | Value |
| --- | --- |
| `POLAR_DAILY_SALES_SHEET_ID` | `1WRTjFrzLXvL0OTWv-FE8uPF-UWBSFJe6gNuFnB9cF-I` |
| `POLAR_DAILY_SALES_WORKSHEET` | `Daily_Sales` |
| `POLAR_GSPREAD_KEY` | Service account JSON — share the Finance sheet with that SA as **Editor** |

## Notes

- This system does **not** process payments.
- Staff PIN: env `POLAR_STAFF_PIN` (default `polar2026`).
- Runtime DB/receipts: env `POLAR_DATA_DIR` (default `data/`; cloud uses `/data`).
- Menu photos: see `docs/ADD-MENU-PHOTOS.md`

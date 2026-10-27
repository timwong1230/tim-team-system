# Polar Lounge — Finance (P&L + Balance Sheet)

## Workbook

| File | Link |
| --- | --- |
| **Template (full multi-tab)** | [Drive Excel](https://drive.google.com/file/d/1T94DR8EugI7-nirBswpOG4xXczhUSrXr/view) — open with Google Sheets |
| Repo copy | `Polar_Lounge_Finance_PL_BS.xlsx` |
| Daily sales sync target (today) | [Polar Lounge — Daily Sales](https://docs.google.com/spreadsheets/d/1GBFYoOa6oBSTono0b6qy8qX6mKQSbOsnaoWTzP-LiIY/edit) |

## Tabs

| Tab | Who | Purpose |
| --- | --- | --- |
| `00_README` / `Setup` | — | Instructions |
| `Chart_of_Accounts` | locked list | Nature / account codes |
| `Daily_Sales` | **Auto** (Polar Order Sync) | Nightly tenders, Claim, Cash Tilt, Monthly Total |
| `Bank_Entries` | **Tim only** | HSBC SA/CA lines + Nature |
| `P&L_Monthly` | Auto formulas | Sales − COGS − opex → net profit + ratios |
| `Balance_Sheet` | Auto formulas | Bank + cash tilt vs equity |
| `KPI` | Auto | Partners-meeting numbers |

## Daily workflow

1. Staff: Polar Order → Reports → claims / Cash Tilt → **Sync to Google Sheet**
2. Tim: paste bank movements into `Bank_Entries` (yellow). Nature via dropdown.
3. Read `P&L_Monthly` / `Balance_Sheet` / `KPI` — no copy-paste into CWB.

## One-time setup

1. Open the Excel template → **Open with Google Sheets** → keep as Google Spreadsheet.
2. Share with Polar Order **service account** (Editor) + `cwbpolar@gmail.com`.
3. Set Render:
   - `POLAR_DAILY_SALES_SHEET_ID` = that spreadsheet id  
   - `POLAR_DAILY_SALES_WORKSHEET` = `Daily_Sales`  
   - `POLAR_GSPREAD_KEY` = service account JSON  
4. Until converted, Sync continues writing the standalone Daily Sales sheet above.

## Bank_Entries rules

- Money in = positive; money out = negative.
- Fill either `hsbc_sa` or `hsbc_ca` (or both if split).
- `nature` must match Chart of Accounts exactly (drives P&L lines).
- `account_code` fills via formula.

## Archive

[Polar Lounge CWB](https://docs.google.com/spreadsheets/d/1tbawLTy__6ox4yzDkn-sHEtUedmhzcNZnZtjHWB4i64/edit) stays historical — no new monthly tabs needed.

# Polar Lounge — Finance (P&L + Balance Sheet)

## Live workbook

https://docs.google.com/spreadsheets/d/1WRTjFrzLXvL0OTWv-FE8uPF-UWBSFJe6gNuFnB9cF-I/edit

| File | Link |
| --- | --- |
| **Live Google Sheet** | above |
| Repo Excel template | `Polar_Lounge_Finance_PL_BS.xlsx` |
| Legacy Daily Sales sheet | [archive](https://docs.google.com/spreadsheets/d/1GBFYoOa6oBSTono0b6qy8qX6mKQSbOsnaoWTzP-LiIY/edit) |

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
3. Read `P&L_Monthly` / `Balance_Sheet` / `KPI`.

## Render

| Key | Value |
| --- | --- |
| `POLAR_DAILY_SALES_SHEET_ID` | `1WRTjFrzLXvL0OTWv-FE8uPF-UWBSFJe6gNuFnB9cF-I` |
| `POLAR_DAILY_SALES_WORKSHEET` | `Daily_Sales` |
| `POLAR_GSPREAD_KEY` | Service account JSON |

Share the live sheet with the service account email as **Editor**.

## Bank_Entries rules

- Money in = positive; money out = negative.
- Fill either `hsbc_sa` or `hsbc_ca` (or both if split).
- `nature` must match Chart of Accounts exactly (drives P&L lines).

## Archive

[Polar Lounge CWB](https://docs.google.com/spreadsheets/d/1tbawLTy__6ox4yzDkn-sHEtUedmhzcNZnZtjHWB4i64/edit) stays historical.

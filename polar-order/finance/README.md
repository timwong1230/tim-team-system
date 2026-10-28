# Polar Lounge — Finance（最少人工）

## Live workbook

https://docs.google.com/spreadsheets/d/1WRTjFrzLXvL0OTWv-FE8uPF-UWBSFJe6gNuFnB9cF-I/edit

## 你（Tim）最最少要做咩

**每星期／每兩星期一次：**

1. HSBC app／網上銀行 → download 交易 CSV  
2. Polar Order → **Reports** → **Upload bank CSV**（揀 SA 或 CA）  
3. 睇吓 `Bank_Entries` Nature 有冇估錯 → 改錯嗰幾行  
4. 睇 `P&L_Monthly` / `KPI`

**唔使日日做。** 唔使逐筆手打銀行。

## 員工做咩（每日埋數）

1. 關枱收錢、入 Claims  
2. 入 **Cash Tilt** → **Save**  
3. → 系統**自動** sync `Daily_Sales` 去 Finance sheet  
4. （可選）WhatsApp Sales report  

「Sync now (backup)」只係自動失敗時先㩒。

## 全自動邊度

| 步驟 | 邊個 | 自動？ |
| --- | --- | --- |
| 銷售／付款組合 | POS | 自動計 |
| Claims / Cash Tilt | 員工入 | 人手（現場先知） |
| Daily_Sales → Sheet | 系統 | **自動**（Save Cash Tilt 後） |
| 銀行分類 → P&L | 系統 | CSV 上載後**自動估 Nature** |
| P&L / BS / KPI | Sheet 公式 | 自動 |

## Render

| Key | Value |
| --- | --- |
| `POLAR_DAILY_SALES_SHEET_ID` | `1WRTjFrzLXvL0OTWv-FE8uPF-UWBSFJe6gNuFnB9cF-I` |
| `POLAR_DAILY_SALES_WORKSHEET` | `Daily_Sales` |
| `POLAR_BANK_ENTRIES_WORKSHEET` | `Bank_Entries` |
| `POLAR_GSPREAD_KEY` | Service account JSON；Finance sheet share 俾 SA **Editor** |

## 未自動化（刻意留俾人）

- 銀行登入／download CSV（系統 access 唔到銀行）  
- Nature 估錯時人手改一行  
- 交會計／報稅／核數（正式帳仍交會計師）

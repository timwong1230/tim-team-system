"""CSS theme for TIM TEAM system."""

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Instrument+Serif:ital@0;1&display=swap');

:root {
  color-scheme: light dark;
  --gold: #C5A028;
  --gold-deep: #9A7B1A;
  --gold-soft: #F7F1DE;
  --ink: #1C2430;
  --muted: #6B7280;
  --line: #E6E8EC;
  --surface: #FFFFFF;
  --bg: #F3F1EB;
  --ok: #1F7A4D;
  --warn: #B45309;
  --danger: #B42318;
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1200px 500px at 10% -10%, #F8EFC8 0%, transparent 55%),
    radial-gradient(900px 420px at 100% 0%, #E8EEF6 0%, transparent 50%),
    var(--bg) !important;
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #FFFFFF 0%, #F7F5F0 100%) !important;
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] > div:first-child {
  padding-top: 1rem !important;
  padding-left: 0.85rem !important;
  padding-right: 0.85rem !important;
}
[data-testid="stHeader"] { background: transparent !important; }

html, body, [class*="css"] {
  font-family: 'DM Sans', sans-serif;
  color: var(--ink);
}
h1, h2, h3 {
  font-family: 'Instrument Serif', Georgia, serif !important;
  color: var(--ink) !important;
  font-weight: 400 !important;
  letter-spacing: 0.2px;
}
h1 { font-size: 2.35rem !important; }
h2 { font-size: 1.85rem !important; }
h3 { font-size: 1.45rem !important; }

/* Sidebar brand / user */
.tt-side-brand { margin: 0 0 10px 0; padding: 2px 4px 8px; }
.tt-side-kicker {
  font-size: 0.68rem; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--gold-deep); font-weight: 650; margin-bottom: 4px;
}
.tt-side-user {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 1.45rem; color: var(--ink); line-height: 1.15;
}
.tt-side-role { font-size: 0.8rem; color: var(--muted); margin-top: 2px; }
.tt-side-nav-label {
  font-size: 0.68rem; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--muted); font-weight: 650; margin: 14px 4px 8px;
}
.tt-side-spacer { height: 18px; }

/* Active nav — subtle light-up only (no heavy glow / top bar) */
.tt-nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 11px 12px; margin: 3px 0; border-radius: 12px;
  background: #FFFFFF;
  border: 1px solid var(--line);
  box-sizing: border-box;
}
.tt-nav-item-active {
  background: #F7F1DE;
  border: 1px solid #D4AF37;
  box-shadow: none;
}
.tt-nav-bar {
  width: 3px; align-self: stretch; min-height: 16px; border-radius: 2px;
  background: var(--gold); flex-shrink: 0;
}
.tt-nav-item-active .tt-nav-text {
  font-weight: 600; color: #5C4A12; font-size: 0.94rem; line-height: 1.35;
}

/* Main content primary buttons */
div.stButton > button {
  background: linear-gradient(135deg, #D4AF37 0%, #B38F21 100%) !important;
  color: #FFFFFF !important;
  border: none !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
  letter-spacing: 0.4px;
  box-shadow: 0 6px 16px rgba(181, 143, 33, 0.22);
}
div.stButton > button[kind="secondary"] {
  background: #FFFFFF !important;
  color: var(--ink) !important;
  border: 1px solid var(--line) !important;
  box-shadow: none;
}

/* Sidebar inactive nav — keep a light frame so selection does not "lose" a box */
[data-testid="stSidebar"] div.stButton > button,
[data-testid="stSidebar"] div.stButton > button[kind="secondary"],
[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
  background: #FFFFFF !important;
  color: var(--ink) !important;
  border: 1.5px solid var(--line) !important;
  border-radius: 12px !important;
  box-shadow: none !important;
  justify-content: flex-start !important;
  text-align: left !important;
  font-weight: 500 !important;
  font-size: 0.92rem !important;
  letter-spacing: 0.01em !important;
  padding: 11px 12px !important;
  min-height: 44px !important;
  margin: 3px 0 !important;
}
[data-testid="stSidebar"] div.stButton > button:hover {
  background: #FFFDF5 !important;
  color: #5C4A12 !important;
  border-color: #E2C56A !important;
}
[data-testid="stSidebar"] div.stButton > button:focus {
  box-shadow: none !important;
  outline: none !important;
  border-color: #C5A028 !important;
}

.tt-hero {
  background: linear-gradient(135deg, #1C2430 0%, #2C3A4E 55%, #3A2F12 100%);
  color: #F8F4EA;
  border-radius: 18px;
  padding: 28px 28px 24px;
  margin-bottom: 18px;
  position: relative;
  overflow: hidden;
}
.tt-hero::after {
  content: "";
  position: absolute;
  right: -40px; top: -40px;
  width: 180px; height: 180px;
  background: radial-gradient(circle, rgba(212,175,55,0.35), transparent 70%);
}
.tt-hero h1, .tt-hero h2, .tt-hero p, .tt-hero span { color: #F8F4EA !important; }
.tt-kicker {
  font-family: 'DM Sans', sans-serif !important;
  font-size: 0.78rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #D4AF37 !important;
  margin-bottom: 8px;
}
.tt-sub { color: rgba(248,244,234,0.78) !important; margin: 6px 0 0 0; font-size: 0.98rem; }

.tt-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px 18px 16px;
  box-shadow: 0 8px 24px rgba(28,36,48,0.04);
  height: 100%;
}
.tt-label {
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 6px;
}
.tt-value {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 1.85rem;
  color: var(--ink);
  line-height: 1.1;
}
.tt-hint { color: var(--muted); font-size: 0.88rem; margin-top: 6px; }

.tt-progress-wrap {
  background: #ECE7DC;
  border-radius: 999px;
  height: 10px;
  overflow: hidden;
  margin-top: 10px;
}
.tt-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #D4AF37, #F0D078);
  border-radius: 999px;
}

.activity-card {
  background: #ffffff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  border-left: 5px solid #e9ecef;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.card-signed { border-left-color: #D4AF37 !important; }
.card-meeting { border-left-color: #3498db !important; }
.card-recruit { border-left-color: #9b59b6 !important; }
.card-admin { border-left-color: #95a5a6 !important; }
.act-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.act-avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; margin-right: 10px; border: 2px solid #f0f0f0; }
.act-name { font-weight: 700; color: #2c3e50; }
.act-time { font-size: 0.85em; color: #95a5a6; }
.act-badge { padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 600; }
.badge-signed { background-color: #FFF8E1; color: #D4AF37; border: 1px solid #D4AF37; }
.badge-meeting { background-color: #ebf5fb; color: #3498db; border: 1px solid #3498db; }
.badge-recruit { background-color: #f4ecf7; color: #9b59b6; border: 1px solid #9b59b6; }
.badge-default { background-color: #f8f9fa; color: #7f8c8d; border: 1px solid #bdc3c7; }
.act-content { background-color: #f8f9fa; padding: 10px; border-radius: 8px; color: #555; font-size: 0.95em; line-height: 1.5; margin-top: 5px; }

.reward-card-premium {
  background: linear-gradient(145deg, #ffffff, #fffdf5);
  border: 2px solid #D4AF37;
  border-radius: 16px; padding: 25px 20px; text-align: center;
  box-shadow: 0 10px 25px rgba(212, 175, 55, 0.15);
  height: 100%; position: relative; overflow: hidden;
}
.reward-card-premium::before {
  content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 8px;
  background: linear-gradient(90deg, #D4AF37, #FDC830, #D4AF37);
}
.reward-icon { font-size: 2.4em; margin-bottom: 12px; display: block; }
.reward-title-p { color: #D4AF37; font-size: 1.15em; font-weight: 800; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1.2px; }
.reward-prize-p { color: #c0392b; font-size: 1.45em; font-weight: 900; margin-bottom: 8px; }
.reward-desc-p { color: #7f8c8d; font-size: 0.9em; line-height: 1.4; }

.challenge-header-box {
  background: linear-gradient(to right, #FFF8E1, #FFFFFF);
  border-left: 6px solid #D4AF37;
  padding: 22px; border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.05);
  margin-bottom: 20px;
}
.offer-banner {
  background: linear-gradient(135deg, #1C2430 0%, #2C3A4E 100%);
  color: #F8F4EA !important;
  border-radius: 14px;
  padding: 14px 16px;
  font-size: 0.9rem;
  line-height: 1.5;
  margin: 0 0 14px 0;
  border: 1px solid rgba(212,175,55,0.35);
  box-shadow: 0 10px 24px rgba(28,36,48,0.12);
}
.offer-section {
  margin: 0 0 18px 0;
}
.offer-section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 800;
  font-size: 1.02rem;
  color: #1C2430 !important;
  margin: 0 0 8px 0;
}
.offer-section-bar {
  display: inline-block;
  width: 4px;
  height: 16px;
  border-radius: 4px;
  background: #D4AF37;
  flex-shrink: 0;
}
.offer-table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border: 1px solid #E8E2D4;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 22px rgba(28,36,48,.05);
  margin-bottom: 4px;
}
.offer-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 520px;
}
.offer-table-fixed {
  table-layout: fixed;
}
.offer-table th {
  background: linear-gradient(180deg, #1C2430, #2A3444);
  color: #F8F4EA !important;
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 700;
  padding: 12px;
  text-align: left;
  white-space: nowrap;
}
.offer-table td {
  padding: 12px;
  font-size: 0.9rem;
  color: #2C3440 !important;
  line-height: 1.45;
  border-top: 1px solid #F0EBE0;
  vertical-align: top;
  word-break: break-word;
}
.offer-table tr:nth-child(even) td {
  background: #FCFAF5;
}
.offer-table col.offer-product,
.offer-table th.offer-product,
.offer-table td.offer-product {
  width: 20%;
}
.offer-table td.offer-product {
  font-weight: 700;
  color: #1C2430 !important;
}
/* 詳情／優惠重點：主力闊欄 */
.offer-table col.offer-detail-col,
.offer-table th.offer-detail-col,
.offer-table td.offer-detail-col {
  width: 58%;
}
.offer-table col.offer-mid-col,
.offer-table th.offer-mid-col,
.offer-table td.offer-mid-col {
  width: 14%;
}
/* 備註：窄欄 */
.offer-table col.offer-note-col,
.offer-table th.offer-note-col,
.offer-table td.offer-note-col {
  width: 10%;
  color: #6B7280 !important;
  font-size: 0.8rem;
}
.offer-table th.offer-note-col {
  color: #F8F4EA !important;
  white-space: nowrap;
}
/* 項目：領獎須知等標籤欄（窄） */
.offer-table col.offer-label-col,
.offer-table th.offer-label-col,
.offer-table td.offer-label-col {
  width: 18%;
  font-weight: 700;
  color: #1C2430 !important;
  white-space: nowrap;
}
/* 兩欄表（項目／說明）：項目窄、說明闊 */
.offer-table.offer-cols-2 col.offer-label-col,
.offer-table.offer-cols-2 th.offer-label-col,
.offer-table.offer-cols-2 td.offer-label-col,
.offer-table.offer-cols-2 col.offer-product,
.offer-table.offer-cols-2 th.offer-product,
.offer-table.offer-cols-2 td.offer-product {
  width: 18%;
}
.offer-table.offer-cols-2 col.offer-detail-col,
.offer-table.offer-cols-2 th.offer-detail-col,
.offer-table.offer-cols-2 td.offer-detail-col {
  width: 82%;
}
/* 三欄表（產品／詳情／備註）：詳情再闊、備註再窄 */
.offer-table.offer-cols-3 col.offer-product,
.offer-table.offer-cols-3 th.offer-product,
.offer-table.offer-cols-3 td.offer-product {
  width: 22%;
}
.offer-table.offer-cols-3 col.offer-detail-col,
.offer-table.offer-cols-3 th.offer-detail-col,
.offer-table.offer-cols-3 td.offer-detail-col {
  width: 68%;
}
.offer-table.offer-cols-3 col.offer-note-col,
.offer-table.offer-cols-3 th.offer-note-col,
.offer-table.offer-cols-3 td.offer-note-col {
  width: 10%;
}
.offer-card {
  background: #ffffff;
  border: 1px solid #E8E2D4;
  border-left: 5px solid #D4AF37;
  border-radius: 12px;
  padding: 16px 16px 14px;
  margin: 0 0 12px 0;
  box-shadow: 0 6px 18px rgba(28,36,48,0.05);
}
.offer-title {
  font-weight: 800;
  font-size: 1.05rem;
  color: #1C2430;
  margin-bottom: 6px;
}
.offer-detail {
  color: #3A4452;
  font-size: 0.95rem;
  line-height: 1.55;
}
.offer-note {
  margin-top: 10px;
  color: #7A6420;
  background: #FFF8E1;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 0.85rem;
}

.login-panel {
  background: rgba(255,255,255,0.92);
  border: 1px solid rgba(197,160,40,0.35);
  border-radius: 18px;
  padding: 28px 24px;
  box-shadow: 0 18px 40px rgba(28,36,48,0.08);
}

/* Premium login composition — ink + gold, one visual unit */
.tt-login-shell {
  position: relative;
  overflow: hidden;
  text-align: center;
  background:
    radial-gradient(720px 320px at 50% -8%, rgba(212,175,55,0.22), transparent 58%),
    linear-gradient(165deg, #10161F 0%, #1C2430 52%, #2A2314 100%) !important;
  border: 1px solid rgba(212,175,55,0.32) !important;
  border-radius: 22px !important;
  padding: 44px 28px 38px !important;
  margin-bottom: 18px !important;
  box-shadow: 0 28px 64px rgba(16,22,31,0.28) !important;
}
.tt-login-shell::after {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(212,175,55,0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(212,175,55,0.045) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at 50% 30%, #000 20%, transparent 72%);
  pointer-events: none;
}
.tt-login-brand {
  position: relative;
  z-index: 2;
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 700 !important;
  font-size: 1.15rem !important;
  letter-spacing: 0.28em !important;
  text-transform: uppercase !important;
  color: #F0D078 !important; /* bright gold — readable on ink */
  margin: 0 0 14px 0 !important;
  line-height: 1.35 !important;
}
.tt-login-shell h1,
.tt-login-shell h1.tt-login-title,
.tt-login-title {
  position: relative;
  z-index: 2;
  margin: 0 !important;
  color: #F8F4EA !important;
  font-size: 2.55rem !important;
  line-height: 1.12 !important;
  font-weight: 400 !important;
}
.tt-login-rule {
  position: relative;
  z-index: 2;
  width: 56px;
  height: 2px;
  margin: 20px auto 0 !important;
  background: linear-gradient(90deg, transparent, #D4AF37, transparent) !important;
}
.tt-login-foot {
  text-align: center;
  color: #8A8478;
  font-size: 0.82rem;
  letter-spacing: 0.02em;
  margin-top: 14px;
}
.iris-banner {
  background: linear-gradient(90deg, #EDF5FF, #FFFFFF);
  border: 1px solid #C9DBF2;
  border-left: 5px solid #2F6FED;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
}

.tt-install-card {
  background: linear-gradient(135deg, #FFF8E1, #FFFFFF);
  border: 1px solid #E8D59A;
  border-radius: 14px;
  padding: 14px 16px;
  margin: 10px 0 16px 0;
}
/* Marker only — Streamlit cannot nest the popover inside this div */
.tt-mobile-nav {
  display: none;
}

/* Phone top menu (popover right after marker): sticky + no copy/select */
[data-testid="element-container"]:has(.tt-mobile-nav)
  + [data-testid="element-container"] {
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(243,241,235,0.92);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  padding: 6px 0 10px;
  margin-bottom: 8px;
  -webkit-user-select: none !important;
  user-select: none !important;
  -webkit-touch-callout: none !important;
}
[data-testid="element-container"]:has(.tt-mobile-nav)
  + [data-testid="element-container"] *,
[data-testid="element-container"]:has(.tt-mobile-nav)
  + [data-testid="element-container"] button {
  -webkit-user-select: none !important;
  user-select: none !important;
  -webkit-touch-callout: none !important;
  caret-color: transparent !important;
}
/* Popover trigger — look like a nav bar, not an editable field */
[data-testid="element-container"]:has(.tt-mobile-nav)
  + [data-testid="element-container"] [data-testid="stPopover"] button,
[data-testid="element-container"]:has(.tt-mobile-nav)
  + [data-testid="element-container"] button[kind="secondary"] {
  width: 100% !important;
  min-height: 48px !important;
  justify-content: space-between !important;
  text-align: left !important;
  font-size: 1.02rem !important;
  font-weight: 600 !important;
  border: 1px solid var(--line) !important;
  border-radius: 12px !important;
  background: #FFFFFF !important;
  color: var(--ink) !important;
  box-shadow: none !important;
}

/* ---- Leaderboard cards ---- */
.lb-list { display: flex; flex-direction: column; gap: 12px; margin: 4px 0 18px; }
.lb-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 14px 12px;
  box-shadow: 0 8px 22px rgba(28,36,48,0.05);
  position: relative;
  overflow: hidden;
}
.lb-card.lb-top1 {
  background: linear-gradient(145deg, #FFFDF5 0%, #FFFFFF 55%);
  border-color: #E2C56A;
  box-shadow: 0 10px 28px rgba(197,160,40,0.16);
}
.lb-card.lb-top1::before {
  content: "";
  position: absolute; left: 0; top: 0; right: 0; height: 4px;
  background: linear-gradient(90deg, #D4AF37, #F0D078, #D4AF37);
}
.lb-row { display: flex; align-items: center; gap: 12px; }
.lb-rank {
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 0.95rem;
  background: #F3F1EB; color: #1C2430; flex-shrink: 0;
}
.lb-rank.gold { background: linear-gradient(135deg,#F0D078,#C5A028); color: #1C2430; }
.lb-rank.silver { background: linear-gradient(135deg,#EEF1F4,#B8C0C8); color: #1C2430; }
.lb-rank.bronze { background: linear-gradient(135deg,#F0D3B8,#C4895A); color: #1C2430; }
.lb-avatar {
  width: 48px; height: 48px; border-radius: 50%; object-fit: cover;
  border: 2px solid #F0E6C4; flex-shrink: 0; background: #eee;
}
.lb-main { flex: 1; min-width: 0; }
.lb-name {
  font-weight: 700; font-size: 1.05rem; color: #1C2430;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.lb-fyc {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 1.35rem; color: #1C2430; line-height: 1.15; margin-top: 2px;
}
.lb-target { color: #6B7280; font-size: 0.82rem; margin-top: 2px; }
.lb-pct {
  flex-shrink: 0; text-align: right;
  font-weight: 800; font-size: 1.05rem; color: #9A7B1A;
  min-width: 58px;
}
.lb-bar-wrap {
  margin-top: 10px; height: 9px; border-radius: 999px;
  background: #ECE7DC; overflow: hidden;
}
.lb-bar {
  height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, #D4AF37, #F0D078);
}
.lb-meta {
  display: flex; gap: 14px; margin-top: 10px;
  color: #6B7280; font-size: 0.84rem;
}
.lb-meta strong { color: #1C2430; font-weight: 700; }
.lb-chip {
  display: inline-flex; align-items: center; gap: 4px;
  background: #F7F1DE; border-radius: 999px;
  padding: 3px 9px; color: #7A6420; font-size: 0.78rem; font-weight: 650;
}

.dash-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 8px 0 18px; }
.dash-kpi {
  background: #fff; border: 1px solid var(--line); border-radius: 14px;
  padding: 12px 12px 10px; box-shadow: 0 6px 18px rgba(28,36,48,0.04);
}
.dash-kpi .k { font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase; color: #6B7280; }
.dash-kpi .v {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 1.35rem; color: #1C2430; margin-top: 4px; line-height: 1.1;
}

/* Member home — 我的業績 */
.tt-scorecard { display: flex; flex-direction: column; gap: 10px; margin: 4px 0 8px; }
.tt-score-card {
  background: #FFFEFA;
  border: 1px solid #E8E4D9;
  border-radius: 14px;
  padding: 14px 16px 12px;
  box-shadow: 0 4px 14px rgba(28, 36, 48, 0.04);
}
.tt-score-card-accent { border-left: 4px solid #C5A028; }
.tt-score-kicker {
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  color: #6B7280;
  margin: 0 0 6px;
}
.tt-score-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
}
.tt-score-row-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.tt-score-value {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 1.75rem;
  color: #1C2430;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.tt-score-value-sm { font-size: 1.45rem; }
.tt-score-hint {
  font-size: 0.78rem;
  color: #6B7280;
  margin-top: 8px;
  line-height: 1.4;
}
.tt-score-bar {
  background: #F3F4F6;
  border-radius: 999px;
  height: 8px;
  overflow: hidden;
  margin-top: 10px;
}
.tt-score-bar > span {
  display: block;
  height: 100%;
  background: #C5A028;
  border-radius: 999px;
}
.tt-score-foot {
  font-size: 0.78rem;
  color: #6B7280;
  margin: 2px 2px 0;
}

@media (max-width: 900px) {
  .dash-kpis { grid-template-columns: 1fr; gap: 8px; }
  .dash-kpi .v { font-size: 1.55rem; }
  .lb-fyc { font-size: 1.25rem; }
  .lb-avatar { width: 44px; height: 44px; }
  .tt-score-value { font-size: 1.85rem; }
}

/* ---- iPhone / iPad ---- */
@media (max-width: 900px) {
  h1 { font-size: 1.7rem !important; }
  h2 { font-size: 1.4rem !important; }
  h3 { font-size: 1.2rem !important; }

  [data-testid="stAppViewContainer"] {
    background:
      radial-gradient(700px 280px at 0% 0%, #F8EFC8 0%, transparent 55%),
      var(--bg) !important;
  }

  /* Comfortable thumb targets */
  div.stButton > button {
    min-height: 48px !important;
    font-size: 1.02rem !important;
    border-radius: 12px !important;
  }
  [data-testid="stSidebar"] div.stButton > button {
    min-height: 46px !important;
  }
  .stTextInput > div > div > input,
  .stTextArea > div > div > textarea,
  .stSelectbox > div > div {
    min-height: 44px !important;
    font-size: 16px !important; /* prevents iOS zoom-on-focus */
  }

  .tt-hero {
    border-radius: 14px;
    padding: 18px 16px 16px;
    margin-bottom: 12px;
  }
  .tt-card {
    padding: 14px;
    margin-bottom: 8px;
  }
  .tt-value { font-size: 1.45rem; }
  .login-panel {
    padding: 20px 16px;
    border-radius: 14px;
  }
  .tt-login-shell {
    border-radius: 16px !important;
    padding: 32px 18px 28px !important;
    margin-bottom: 14px !important;
  }
  .tt-login-brand {
    font-size: 0.95rem !important;
    letter-spacing: 0.22em !important;
  }
  .tt-login-shell h1,
  .tt-login-title {
    font-size: 1.9rem !important;
  }
  .activity-card { padding: 12px; }
  .act-badge { font-size: 0.72em; max-width: 46%; text-align: right; }
  .reward-card-premium { padding: 18px 14px; margin-bottom: 12px; }
  .challenge-header-box { padding: 14px; }

  /* Streamlit blocks: less side padding feel */
  .block-container {
    padding-top: 1rem !important;
    padding-left: 0.9rem !important;
    padding-right: 0.9rem !important;
    padding-bottom: 5rem !important; /* space above iOS home indicator */
  }

  /* Dataframes scroll horizontally instead of crushing layout */
  [data-testid="stDataFrame"] { overflow-x: auto; }
}

@media (max-width: 480px) {
  h1 { font-size: 1.5rem !important; }
  .tt-hero h1 { font-size: 1.45rem !important; }
  .tt-kicker { font-size: 0.7rem; }
}

/* Standalone home-screen mode */
html[data-tt-standalone="1"] header[data-testid="stHeader"] {
  background: transparent !important;
}
html[data-tt-standalone="1"] .block-container {
  padding-top: calc(0.75rem + env(safe-area-inset-top)) !important;
  padding-bottom: calc(4.5rem + env(safe-area-inset-bottom)) !important;
}

/* Medical finance step pills */
.mf-steps { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 14px 0; font-size:13px; }
.mf-step {
  background: #F3F4F6; color: #374151;
  padding: 6px 12px; border-radius: 999px;
}
.mf-step-active {
  background: #1a1a2e; color: #F5D76E;
}

/* ---- iPhone / system Dark Mode ----
   Streamlit widgets flip to light text; our light surfaces must follow
   or labels become white-on-white (see 醫療融資 on iOS night mode). */
@media (prefers-color-scheme: dark) {
  :root {
    --gold: #E0C15A;
    --gold-deep: #C5A028;
    --gold-soft: #3A3420;
    --ink: #E8EAED;
    --muted: #9CA3AF;
    --line: #2F3A48;
    --surface: #1A222D;
    --bg: #0F1419;
    --ok: #34D399;
    --warn: #FBBF24;
    --danger: #F87171;
  }

  html, body {
    color-scheme: dark;
    background: var(--bg) !important;
    color: var(--ink) !important;
  }

  [data-testid="stAppViewContainer"],
  [data-testid="stAppViewContainer"] > .main,
  .stApp {
    background:
      radial-gradient(900px 420px at 10% -10%, rgba(212,175,55,0.12) 0%, transparent 55%),
      radial-gradient(700px 360px at 100% 0%, rgba(60,90,140,0.18) 0%, transparent 50%),
      var(--bg) !important;
    color: var(--ink) !important;
  }
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #141A22 0%, #0F1419 100%) !important;
    border-right: 1px solid var(--line) !important;
  }
  [data-testid="stHeader"] { background: transparent !important; }

  /* Streamlit text / labels — force readable ink on our dark surfaces */
  html, body, [class*="css"],
  p, span, label, li,
  .stMarkdown, [data-testid="stMarkdownContainer"],
  [data-testid="stMarkdownContainer"] p,
  [data-testid="stMarkdownContainer"] span,
  [data-testid="stWidgetLabel"],
  [data-testid="stWidgetLabel"] p,
  [data-testid="stCaptionContainer"],
  [data-testid="stCaptionContainer"] p,
  [data-testid="stText"],
  .stRadio label, .stCheckbox label,
  [data-baseweb="tab"] {
    color: var(--ink) !important;
  }
  h1, h2, h3, h4 {
    color: var(--ink) !important;
  }

  /* Phone top menu sticky surface — dark mode */
  [data-testid="element-container"]:has(.tt-mobile-nav)
    + [data-testid="element-container"] {
    background: rgba(15, 20, 25, 0.92);
  }
  [data-testid="element-container"]:has(.tt-mobile-nav)
    + [data-testid="element-container"] [data-testid="stPopover"] button,
  [data-testid="element-container"]:has(.tt-mobile-nav)
    + [data-testid="element-container"] button[kind="secondary"] {
    background: var(--surface) !important;
    color: var(--ink) !important;
    border-color: var(--line) !important;
  }

  /* Sidebar button nav — dark mode */
  [data-testid="stSidebar"] div.stButton > button,
  [data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
    background: var(--surface) !important;
    color: var(--ink) !important;
    border: 1.5px solid var(--line) !important;
  }
  [data-testid="stSidebar"] div.stButton > button:hover {
    background: rgba(197, 160, 40, 0.14) !important;
    border-color: #C5A028 !important;
  }
  .tt-nav-item {
    background: var(--surface) !important;
    border-color: var(--line) !important;
  }
  .tt-nav-item-active {
    background: rgba(197, 160, 40, 0.12) !important;
    border: 1px solid #C5A028 !important;
    box-shadow: none !important;
  }
  .tt-nav-item-active .tt-nav-text { color: #F5E6B8 !important; }
  .tt-side-kicker { color: var(--gold) !important; }
  .tt-side-user, .tt-side-nav-label { color: var(--ink) !important; }
  .tt-side-role { color: var(--muted) !important; }

  /* Inputs — keep contrast with dark fields */
  .stTextInput input, .stTextArea textarea,
  .stNumberInput input, .stSelectbox [data-baseweb="select"] > div,
  [data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
    background-color: #121820 !important;
    color: var(--ink) !important;
    border-color: var(--line) !important;
    -webkit-text-fill-color: var(--ink) !important;
  }
  .stTextInput input::placeholder, .stTextArea textarea::placeholder {
    color: #8B93A0 !important;
    -webkit-text-fill-color: #8B93A0 !important;
  }

  div.stButton > button[kind="secondary"] {
    background: var(--surface) !important;
    color: var(--ink) !important;
    border: 1px solid var(--line) !important;
  }
  /* Keep sidebar nav framed in dark mode (override secondary chrome above) */
  [data-testid="stSidebar"] div.stButton > button,
  [data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
    background: var(--surface) !important;
    border: 1.5px solid var(--line) !important;
    color: var(--ink) !important;
    box-shadow: none !important;
  }

  /* Expanders / tabs / metrics */
  [data-testid="stExpander"],
  [data-testid="stExpander"] details,
  [data-testid="stMetric"],
  [data-testid="stMetricValue"],
  [data-testid="stMetricLabel"] {
    color: var(--ink) !important;
  }
  [data-testid="stExpander"] summary,
  [data-testid="stExpander"] summary span,
  [data-testid="stExpander"] summary p {
    color: var(--ink) !important;
  }

  /* Alerts */
  [data-testid="stAlert"] { color: var(--ink) !important; }

  /* Custom cards */
  .tt-card, .activity-card, .dash-kpi, .lb-card, .offer-table-wrap, .tt-score-card {
    background: var(--surface) !important;
    border-color: var(--line) !important;
    color: var(--ink) !important;
  }
  .tt-label, .tt-hint, .dash-kpi .k, .act-time,
  .tt-score-kicker, .tt-score-hint, .tt-score-foot { color: var(--muted) !important; }
  .tt-value, .dash-kpi .v, .act-name, .lb-name, .lb-fyc, .tt-score-value {
    color: var(--ink) !important;
  }
  .tt-score-bar { background: #2A3340 !important; }
  .act-content {
    background: #121820 !important;
    color: var(--ink) !important;
  }
  .tt-progress-wrap, .lb-bar-track { background: #2A3340 !important; }

  .reward-card-premium {
    background: linear-gradient(145deg, #1A222D, #1E2633) !important;
    border-color: var(--gold) !important;
  }
  .reward-desc-p { color: var(--muted) !important; }
  .challenge-header-box {
    background: linear-gradient(to right, #2A2414, #1A222D) !important;
    color: var(--ink) !important;
  }
  .offer-section-title { color: var(--ink) !important; }
  .offer-table td { color: var(--ink) !important; border-color: var(--line) !important; }
  .offer-table tr:nth-child(even) td { background: #141A22 !important; }

  .mf-step {
    background: #243041 !important;
    color: #D1D5DB !important;
  }
  .mf-step-active {
    background: #F5D76E !important;
    color: #1a1a2e !important;
  }

  /* Login shell stays dark ink with light text (already dark) */
  .tt-login-foot { color: var(--muted) !important; }

  @media (max-width: 900px) {
    [data-testid="stAppViewContainer"] {
      background:
        radial-gradient(700px 280px at 0% 0%, rgba(212,175,55,0.10) 0%, transparent 55%),
        var(--bg) !important;
    }
  }
}
</style>
"""

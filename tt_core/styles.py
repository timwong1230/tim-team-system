"""CSS theme for TIM TEAM system."""

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Instrument+Serif:ital@0;1&display=swap');

:root {
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
  background: linear-gradient(180deg, #FFFFFF 0%, #FBF9F4 100%) !important;
  border-right: 1px solid var(--line);
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

div[role="radiogroup"] > label > div:first-child { display: none !important; }
div[role="radiogroup"] label {
  background: var(--surface) !important;
  padding: 11px 14px !important;
  margin-bottom: 6px !important;
  border-radius: 10px !important;
  border: 1px solid var(--line) !important;
  transition: all 0.2s ease !important;
  width: 100% !important;
}
div[role="radiogroup"] label:hover {
  border-color: var(--gold) !important;
  background: var(--gold-soft) !important;
  transform: translateX(3px);
}

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
.tt-mobile-nav {
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(243,241,235,0.92);
  backdrop-filter: blur(10px);
  padding: 6px 0 10px;
  margin-bottom: 8px;
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
@media (max-width: 900px) {
  .dash-kpis { grid-template-columns: 1fr; gap: 8px; }
  .dash-kpi .v { font-size: 1.55rem; }
  .lb-fyc { font-size: 1.25rem; }
  .lb-avatar { width: 44px; height: 44px; }
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
  div[role="radiogroup"] label {
    padding: 14px 14px !important;
    min-height: 48px;
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
</style>
"""

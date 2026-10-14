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
.ammo-nightmare { background-color: #fdedec; border-left: 4px solid #e74c3c; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
.ammo-dream { background-color: #eafaf1; border-left: 4px solid #2ecc71; padding: 15px; border-radius: 5px; margin-bottom: 10px; }

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
</style>
"""

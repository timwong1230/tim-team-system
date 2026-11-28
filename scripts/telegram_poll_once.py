#!/usr/bin/env python3
"""One-shot Telegram Coach Tim poll (for cron / manual ops).

Requires bot token in env TELEGRAM_BOT_TOKEN or Streamlit-style settings
via coach_tim_telegram_bot_token in the Sheets-backed system_settings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from tt_core import telegram_coach as tg

    env_tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if env_tok:
        tg.save_bot_token(env_tok)

    if not tg.bot_configured():
        print("missing bot token (set TELEGRAM_BOT_TOKEN)", file=sys.stderr)
        return 2

    result = tg.poll_once(limit=50, timeout=0)
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

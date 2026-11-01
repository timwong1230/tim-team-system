"""Past-day Daily reports must survive wiping live sessions."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_past_day_report_survives_reset_via_snapshot():
    tmp = tempfile.mkdtemp(prefix="polar-snap-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.reports as reports

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(reports)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    pin = "polar2026"
    with TestClient(main.app) as client:
        assert (
            client.post(
                "/api/t/TABLE1/welcome", json={"guest_name": "Pat", "party_size": 2}
            ).status_code
            == 200
        )
        conn = db.connect()
        t1 = conn.execute("SELECT id FROM tables WHERE code='TABLE1'").fetchone()["id"]
        s1 = conn.execute(
            "SELECT id FROM sessions WHERE table_id=? AND status='open'", (t1,)
        ).fetchone()["id"]
        conn.execute(
            """
            UPDATE sessions SET status='closed', total=19187, payment_method='Visa',
              business_date='2026-10-31', closed_at='2026-10-31T20:00:00+08:00',
              party_size=2, guest_name='Pat'
            WHERE id=?
            """,
            (s1,),
        )
        conn.commit()

        # Write a fake receipt PDF so post-reset PDF links still resolve.
        from app.paths import RECEIPT_DIR

        RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = RECEIPT_DIR / f"receipt-S{s1}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake polar receipt")
        conn.execute(
            "UPDATE sessions SET receipt_path = ? WHERE id = ?",
            (f"receipts/receipt-S{s1}.pdf", s1),
        )
        conn.commit()

        live = reports.daily_sales_report(conn, date(2026, 10, 31))
        assert live["gross_sales"] == 19187.0
        assert live["from_snapshot"] is False
        assert db.get_daily_report_snapshot(conn, "2026-10-31") is not None

        # Staff/test reset wipes live sessions but keeps snapshots + PDFs.
        cleared = db.reset_operational_data(conn)
        assert cleared["sessions"] >= 1
        assert cleared["daily_report_snapshots_kept"] >= 1
        assert cleared.get("receipts_kept") is True
        assert pdf_path.exists()
        assert (
            conn.execute(
                "SELECT COUNT(*) AS c FROM sessions WHERE status='closed'"
            ).fetchone()["c"]
            == 0
        )

        restored = reports.daily_sales_report(conn, date(2026, 10, 31))
        assert restored["from_snapshot"] is True
        assert restored["gross_sales"] == 19187.0
        assert restored["session_count"] == 1
        assert restored["sessions"][0]["receipt_path"]
        conn.close()

        page = client.get(f"/staff/reports?pin={pin}&day=2026-10-31")
        assert page.status_code == 200
        assert b"19187" in page.content
        assert b"snapshot" in page.content.lower() or "存檔".encode() in page.content
        assert f"/staff/receipt/{s1}".encode() in page.content

        pdf = client.get(f"/staff/receipt/{s1}?pin={pin}")
        assert pdf.status_code == 200, pdf.text
        assert pdf.content.startswith(b"%PDF")

        wa = client.get(
            f"/api/staff/whatsapp-sales-report?pin={pin}&day=2026-10-31"
        )
        assert wa.status_code == 200
        assert "Daily Sales: $19187" in wa.json()["message"]


def test_bare_reset_on_start_token_is_ignored(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="polar-reset-token-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"
    os.environ["POLAR_RESET_ON_START"] = "RESET"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        # Seed a closed sale, then re-hit health (app already started with ignored token).
        conn = db.connect()
        t = conn.execute("SELECT id FROM tables WHERE code='TABLE2'").fetchone()["id"]
        from app.db import start_session, utc_now

        s = start_session(conn, t, "Keep", 2)
        conn.execute(
            """
            UPDATE sessions SET status='closed', total=50, payment_method='Cash',
              business_date='2026-11-01', closed_at=? WHERE id=?
            """,
            (utc_now(), s["id"]),
        )
        conn.commit()
        conn.close()

        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["closed_sessions"] >= 1
        assert body["db_exists"] is True

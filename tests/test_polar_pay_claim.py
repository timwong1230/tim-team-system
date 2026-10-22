"""Mark paid requires payment method; nightly claims on reports."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_payment_method_and_claims():
    tmp = tempfile.mkdtemp(prefix="polar-pay-claim-")
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

    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from app.ops_constants import CLAIM_PRESETS, PAYMENT_METHODS
    from app.pricing import business_date

    pin = "polar2026"
    with TestClient(main.app) as client:
        client.post(
            "/api/t/TABLE5/welcome",
            json={"guest_name": "Pat", "party_size": 2},
        )
        client.post(
            "/api/t/TABLE5/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )

        bill = client.get(f"/staff/bill/TABLE5?pin={pin}")
        assert bill.status_code == 200
        assert b"Payment method" in bill.content
        for m in PAYMENT_METHODS:
            assert m.encode() in bill.content

        missing = client.post(
            "/api/staff/bill/TABLE5/close",
            data={"pin": pin, "discount_percent": 0},
        )
        assert missing.status_code == 422

        bad = client.post(
            "/api/staff/bill/TABLE5/close",
            data={"pin": pin, "discount_percent": 0, "payment_method": "Bitcoin"},
        )
        assert bad.status_code == 400

        closed = client.post(
            "/api/staff/bill/TABLE5/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "payment_method": "AlipayHK",
            },
        )
        assert closed.status_code == 200, closed.text
        payload = closed.json()
        assert payload["ok"] is True
        sid = payload["session_id"]

        conn = db.connect()
        row = conn.execute(
            "SELECT payment_method, total FROM sessions WHERE id = ?", (sid,)
        ).fetchone()
        assert row["payment_method"] == "AlipayHK"
        assert float(row["total"] or 0) > 0
        conn.close()

        day = business_date(datetime.now(ZoneInfo("Asia/Hong_Kong"))).isoformat()
        for preset in CLAIM_PRESETS:
            assert preset  # sanity

        add = client.post(
            "/api/staff/claims",
            json={
                "pin": pin,
                "business_date": day,
                "category": "Staff Meal",
                "amount": 120,
            },
        )
        assert add.status_code == 200, add.text
        claim_id = add.json()["claim"]["id"]

        custom = client.post(
            "/api/staff/claims",
            json={
                "pin": pin,
                "business_date": day,
                "custom_name": "Napkins",
                "amount": 40,
            },
        )
        assert custom.status_code == 200, custom.text
        assert custom.json()["claim"]["category"] == "Napkins"
        assert custom.json()["claims_total"] == 160

        page = client.get(f"/staff/reports?pin={pin}&day={day}")
        assert page.status_code == 200
        assert b"Staff Meal" in page.content
        assert b"Napkins" in page.content
        assert b"AlipayHK" in page.content
        assert b"Claims" in page.content

        deleted = client.delete(f"/api/staff/claims/{claim_id}?pin={pin}")
        assert deleted.status_code == 200

        conn = db.connect()
        left = db.list_claims(conn, day)
        conn.close()
        assert len(left) == 1
        assert left[0]["category"] == "Napkins"

"""Edit a closed bill even when the same seat already has a new open party."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
sys.path = [str(_POLAR)] + [p for p in sys.path if Path(p).resolve() != _ROOT]
for _name in list(sys.modules):
    if _name == "app" or _name.startswith("app."):
        del sys.modules[_name]


def test_edit_old_boss_credit_while_new_party_open():
    tmp = tempfile.mkdtemp(prefix="polar-edit-alongside-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"
    os.environ["POLAR_BILL_EDIT_PASSWORD"] = "polar2019"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.ops_constants as ops
    import app.reports as reports

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(ops)
    importlib.reload(reports)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    from app.seats import boss_seat_code

    pin = "polar2026"
    seat = boss_seat_code("jon")
    assert seat == "BOSSJON"

    with TestClient(main.app) as client:
        first = client.post(
            f"/api/staff/bill/{seat}/orders",
            json={"pin": pin, "items": [{"item_id": "coke", "qty": 1}]},
        )
        assert first.status_code == 200, first.text
        closed = client.post(
            f"/api/staff/bill/{seat}/close",
            data={"pin": pin, "discount_percent": 0},
        )
        assert closed.status_code == 200, closed.text
        old_id = int(closed.json()["session_id"])

        second = client.post(
            f"/api/staff/bill/{seat}/orders",
            json={"pin": pin, "items": [{"item_id": "shisha-regular", "qty": 1}]},
        )
        assert second.status_code == 200, second.text

        conn = db.connect()
        live = db.get_open_session(
            conn,
            db.get_table_by_code(conn, seat)["id"],
        )
        live_id = int(live["id"])
        conn.close()
        assert live_id != old_id

        blocked_before = "already has an open party"
        reopen = client.post(
            f"/api/staff/sessions/{old_id}/reopen-edit",
            json={"pin": pin, "edit_password": "polar2019"},
        )
        assert reopen.status_code == 200, reopen.text
        assert blocked_before not in reopen.text
        body = reopen.json()
        assert body["edit_session"] == old_id
        assert f"edit_session={old_id}" in body["redirect"]

        conn = db.connect()
        old = db.get_session(conn, old_id)
        live_after = db.get_session(conn, live_id)
        conn.close()
        assert old["status"] == "editing"
        assert live_after["status"] == "open"

        page = client.get(body["redirect"])
        assert page.status_code == 200
        assert "改緊舊單".encode() in page.content
        assert b"Coke" in page.content or b"coke" in page.content.lower()
        assert f'name="edit_session" value="{old_id}"'.encode() in page.content

        conn = db.connect()
        row = conn.execute(
            """
            SELECT oi.id FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.session_id = ? AND o.status != 'cancelled'
            """,
            (old_id,),
        ).fetchone()
        conn.close()
        up = client.post(
            f"/api/staff/bill/{seat}/items/{row['id']}",
            json={"pin": pin, "qty": 3, "edit_session": old_id},
        )
        assert up.status_code == 200, up.text

        closed_again = client.post(
            f"/api/staff/bill/{seat}/close",
            data={"pin": pin, "discount_percent": 0, "edit_session": str(old_id)},
        )
        assert closed_again.status_code == 200, closed_again.text
        assert int(closed_again.json()["session_id"]) == old_id
        assert float(closed_again.json()["total"]) > float(closed.json()["total"])

        conn = db.connect()
        old2 = db.get_session(conn, old_id)
        live2 = db.get_session(conn, live_id)
        conn.close()
        assert old2["status"] == "closed"
        assert old2["payment_method"] == "Credit"
        assert live2["status"] == "open"

"""Staff booking schedule — calendar + admin create/cancel."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_staff_booking_schedule_api_and_page():
    tmp = tempfile.mkdtemp(prefix="polar-bookings-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    pin = "polar2026"
    with TestClient(main.app) as client:
        page = client.get(f"/staff/bookings?pin={pin}&month=2027-03&day=2027-03-15")
        assert page.status_code == 200
        assert b"Booking Schedule" in page.content
        assert b"booking-cal" in page.content
        assert b"Add booking" in page.content

        board = client.get(f"/staff/board?pin={pin}")
        assert board.status_code == 200
        assert b"Booking Schedule" in board.content

        bad = client.post(
            "/api/staff/bookings",
            json={
                "pin": "wrong",
                "guest_name": "Alex",
                "party_size": 4,
                "booking_date": "2027-03-15",
                "booking_time": "20:00",
            },
        )
        assert bad.status_code == 401

        created = client.post(
            "/api/staff/bookings",
            json={
                "pin": pin,
                "guest_name": "Alex Chen",
                "party_size": 4,
                "booking_date": "2027-03-15",
                "booking_time": "20:30",
                "note": "+852 9000 1111 · window",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["ok"] is True
        booking_id = body["booking"]["id"]
        assert body["booking"]["guest_name"] == "Alex Chen"
        assert body["booking"]["booking_time"] == "20:30"

        day_page = client.get(f"/staff/bookings?pin={pin}&month=2027-03&day=2027-03-15")
        assert day_page.status_code == 200
        assert b"Alex Chen" in day_page.content
        assert b"20:30" in day_page.content
        assert b"+852 9000 1111" in day_page.content

        updated = client.put(
            f"/api/staff/bookings/{booking_id}",
            json={
                "pin": pin,
                "guest_name": "Alex Chen",
                "party_size": 6,
                "booking_date": "2027-03-15",
                "booking_time": "21:00",
                "note": "Updated note",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["booking"]["party_size"] == 6
        assert updated.json()["booking"]["booking_time"] == "21:00"

        cancelled = client.post(
            f"/api/staff/bookings/{booking_id}/status",
            json={"pin": pin, "status": "cancelled"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["booking"]["status"] == "cancelled"

        gone = client.get(f"/staff/bookings?pin={pin}&month=2027-03&day=2027-03-15")
        assert b"Alex Chen" not in gone.content

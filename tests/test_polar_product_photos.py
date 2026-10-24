"""Uploaded venue product photos map onto menu image files + brand names."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_key_product_photos_and_renames():
    tmp = tempfile.mkdtemp(prefix="polar-photos-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    menu_dir = _POLAR / "static" / "images" / "menu"
    for name in (
        "shisha-regular.jpg",
        "corona.jpg",
        "grey-goose.jpg",
        "patron.jpg",
        "coke.jpg",
        "jessy-vodka.jpg",
        "cuervo.jpg",
        "sprite.jpg",
        "pellegrino.jpg",
    ):
        path = menu_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 50_000, name

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Photo", "party_size": 1},
        )
        page = client.get("/t/TABLE1")
        assert page.status_code == 200
        html = page.text
        assert "Krupnik" in html
        assert "El Tio Juan Blanco" in html
        assert "7up" in html
        assert "Chang Soda Water" in html
        assert "Jose Cuervo" not in html
        assert f"grey-goose.jpg?v={main.ASSET_VERSION}" in html

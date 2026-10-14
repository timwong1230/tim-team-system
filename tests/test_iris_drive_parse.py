"""Folder ID parsing helpers."""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_save_folder_id_parses_url():
    import tt_core.iris_drive as d

    saved = {}

    def fake_set(key, value):
        saved["key"] = key
        saved["value"] = value
        return True

    with patch.object(d, "set_setting", side_effect=fake_set):
        assert d.save_folder_id(
            "https://drive.google.com/drive/folders/1AbCdEfGhIjK?usp=sharing"
        )
        assert saved["value"] == "1AbCdEfGhIjK"
        assert d.save_folder_id("1AbCdEfGhIjK")
        assert saved["value"] == "1AbCdEfGhIjK"
    print("iris_drive parse ok")


if __name__ == "__main__":
    test_save_folder_id_parses_url()

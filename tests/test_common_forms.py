"""Unit tests for 常用表格 helpers (no live Drive required)."""

from __future__ import annotations

from tt_core.common_forms import (
    ALLOWED_EXT,
    CATEGORIES,
    _normalize_folder_id,
    _quota_error,
    ensure_view_link,
    format_size,
    share_file_anyone,
    share_all_catalog_files,
)


def test_categories_include_signing_and_admin():
    assert "簽單表格" in CATEGORIES
    assert "行政文件" in CATEGORIES
    assert "培訓工具" in CATEGORIES
    assert "招募工具" in CATEGORIES
    assert "產品資料" in CATEGORIES
    assert "Sales Kit" in CATEGORIES
    assert "培訓資料" not in CATEGORIES


def test_allowed_ext_covers_common_office_files():
    for ext in (".pdf", ".docx", ".xlsx", ".png", ".zip"):
        assert ext in ALLOWED_EXT


def test_format_size():
    assert format_size(500) == "500 B"
    assert format_size(2048).endswith("KB")
    assert format_size(3 * 1024 * 1024).endswith("MB")
    assert format_size("bad") == "—"


def test_normalize_folder_id_from_url():
    url = "https://drive.google.com/drive/folders/abc123XYZ?usp=sharing"
    assert _normalize_folder_id(url) == "abc123XYZ"
    assert _normalize_folder_id("  plainId  ") == "plainId"


def test_quota_error_detection():
    assert _quota_error(
        Exception(
            "HttpError 403 when requesting ... "
            "Service Accounts do not have storage quota. ... storageQuotaExceeded"
        )
    )
    assert not _quota_error(Exception("permission denied"))


def test_ensure_view_link_shape():
    url = ensure_view_link("abc123FileId")
    assert url.startswith("https://drive.google.com/file/d/abc123FileId/view")
    assert ensure_view_link("") == ""


def test_share_helpers_exist():
    assert callable(share_file_anyone)
    assert callable(share_all_catalog_files)
    assert share_file_anyone("") is False

"""Mark paid opens PDF receipt in a new browser tab."""

from __future__ import annotations

from pathlib import Path


def test_mark_paid_opens_receipt_in_new_window():
    html = (
        Path(__file__).resolve().parents[1]
        / "polar-order"
        / "templates"
        / "staff_bill.html"
    ).read_text(encoding="utf-8")
    assert "window.open(data.receipt_url, '_blank'" in html
    assert "noopener,noreferrer" in html
    # Current tab returns to tables after opening the PDF
    assert html.count("location.href = '/staff/tables?pin={{ pin }}'") >= 1
    # Must not navigate the current tab to the PDF
    assert "window.location.href = data.receipt_url" not in html

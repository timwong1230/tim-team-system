from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

HK = ZoneInfo("Asia/Hong_Kong")
ROOT = Path(__file__).resolve().parents[1]
RECEIPT_DIR = ROOT / "data" / "receipts"


def _money(n: float) -> str:
    return f"HKD {n:,.1f}".replace(".0", "") if float(n).is_integer() else f"HKD {n:,.1f}"


def generate_receipt_pdf(
    *,
    session_id: int,
    table_label: str,
    party_size: int,
    lines: list[dict],
    bill: dict,
    closed_at_iso: str,
    guest_name: str | None = None,
) -> str:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = RECEIPT_DIR / f"receipt-S{session_id}.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 20 * mm

    def line(txt: str, size: int = 10, bold: bool = False, gap: float = 5.5):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(18 * mm, y, txt)
        y -= gap * mm

    c.setFillColor(colors.HexColor("#1a1530"))
    c.rect(0, height - 28 * mm, width, 28 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(18 * mm, height - 14 * mm, "POLAR LOUNGE")
    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, height - 20 * mm, "16/F L Square · Causeway Bay · Receipt")

    c.setFillColor(colors.black)
    y = height - 36 * mm
    try:
        closed = datetime.fromisoformat(closed_at_iso)
        if closed.tzinfo is None:
            closed = closed.replace(tzinfo=HK)
        closed_local = closed.astimezone(HK).strftime("%Y-%m-%d %H:%M")
    except Exception:
        closed_local = closed_at_iso

    line(f"Seat: {table_label}", bold=True, size=12)
    if guest_name:
        line(f"Guest: {guest_name}", bold=True, size=11)
    line(f"Session #{session_id} · Party {party_size}")
    line(f"Closed: {closed_local}")
    line(f"Receipt: R-{session_id:05d}")
    y -= 2 * mm
    c.setStrokeColor(colors.HexColor("#d4c08c"))
    c.line(18 * mm, y, width - 18 * mm, y)
    y -= 6 * mm

    line("Items", bold=True, size=11)
    for item in lines:
        name = f"{item['qty']}x {item['item_name']}"
        if len(name) > 48:
            name = name[:45] + "..."
        c.setFont("Helvetica", 9)
        c.drawString(18 * mm, y, name)
        c.drawRightString(width - 18 * mm, y, _money(float(item["line_total"])))
        y -= 4.5 * mm
        if item.get("note"):
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.grey)
            c.drawString(22 * mm, y, str(item["note"])[:60])
            c.setFillColor(colors.black)
            y -= 4 * mm
        if y < 40 * mm:
            c.showPage()
            y = height - 20 * mm

    y -= 2 * mm
    c.setStrokeColor(colors.HexColor("#d4c08c"))
    c.line(18 * mm, y, width - 18 * mm, y)
    y -= 7 * mm

    def row(label: str, value: float, bold: bool = False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
        c.drawString(18 * mm, y, label)
        c.drawRightString(width - 18 * mm, y, _money(value))
        y -= 5.5 * mm

    row("Subtotal (products)", bill["subtotal"])
    if bill.get("discount_percent"):
        row(
            f"Discount {int(bill['discount_percent'])}% (products + snacks)",
            -float(bill["discount_amount"]),
        )
    row(f"Snack charge ({bill['party_size']} × $10)", bill["snack_charge"])
    row(
        f"Service {int(bill['service_charge_rate'] * 100)}% (on full price)",
        bill["service_charge"],
    )
    row("Amount due", bill["total"], bold=True)

    y -= 8 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawString(18 * mm, y, "Thank you for visiting Polar Lounge.")
    y -= 4 * mm
    c.drawString(18 * mm, y, "Payment collected separately. Keep this receipt for your records.")
    c.save()
    return str(path.relative_to(ROOT))

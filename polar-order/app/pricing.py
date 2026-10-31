from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")

SHISHA_COMBO_SNACK_PRICE = 40.0
SHISHA_REGULAR_ID = "shisha-regular"
FREE_FLOW_CATEGORY_ID = "free-flow"


def _line_is_free_flow(line: dict) -> bool:
    """Free Flow packages do not attract the 10% service charge."""
    return (line.get("category_id") or "") == FREE_FLOW_CATEGORY_ID


def current_promo(now: datetime | None = None) -> dict:
    """
    Polar time-based pricing (HK):
    - 2pm–5pm Meditation: Shisha $250, drinks 30% off
    - 5pm–8pm Happy Hour: drinks 20% off
    - after 8pm (and before 2pm): regular price
    """
    now = now or datetime.now(HK)
    minutes = now.hour * 60 + now.minute
    if 14 * 60 <= minutes < 17 * 60:
        return {
            "id": "meditation",
            "label": "Meditation Hour",
            "window": "2pm–5pm",
            "drinks_off": 0.30,
            "drinks_label": "30% OFF",
            "shisha_price": 250.0,
            "snack_combo_price": SHISHA_COMBO_SNACK_PRICE,
        }
    if 17 * 60 <= minutes < 20 * 60:
        return {
            "id": "happy_hour",
            "label": "Happy Hour",
            "window": "5pm–8pm",
            "drinks_off": 0.20,
            "drinks_label": "20% OFF",
            "shisha_price": None,
            "snack_combo_price": SHISHA_COMBO_SNACK_PRICE,
        }
    return {
        "id": "regular",
        "label": "Regular pricing",
        "window": "after 8pm",
        "drinks_off": 0.0,
        "drinks_label": None,
        "shisha_price": None,
        "snack_combo_price": SHISHA_COMBO_SNACK_PRICE,
    }


def price_item(
    base_price: float,
    promo_type: str,
    promo: dict,
    *,
    item_id: str | None = None,
) -> tuple[float, str | None]:
    """Return (final_price, promo_tag) for a single item (no snack-combo logic)."""
    if promo_type == "shisha":
        # Meditation special only for Regular Shisha
        if item_id == SHISHA_REGULAR_ID and promo.get("shisha_price") is not None:
            return float(promo["shisha_price"]), promo["label"]
        return float(base_price), None
    if promo_type == "drinks" and promo.get("drinks_off"):
        discounted = round(base_price * (1 - float(promo["drinks_off"])), 1)
        tag = promo.get("drinks_label") or promo.get("label")
        return discounted, tag
    return float(base_price), None


def price_order_lines(
    entries: list[dict],
    *,
    promo: dict | None = None,
    extra_shisha_slots: int = 0,
) -> list[dict]:
    """
    Price a list of cart entries.

    each entry: {
      item_id, name, category_id, promo, base_price, qty, note?
    }

    Shisha combo: each Regular Shisha unlocks one bar snack at $40
    (slots from this cart + extra_shisha_slots from open session).
    """
    promo = promo or current_promo()
    combo_price = float(promo.get("snack_combo_price") or SHISHA_COMBO_SNACK_PRICE)

    cart_shisha = sum(
        int(e["qty"])
        for e in entries
        if e["item_id"] == SHISHA_REGULAR_ID
    )
    slots = max(0, int(extra_shisha_slots) + cart_shisha)

    # Expand snacks into unit slots so we can apply combo per portion
    priced: list[dict] = []
    snack_queue: list[dict] = []

    for e in entries:
        promo_type = e.get("promo") or "none"
        unit, tag = price_item(
            float(e["base_price"]),
            promo_type,
            promo,
            item_id=e["item_id"],
        )
        row = {
            "item_id": e["item_id"],
            "item_name": e["name"],
            "category_id": e["category_id"],
            "promo": promo_type,
            "qty": int(e["qty"]),
            "unit_price": float(unit),
            "note": e.get("note"),
            "promo_tag": tag,
        }
        if promo_type == "snacks":
            snack_queue.append({**row, "list_price": float(e["base_price"])})
        else:
            if tag:
                note = f"[{tag}] {row['note'] or ''}".strip()
                row["note"] = note
            row["line_total"] = round(row["unit_price"] * row["qty"], 1)
            priced.append(row)

    # Apply $40 combo to as many snack units as shisha slots allow
    for snack in snack_queue:
        qty = snack["qty"]
        combo_qty = min(qty, slots)
        slots -= combo_qty
        full_qty = qty - combo_qty
        if combo_qty:
            note = f"[Shisha combo $40] {snack['note'] or ''}".strip()
            priced.append(
                {
                    **snack,
                    "qty": combo_qty,
                    "unit_price": combo_price,
                    "line_total": round(combo_price * combo_qty, 1),
                    "note": note,
                    "promo_tag": "Shisha combo",
                }
            )
        if full_qty:
            priced.append(
                {
                    **snack,
                    "qty": full_qty,
                    "unit_price": float(snack["list_price"]),
                    "line_total": round(float(snack["list_price"]) * full_qty, 1),
                    "promo_tag": None,
                }
            )

    return priced


def compute_bill(
    lines: list[dict],
    party_size: int,
    service_charge_rate: float = 0.1,
    snack_charge_per_head: float = 10.0,
    discount_percent: float = 0.0,
    snack_waived: bool = False,
) -> dict:
    """
    discount_percent: 0 = full price, 10 = 10% off, 20 = 20% off.

    - Discount applies to products + snack charge (not service).
    - Service charge is on (non–Free Flow products + snack) × rate.
      Free Flow packages have no 10% service charge.
    - snack_waived: guest declined bar snacks → $0 snack charge.
    """
    subtotal = round(sum(float(x["line_total"]) for x in lines), 1)
    serviceable_subtotal = round(
        sum(float(x["line_total"]) for x in lines if not _line_is_free_flow(x)),
        1,
    )
    if snack_waived:
        snack_charge = 0.0
    else:
        snack_charge = round(max(1, party_size) * snack_charge_per_head, 1)
    discount_base = round(subtotal + snack_charge, 1)
    service_base = round(serviceable_subtotal + snack_charge, 1)
    service = round(service_base * service_charge_rate, 1)
    try:
        disc = max(0.0, min(100.0, float(discount_percent or 0)))
    except (TypeError, ValueError):
        disc = 0.0
    discount_amount = round(discount_base * (disc / 100.0), 1)
    total = round(subtotal + snack_charge + service - discount_amount, 1)
    return {
        "subtotal": subtotal,
        "serviceable_subtotal": serviceable_subtotal,
        "snack_charge": snack_charge,
        "snack_waived": bool(snack_waived),
        "service_charge": service,
        "service_charge_rate": service_charge_rate,
        "pre_discount_total": discount_base,
        "discount_percent": disc,
        "discount_amount": discount_amount,
        "total": total,
        "party_size": party_size,
    }


def business_date(dt: datetime | None = None):
    """
    Operating day is 2pm → 2am next calendar day.
    e.g. 21 Oct 15:00 and 22 Oct 01:00 both belong to business date 2026-10-21.
    """
    dt = dt or datetime.now(HK)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=HK)
    else:
        dt = dt.astimezone(HK)
    if dt.hour >= 14:
        return dt.date()
    return (dt - timedelta(days=1)).date()


def business_day_window(biz_date):
    """Return (start_inclusive, end_exclusive) as aware HK datetimes for a business date."""
    start = datetime(biz_date.year, biz_date.month, biz_date.day, 14, 0, 0, tzinfo=HK)
    end = start + timedelta(hours=12)  # 2pm → 2am next day
    return start, end

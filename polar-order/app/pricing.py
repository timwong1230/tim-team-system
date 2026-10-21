from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")


def current_promo(now: datetime | None = None) -> dict:
    """Return active promo window for Polar Lounge (HK time)."""
    now = now or datetime.now(HK)
    minutes = now.hour * 60 + now.minute
    # Meditation 14:00-17:00
    if 14 * 60 <= minutes < 17 * 60:
        return {
            "id": "meditation",
            "label": "Meditation Hour",
            "window": "2pm–5pm",
            "drinks_off": 0.30,
            "shisha_price": 250.0,
        }
    # Happy Hour 17:00-20:00
    if 17 * 60 <= minutes < 20 * 60:
        return {
            "id": "happy_hour",
            "label": "Happy Hour",
            "window": "5pm–8pm",
            "drinks_off": 0.20,
            "shisha_price": None,
        }
    return {
        "id": "none",
        "label": None,
        "window": None,
        "drinks_off": 0.0,
        "shisha_price": None,
    }


def price_item(base_price: float, promo_type: str, promo: dict) -> tuple[float, str | None]:
    """Return (final_price, promo_tag)."""
    if promo_type == "shisha" and promo.get("shisha_price") is not None:
        return float(promo["shisha_price"]), promo["label"]
    if promo_type == "drinks" and promo.get("drinks_off"):
        discounted = round(base_price * (1 - float(promo["drinks_off"])), 1)
        return discounted, promo["label"]
    return float(base_price), None


def compute_bill(
    lines: list[dict],
    party_size: int,
    service_charge_rate: float = 0.1,
    snack_charge_per_head: float = 10.0,
    discount_percent: float = 0.0,
) -> dict:
    """
    discount_percent: 0 = full price, 10 = 10% off, 20 = 20% off.

    - Discount applies to products + snack charge (not service).
    - Service charge is calculated on full price: (subtotal + snack) × rate.
    """
    subtotal = round(sum(float(x["line_total"]) for x in lines), 1)
    snack_charge = round(max(1, party_size) * snack_charge_per_head, 1)
    discount_base = round(subtotal + snack_charge, 1)
    service = round(discount_base * service_charge_rate, 1)  # full price
    try:
        disc = max(0.0, min(100.0, float(discount_percent or 0)))
    except (TypeError, ValueError):
        disc = 0.0
    discount_amount = round(discount_base * (disc / 100.0), 1)
    total = round(subtotal + snack_charge + service - discount_amount, 1)
    return {
        "subtotal": subtotal,
        "snack_charge": snack_charge,
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

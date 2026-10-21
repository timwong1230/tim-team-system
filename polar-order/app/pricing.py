from __future__ import annotations

from datetime import datetime
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
        # Only Regular Shisha uses meditation price; Change Head stays list price.
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
) -> dict:
    subtotal = round(sum(float(x["line_total"]) for x in lines), 1)
    snack_charge = round(max(1, party_size) * snack_charge_per_head, 1)
    taxable = subtotal + snack_charge
    service = round(taxable * service_charge_rate, 1)
    total = round(taxable + service, 1)
    return {
        "subtotal": subtotal,
        "snack_charge": snack_charge,
        "service_charge": service,
        "service_charge_rate": service_charge_rate,
        "total": total,
        "party_size": party_size,
    }

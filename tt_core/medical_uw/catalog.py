"""Catalog helpers for 常見疾病核保."""

from __future__ import annotations

from tt_core.medical_uw.diseases_data import DISEASES, DISCLAIMER_ZH

PRODUCT_LABELS = {
    "life": "人壽",
    "ci": "危疾",
    "medical": "醫療",
    "accident": "意外",
    "cancer": "癌症",
}


def disclaimer_text() -> str:
    return DISCLAIMER_ZH


def list_diseases() -> list[dict]:
    return list(DISEASES)


def get_disease(disease_id: str) -> dict | None:
    for d in DISEASES:
        if d["id"] == disease_id:
            return d
    return None


def search_diseases(query: str) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return list_diseases()
    out = []
    for d in DISEASES:
        blob = " ".join(
            [
                d.get("id", ""),
                d.get("name_zh", ""),
                d.get("name_en", ""),
                " ".join(d.get("keywords") or []),
            ]
        ).lower()
        if q in blob:
            out.append(d)
    return out

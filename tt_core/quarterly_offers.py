"""Quarterly customer offers & salesperson rewards.

Content is organised as table sections for field lookup.
Seeded from FWD Flash Reports (internal use). Leaders can override via the
`quarterly_offers` Google Sheet (flat title/detail/note rows).
"""

from __future__ import annotations

from datetime import date

QUARTERS = {
    "Q1": {
        "label": "第一季",
        "period": "1月 – 3月",
        "months": (1, 2, 3),
    },
    "Q2": {
        "label": "第二季",
        "period": "4月 – 6月",
        "months": (4, 5, 6),
    },
    "Q3": {
        "label": "第三季",
        "period": "7月 – 9月",
        "months": (7, 8, 9),
    },
    "Q4": {
        "label": "第四季",
        "period": "10月 – 12月",
        "months": (10, 11, 12),
    },
}

# Catalog shape per quarter/kind:
# {
#   "banner": str,
#   "footnote": str,
#   "sections": [
#     {"title": str, "columns": [str, ...], "rows": [[str, ...], ...]},
#   ],
# }
# Sources: PDM76/2026 (客戶優惠), TA261048 (理財顧問獎賞)
DEFAULT_CATALOG: dict[str, dict[str, dict]] = {
    "Q1": {"customer": {"banner": "", "footnote": "", "sections": []}, "agent": {"banner": "", "footnote": "", "sections": []}},
    "Q2": {"customer": {"banner": "", "footnote": "", "sections": []}, "agent": {"banner": "", "footnote": "", "sections": []}},
    "Q3": {"customer": {"banner": "", "footnote": "", "sections": []}, "agent": {"banner": "", "footnote": "", "sections": []}},
    "Q4": {
        "customer": {
            "banner": (
                "推廣期至 2026-12-31（保單一般須於 2027-03-31 或之前繕發）· "
                "適用月供／半年供／年供（如適用）· Ref：PDM76/2026"
            ),
            "footnote": "詳細條款以 Agency Portal 宣傳單張及官方 Flash Report 為準。",
            "sections": [
                {
                    "title": "自願醫保／醫療計劃",
                    "columns": ["產品", "優惠重點", "備註"],
                    "rows": [
                        [
                            "確衛您／更衛您",
                            "首年 3 個月保費折扣；與家人齊投保各加 1 個月",
                            "",
                        ],
                        [
                            "倍衛您／尊衛您（寰譽版）",
                            "自付費 0：首年 3 個月\n"
                            "自付費 <$100k：首年 5／次年 3／第 3 年 2 個月\n"
                            "自付費 ≥$100k：首年 5／次年 4／第 3 年 3 個月\n"
                            "齊投保：首年各加 1 個月",
                            "自付費檔位見官方表",
                        ],
                        [
                            "醫家保（無子女選項）",
                            "首年 3 個月保費折扣",
                            "",
                        ],
                        [
                            "醫家保 + 子女之家添守護「9+9」",
                            "主計劃首兩年各 3 個月；子女選項首兩年各 6 個月\n"
                            "齊投保：主計劃首年加 1 個月（不含子女選項保費）",
                            "子女選項非 VHIS／不適用稅務扣減",
                        ],
                        [
                            "人仁保「雙重賞」（年繳）",
                            "入門：首兩年各 6 個月 + 疫苗券 $200（第 2／3 年）\n"
                            "昇華：首兩年各 3 個月 + 疫苗券 $600（第 2 年）\n"
                            "薈亞：首兩年各 3 個月 + 疫苗券 $1,000（第 2 年）\n"
                            "父母之家添守護：首兩年各 6 個月 + 疫苗券 $400",
                            "父母選項僅薈亞級別",
                        ],
                        [
                            "智員善—智．升",
                            "首年及第 2 年各 6 個月保費折扣",
                            "須於 2027-01-31 或之前繕發",
                        ],
                        [
                            "跨越．無界醫療臻薈",
                            "首年 3 個月保費折扣",
                            "",
                        ],
                        [
                            "大灣區智通行門診",
                            "第 2 年 2 個月保費折扣",
                            "",
                        ],
                    ],
                },
                {
                    "title": "危疾／意外／精神健康",
                    "columns": ["產品", "優惠重點", "備註"],
                    "rows": [
                        [
                            "危疾應援保／緻尚保／優易保–摯護您",
                            "「雙 18」：第 2 年 18% + 第 3 年 18% 保費折扣",
                            "",
                        ],
                        [
                            "危疾優易保—癌護您／心護您",
                            "第 2 年 2 個月保費折扣",
                            "",
                        ],
                        [
                            "好易揀危疾",
                            "首年及第 2 年各 3 個月保費折扣",
                            "",
                        ],
                        [
                            "全意守護意外（計劃／附約）",
                            "首年及第 2 年各 2 個月保費折扣",
                            "附約須連新基本計劃遞交",
                        ],
                        [
                            "智•守衛精神健康（計劃／附約）",
                            "首年 5 個月保費折扣",
                            "附約須連新基本計劃遞交",
                        ],
                    ],
                },
                {
                    "title": "壽險／定期壽險",
                    "columns": ["產品", "繳費／條件", "優惠", "備註"],
                    "rows": [
                        [
                            "家·年華",
                            "躉繳 SI <$125k／$1M",
                            "躉繳保費 2.5%",
                            "",
                        ],
                        [
                            "家·年華",
                            "躉繳 SI ≥$125k／$1M",
                            "躉繳保費 5%",
                            "",
                        ],
                        [
                            "家·年華",
                            "5／10 年供",
                            "次年保費 10%",
                            "抵銷次年每期保費",
                        ],
                        [
                            "家·年華",
                            "20 年供",
                            "次年保費 20%",
                            "抵銷次年每期保費",
                        ],
                        [
                            "承譽定期",
                            "10／20 年",
                            "次年保費 50%",
                            "",
                        ],
                        [
                            "自主保／附約",
                            "5／10／20 年",
                            "首年 25%；第 2–5 年 20%",
                            "",
                        ],
                    ],
                },
                {
                    "title": "儲蓄／財富產品",
                    "columns": ["產品", "條件", "優惠", "備註"],
                    "rows": [
                        [
                            "非凡匯聚 (HK)",
                            "躉繳 <$200k",
                            "1%",
                            "",
                        ],
                        [
                            "非凡匯聚 (HK)",
                            "躉繳 $200k–<$500k",
                            "2%",
                            "",
                        ],
                        [
                            "非凡匯聚 (HK)",
                            "躉繳 ≥$500k",
                            "4%",
                            "",
                        ],
                        [
                            "智盈匯聚（優越版）III／V",
                            "躉繳 <$200k（或等值）",
                            "4%",
                            "V 另設人民幣檔",
                        ],
                        [
                            "智盈匯聚（優越版）III／V",
                            "躉繳 $200k–<$500k",
                            "6%",
                            "",
                        ],
                        [
                            "智盈匯聚（優越版）III／V",
                            "躉繳 ≥$500k",
                            "8%",
                            "",
                        ],
                        [
                            "創逸致富（豐裕版）II",
                            "躉繳 SI <$3M／≥$3M",
                            "2%／3%",
                            "",
                        ],
                        [
                            "創逸致富（豐裕版）II",
                            "5 年供／10 年供",
                            "首年 5%／次年 10%",
                            "",
                        ],
                        [
                            "盈∙歲悅延期年金",
                            "5 年 ≥USD5k 或 10 年 ≥USD2.5k",
                            "首年 10% + 次年 5%（合共 15%）",
                            "合資格 QDAP 客戶次年 8%（合共 18%）",
                        ],
                        [
                            "盈聚‧天下 II",
                            "躉繳／2／5／10 年供",
                            "按保費層級 2%–更高檔",
                            "完整貨幣表見 Portal",
                        ],
                        [
                            "智盈·超凡",
                            "躉繳 <$1M USD（或等值）／≥",
                            "5%／7%",
                            "",
                        ],
                        [
                            "智悅未來",
                            "第 7 年完結；USD≥2.5M／HKD≥20M",
                            "特別獎賞率 7%（× 躉繳保費）",
                            "須於 2027-01-31 前繕發；首 7 年不可部分提款",
                        ],
                    ],
                },
                {
                    "title": "Q4 更改／限時優惠（2026-10-01 至 12-31）",
                    "columns": ["產品", "條件", "優惠", "備註"],
                    "rows": [
                        [
                            "智優盛儲蓄",
                            "須於 2027-01-31 前繕發",
                            "7.4% 躉繳折扣 + 高達每年 5% 保證期滿回報",
                            "限額發售，或會提早結束",
                        ],
                        [
                            "盈聚‧天下 II（3 年供）",
                            "年繳 <USD50k",
                            "首年 25%",
                            "其他貨幣等值見官方表",
                        ],
                        [
                            "盈聚‧天下 II（3 年供）",
                            "年繳 USD50k–<$100k",
                            "首年 30%",
                            "",
                        ],
                        [
                            "盈聚‧天下 II（3 年供）",
                            "年繳 ≥USD100k",
                            "首年 35%",
                            "",
                        ],
                    ],
                },
            ],
        },
        "agent": {
            "banner": (
                "業績期：2026-10-01 至 2026-12-31（遞交及繕發）· "
                "特別獎金可計入 2027 MDRT · Ref：TA261048"
            ),
            "footnote": (
                "續保率截至 2026-12-31 須 ≥85%；預計 2027-02 發放。"
                "完整一般規則以官方 Flash Report 為準。"
            ),
            "sections": [
                {
                    "title": "盈聚•天下特別獎金（TA261048.1）",
                    "columns": ["累積首年保費", "特別獎金", "合資格要求"],
                    "rows": [
                        ["≥ USD200k", "首年佣金 40%", "盈聚•天下 II · 年繳 · 2／3／5 年供"],
                        ["USD75k – <200k", "首年佣金 30%", "同上"],
                        ["USD50k – <75k", "首年佣金 20%", "同上"],
                        ["USD6k – <50k", "首年佣金 10%", "同上"],
                    ],
                },
                {
                    "title": "高端客戶特別獎金（TA261048.2）",
                    "columns": ["產品", "繳費", "獎賞"],
                    "rows": [
                        [
                            "智盈匯聚（優越版）V／創逸致富（豐裕版）II／智盈·超凡",
                            "躉繳",
                            "首年保費額外 2%",
                        ],
                        [
                            "非凡匯聚 (HK)",
                            "躉繳 ≥ USD500k",
                            "額外 5% 佣金",
                        ],
                        [
                            "非凡匯聚 (HK)",
                            "躉繳 USD200k – <500k",
                            "額外 4% 佣金",
                        ],
                        [
                            "非凡匯聚 (HK)",
                            "躉繳 < USD200k",
                            "額外 3% 佣金",
                        ],
                        [
                            "非凡致富 (HK)",
                            "躉繳／5 年繳（SI ≥ US$4M）",
                            "第 1 年：目標保費額外 10%",
                        ],
                        [
                            "非凡致富 (HK)",
                            "10 年繳",
                            "第 1 年已繳目標保費 +10%；第 2 年未繳目標保費 +10%",
                        ],
                    ],
                },
                {
                    "title": "領獎須知（摘要）",
                    "columns": ["項目", "說明"],
                    "rows": [
                        ["個人上限", "盈聚•天下特別獎金上限 HKD 4,000,000"],
                        ["續保率", "截至 2026-12-31 須達 85% 或以上"],
                        ["發放", "預計 2027-02（2027-01 薪酬）；須仍持有效合約"],
                        ["MDRT", "特別獎金可計入 2027 MDRT 資格"],
                        ["上訴", "暫定 2027-02-15 17:00 前電郵 Zone Head（CC 直屬經理／區域總監）"],
                    ],
                },
            ],
        },
    },
}

# Backward-compatible alias used by older helpers / tests
DEFAULT_OFFERS = DEFAULT_CATALOG

OFFER_COLUMNS = [
    "id",
    "quarter",
    "kind",
    "title",
    "detail",
    "note",
    "sort",
    "updated_at",
]


def current_quarter_key(today: date | None = None) -> str:
    d = today or date.today()
    m = d.month
    if m <= 3:
        return "Q1"
    if m <= 6:
        return "Q2"
    if m <= 9:
        return "Q3"
    return "Q4"


def default_catalog(quarter: str, kind: str) -> dict:
    """Return {banner, footnote, sections} for a quarter/kind."""
    q = str(quarter or "").strip().upper()
    k = str(kind or "").strip().lower()
    empty = {"banner": "", "footnote": "", "sections": []}
    block = DEFAULT_CATALOG.get(q, {}).get(k)
    if not isinstance(block, dict):
        return empty
    return {
        "banner": str(block.get("banner", "") or ""),
        "footnote": str(block.get("footnote", "") or ""),
        "sections": list(block.get("sections") or []),
    }


def default_items(quarter: str, kind: str) -> list[dict]:
    """Flat list for Leader sheet merge / legacy callers."""
    catalog = default_catalog(quarter, kind)
    items: list[dict] = []
    sort = 0
    if catalog.get("banner"):
        sort += 1
        items.append(
            {
                "sort": sort,
                "title": "推廣期／總覽",
                "detail": catalog["banner"],
                "note": catalog.get("footnote", ""),
            }
        )
    for section in catalog.get("sections") or []:
        cols = section.get("columns") or []
        for row in section.get("rows") or []:
            sort += 1
            cells = list(row) + [""] * max(0, len(cols) - len(row))
            if not cols:
                continue
            title = str(cells[0] if cells else section.get("title", "")).strip()
            detail_parts = []
            for i, col in enumerate(cols[1:], start=1):
                val = str(cells[i] if i < len(cells) else "").strip()
                if val:
                    detail_parts.append(f"{col}：{val}")
            items.append(
                {
                    "sort": sort,
                    "title": f"{section.get('title', '')} · {title}".strip(" ·"),
                    "detail": "\n".join(detail_parts),
                    "note": "",
                    "section": section.get("title", ""),
                    "columns": cols,
                    "row": cells[: len(cols)],
                }
            )
    return items


def catalog_from_flat_items(items: list[dict], *, kind: str) -> dict:
    """Build a single table section from Sheet title/detail/note rows."""
    rows = []
    for item in sorted(items or [], key=lambda x: int(x.get("sort", 0) or 0)):
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        rows.append(
            [
                title,
                str(item.get("detail", "") or "").strip(),
                str(item.get("note", "") or "").strip(),
            ]
        )
    if not rows:
        return {"banner": "", "footnote": "", "sections": []}
    label = "客戶優惠" if kind == "customer" else "營業員獎賞"
    return {
        "banner": "以下為 Leader 自訂項目（Google Sheet）",
        "footnote": "",
        "sections": [
            {
                "title": f"自訂{label}",
                "columns": ["項目", "詳情", "備註"],
                "rows": rows,
            }
        ],
    }

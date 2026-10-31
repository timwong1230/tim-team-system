"""Guest-facing nested category tree (hub → optional sub → products)."""

from __future__ import annotations

from typing import Any

# Soft-drink vs juice split inside Non Alcohol (by menu item id).
_JUICE_IDS = frozenset({"aj", "oj", "cran"})


def _leaf(
    leaf_id: str,
    name: str,
    *,
    category_ids: list[str] | None = None,
    unit: str | None = None,
    item_ids: frozenset[str] | None = None,
    exclude_item_ids: frozenset[str] | None = None,
    rail_lines: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": leaf_id,
        "name": name,
        "kind": "products",
        "category_ids": category_ids or [],
        "unit": unit,
        "item_ids": item_ids,
        "exclude_item_ids": exclude_item_ids,
        # Optional left-rail line breaks (avoid mid-word hyphenation).
        "rail_lines": rail_lines or [name],
    }


def _group(group_id: str, name: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": group_id, "name": name, "kind": "group", "children": children}


# Top-level guest menu — keep this short; nest detail one level down.
GUEST_NAV_TREE: list[dict[str, Any]] = [
    _leaf("shisha", "Shisha", category_ids=["shisha"]),
    _leaf(
        "celestial",
        "Celestial Signature Cocktails",
        category_ids=["celestial"],
        rail_lines=["Celestial", "Signature", "Cocktails"],
    ),
    _group(
        "wine",
        "Wine",
        [
            _leaf("red-wine", "Red Wine", category_ids=["red-wine"]),
            _leaf("white-wine", "White Wine", category_ids=["white-wine"]),
        ],
    ),
    _group(
        "beer",
        "Beer",
        [
            _leaf("draft-beer", "Draft Beer", category_ids=["beer"], unit="Glass"),
            _leaf("bottle-beer", "Bottle Beer", category_ids=["beer"], unit="Bottle"),
        ],
    ),
    _leaf("tower", "Tower", category_ids=["tower"]),
    _group(
        "spirit",
        "Spirit",
        [
            _leaf("vodka", "Vodka", category_ids=["vodka"]),
            _leaf("gin", "Gin", category_ids=["gin"]),
            _leaf("whisky", "Whisky", category_ids=["whisky"]),
            _leaf("liqueur", "Liqueur", category_ids=["liqueur"]),
            _leaf("tequila", "Tequila", category_ids=["tequila"]),
            _leaf("cognac", "Cognac", category_ids=["cognac"]),
        ],
    ),
    _leaf("champagne", "Champagne", category_ids=["champagne"]),
    _group(
        "non-alcohol",
        "Non Alcohol",
        [
            _leaf(
                "juice",
                "Juice",
                category_ids=["non-alcohol"],
                item_ids=_JUICE_IDS,
            ),
            _leaf(
                "soft-drinks",
                "Soft Drinks",
                category_ids=["non-alcohol"],
                exclude_item_ids=_JUICE_IDS,
            ),
            _leaf("special-tea", "Special Tea", category_ids=["teas"]),
        ],
    ),
    _leaf("snacks", "Bar Snacks", category_ids=["snacks"]),
]


def _filter_items(items: list[dict[str, Any]], node: dict[str, Any]) -> list[dict[str, Any]]:
    out = list(items)
    unit = node.get("unit")
    if unit:
        out = [i for i in out if (i.get("unit") or "") == unit]
    item_ids = node.get("item_ids")
    if item_ids is not None:
        out = [i for i in out if i.get("id") in item_ids]
    exclude = node.get("exclude_item_ids")
    if exclude is not None:
        out = [i for i in out if i.get("id") not in exclude]
    return out


def _items_for_leaf(
    menu_by_id: dict[str, dict[str, Any]],
    node: dict[str, Any],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for cid in node.get("category_ids") or []:
        cat = menu_by_id.get(cid)
        if not cat:
            continue
        collected.extend(cat.get("items") or [])
    return _filter_items(collected, node)


def _nav_category_ids(nodes: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for node in nodes:
        for cid in node.get("category_ids") or []:
            ids.add(str(cid))
        for child in node.get("children") or []:
            for cid in child.get("category_ids") or []:
                ids.add(str(cid))
    return ids


def build_guest_nav(menu: list[dict[str, Any]]) -> dict[str, Any]:
    """Build hub roots + product leaves from flat staff menu payload."""
    menu_by_id = {c["id"]: c for c in menu}
    roots: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []

    def add_leaf(
        node: dict[str, Any],
        parent_id: str | None,
        parent_name: str | None,
    ) -> dict[str, Any]:
        items = _items_for_leaf(menu_by_id, node)
        units = {r.get("unit") for r in items if r.get("unit")}
        leaf = {
            "id": node["id"],
            "name": node["name"],
            "parent_id": parent_id,
            "parent_name": parent_name,
            "items": items,
            "split_serve": "Glass" in units and "Bottle" in units,
        }
        leaves.append(leaf)
        return {
            "id": node["id"],
            "name": node["name"],
            "kind": "products",
            "target": f"leaf-{node['id']}",
            "rail_lines": node.get("rail_lines") or [node["name"]],
        }

    for node in GUEST_NAV_TREE:
        if node["kind"] == "products":
            roots.append(add_leaf(node, None, None))
            continue
        children = []
        for child in node.get("children") or []:
            children.append(add_leaf(child, node["id"], node["name"]))
        roots.append(
            {
                "id": node["id"],
                "name": node["name"],
                "kind": "group",
                "children": children,
                "rail_lines": node.get("rail_lines") or [node["name"]],
            }
        )

    # Staff-only categories present in the payload (Demo practice Free Flow).
    # Real guest menus omit these from `_menu_payload`, so nothing is added.
    covered = _nav_category_ids(GUEST_NAV_TREE)
    extras: list[dict[str, Any]] = []
    for cat in menu:
        cid = str(cat.get("id") or "")
        if not cid or cid in covered:
            continue
        if not cat.get("staff_only"):
            continue
        if not (cat.get("items") or []):
            continue
        extras.append(
            add_leaf(
                _leaf(cid, cat.get("name") or cid, category_ids=[cid]),
                None,
                None,
            )
        )
    if extras:
        roots[0:0] = extras

    return {"roots": roots, "leaves": leaves}

#!/usr/bin/env python3
"""Download open-license product photos and wire them into menu.json."""

from __future__ import annotations

import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT / "data" / "menu.json"
OUT = ROOT / "static" / "images" / "menu"
UA = "PolarLoungeMenuBot/1.0 (menu imagery; educational lounge POS)"

# Unique asset key → search queries (tried in order). Glass/Bottle share one asset.
ASSETS: dict[str, list[str]] = {
    # Soft drinks / juices
    "coke": ["Coca-Cola glass bottle", "Coca Cola bottle"],
    "coke-zero": ["Coca-Cola Zero bottle", "Coke Zero can"],
    "sprite": ["Sprite soda bottle green", "Sprite lemon lime soda"],
    "ginger-ale": ["ginger ale glass", "Canada Dry ginger ale"],
    "tonic": ["tonic water bottle", "Schweppes tonic water"],
    "redbull": ["Red Bull energy drink can"],
    "oj": ["glass of orange juice"],
    "aj": ["glass of apple juice"],
    "cran": ["cranberry juice glass"],
    "pellegrino": ["San Pellegrino sparkling water bottle"],
    # Teas
    "tea-orange": ["orange jasmine tea cup", "citrus tea glass"],
    "tea-pineapple": ["pineapple tea glass", "fruit iced tea"],
    "tea-lemon": ["lemon ginger honey tea", "lemon ginger tea cup"],
    # Snacks
    "wings": ["buffalo chicken wings plate"],
    "kfc": ["korean fried chicken", "yangnyeom chicken"],
    # Beer
    "corona": ["Corona Extra beer bottle"],
    "asahi": ["Asahi Super Dry beer", "Asahi beer glass"],
    "asahi-dark": ["dark beer glass stout", "black beer pint"],
    "vedett": ["Vedett Extra White beer", "witbier glass orange"],
    # Towers
    "draft-tower": ["beer tower dispenser", "draft beer tower"],
    "bottle-tower": ["beer bucket bottles ice", "bottled beer ice bucket"],
    "single-mix": ["cocktail pitcher party", "mixed drinks pitcher"],
    # Wine (generic by style when brand scarce)
    "lfe-cab": ["cabernet sauvignon wine bottle", "red wine bottle cabernet"],
    "bella": ["merlot wine bottle", "red wine bottle merlot"],
    "rose-b": ["rose wine bottle", "rosé wine bottle"],
    "lfe-sav": ["sauvignon blanc wine bottle", "white wine bottle"],
    "trebbiano": ["trebbiano white wine", "italian white wine bottle"],
    "moscato-b": ["moscato wine bottle", "sweet white wine bottle"],
    "chaos-b": ["sparkling wine bottle", "prosecco bottle"],
    # Vodka
    "belvedere": ["Belvedere vodka bottle"],
    "grey-goose": ["Grey Goose vodka bottle"],
    "jessy-vodka": ["vodka bottle frosted", "premium vodka bottle"],
    # Gin
    "bombay": ["Bombay Sapphire gin bottle"],
    "hendricks": ["Hendrick's gin bottle"],
    "tanqueray": ["Tanqueray gin bottle"],
    "mg-rosa": ["pink gin bottle", "rose gin bottle"],
    "jessy-gin": ["gin bottle botanical", "premium gin bottle"],
    # Whisky
    "claymore": ["blended scotch whisky bottle", "scotch whisky bottle"],
    "black-label": ["Johnnie Walker Black Label bottle"],
    "jd": ["Jack Daniel's whiskey bottle"],
    "makers": ["Maker's Mark bourbon bottle"],
    "glenfiddich": ["Glenfiddich 12 bottle"],
    "glenlivet": ["Glenlivet 12 bottle"],
    "singleton": ["Singleton whisky bottle", "single malt whisky bottle"],
    # Liqueur
    "baileys": ["Baileys Irish Cream bottle"],
    "kahlua": ["Kahlúa bottle", "Kahlua coffee liqueur"],
    "jager": ["Jägermeister bottle", "Jagermeister bottle"],
    "tequila-rose": ["Tequila Rose bottle", "strawberry cream liqueur"],
    # Champagne
    "moet": ["Moët & Chandon champagne bottle", "Moet Chandon Imperial"],
    "vcp": ["Veuve Clicquot champagne bottle", "Veuve Clicquot Yellow Label"],
    "dom": ["Dom Pérignon champagne bottle", "Dom Perignon bottle"],
    # Tequila
    "cuervo": ["Jose Cuervo Silver tequila bottle"],
    "patron": ["Patrón Silver tequila bottle", "Patron Silver tequila"],
    "campo": ["blanco tequila bottle", "silver tequila bottle"],
    # Rum / cognac
    "myers": ["Myers's rum bottle", "Myers rum dark"],
    "jessy-rum": ["dark rum bottle", "rum bottle"],
    "vsop": ["VSOP cognac bottle", "cognac bottle"],
}

# Map menu item id → asset key (glass/bottle share)
ITEM_ASSET: dict[str, str] = {
    "coke": "coke",
    "coke-zero": "coke-zero",
    "sprite": "sprite",
    "ginger-ale": "ginger-ale",
    "tonic": "tonic",
    "redbull": "redbull",
    "oj": "oj",
    "aj": "aj",
    "cran": "cran",
    "pellegrino": "pellegrino",
    "tea-orange": "tea-orange",
    "tea-pineapple": "tea-pineapple",
    "tea-lemon": "tea-lemon",
    "wings": "wings",
    "kfc": "kfc",
    "corona": "corona",
    "asahi": "asahi",
    "asahi-dark": "asahi-dark",
    "vedett": "vedett",
    "draft-tower": "draft-tower",
    "bottle-tower": "bottle-tower",
    "single-mix": "single-mix",
    "lfe-cab-g": "lfe-cab",
    "lfe-cab-b": "lfe-cab",
    "bella-g": "bella",
    "bella-b": "bella",
    "rose-b": "rose-b",
    "lfe-sav-g": "lfe-sav",
    "lfe-sav-b": "lfe-sav",
    "trebbiano-g": "trebbiano",
    "trebbiano-b": "trebbiano",
    "moscato-b": "moscato-b",
    "chaos-b": "chaos-b",
    "belvedere-g": "belvedere",
    "belvedere-b": "belvedere",
    "grey-goose-g": "grey-goose",
    "grey-goose-b": "grey-goose",
    "jessy-vodka-g": "jessy-vodka",
    "jessy-vodka-b": "jessy-vodka",
    "bombay-g": "bombay",
    "bombay-b": "bombay",
    "hendricks-g": "hendricks",
    "hendricks-b": "hendricks",
    "tanqueray-g": "tanqueray",
    "tanqueray-b": "tanqueray",
    "mg-rosa-g": "mg-rosa",
    "mg-rosa-b": "mg-rosa",
    "jessy-gin-g": "jessy-gin",
    "jessy-gin-b": "jessy-gin",
    "claymore-g": "claymore",
    "claymore-b": "claymore",
    "black-label-g": "black-label",
    "black-label-b": "black-label",
    "jd-g": "jd",
    "jd-b": "jd",
    "makers-g": "makers",
    "makers-b": "makers",
    "glenfiddich-g": "glenfiddich",
    "glenfiddich-b": "glenfiddich",
    "glenlivet-g": "glenlivet",
    "glenlivet-b": "glenlivet",
    "singleton-g": "singleton",
    "singleton-b": "singleton",
    "baileys-g": "baileys",
    "baileys-b": "baileys",
    "kahlua-g": "kahlua",
    "kahlua-b": "kahlua",
    "jager-g": "jager",
    "jager-b": "jager",
    "tequila-rose-g": "tequila-rose",
    "tequila-rose-b": "tequila-rose",
    "moet": "moet",
    "vcp": "vcp",
    "dom": "dom",
    "cuervo-g": "cuervo",
    "cuervo-b": "cuervo",
    "patron-g": "patron",
    "patron-b": "patron",
    "campo-g": "campo",
    "campo-b": "campo",
    "myers-g": "myers",
    "myers-b": "myers",
    "jessy-rum-g": "jessy-rum",
    "jessy-rum-b": "jessy-rum",
    "vsop-g": "vsop",
    "vsop-b": "vsop",
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def search_openverse(q: str, limit: int = 5) -> list[str]:
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": q, "page_size": limit, "license_type": "commercial"}
    )
    try:
        data = json.loads(_get(url).decode())
    except Exception:
        return []
    urls = []
    for x in data.get("results", []):
        u = x.get("url") or x.get("thumbnail")
        if u and re.search(r"\.(jpe?g|png|webp)(\?|$)", u, re.I):
            urls.append(u)
        elif u:
            urls.append(u)
    return urls


def search_wikimedia(q: str, limit: int = 5) -> list[str]:
    api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": q,
            "gsrlimit": limit,
            "gsrnamespace": 6,
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": 1200,
        }
    )
    try:
        data = json.loads(_get(api).decode())
    except Exception:
        return []
    urls = []
    for p in (data.get("query") or {}).get("pages", {}).values():
        info = (p.get("imageinfo") or [{}])[0]
        mime = info.get("mime") or ""
        if not mime.startswith("image/") or "svg" in mime or "tif" in mime:
            continue
        u = info.get("thumburl") or info.get("url")
        if u:
            urls.append(u)
    return urls


def process_image(raw: bytes, dest: Path) -> bool:
    try:
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGB")
    except Exception:
        return False
    tw, th = 800, 1000
    # cover-fit into portrait canvas on dark lounge bg
    ratio = max(tw / im.width, th / im.height)
    nw, nh = max(1, int(im.width * ratio)), max(1, int(im.height * ratio))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    im = im.crop((left, top, left + tw, top + th))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, quality=88, optimize=True)
    return dest.exists() and dest.stat().st_size > 2000


def fetch_asset(key: str, queries: list[str]) -> Path | None:
    dest = OUT / f"{key}.jpg"
    if dest.exists() and dest.stat().st_size > 2000:
        return dest
    tried: list[str] = []
    for q in queries:
        for url in search_wikimedia(q) + search_openverse(q):
            if url in tried:
                continue
            tried.append(url)
            try:
                raw = _get(url)
                if process_image(raw, dest):
                    print(f"  OK {key} <- {q[:40]} ({dest.stat().st_size}b)")
                    return dest
            except Exception as e:
                print(f"  fail {key}: {e}")
            time.sleep(0.35)
        time.sleep(0.5)
    print(f"  MISS {key}")
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}
    for key, queries in ASSETS.items():
        print(f"[{key}]")
        path = fetch_asset(key, queries)
        if path:
            results[key] = f"/static/images/menu/{key}.jpg"
        time.sleep(0.2)

    menu = json.loads(MENU.read_text(encoding="utf-8"))
    updated = 0
    missing_items = []
    for cat in menu["categories"]:
        for item in cat["items"]:
            iid = item["id"]
            # keep celestial / existing explicit images if already set & file exists
            existing = item.get("image")
            if existing:
                p = ROOT / existing.lstrip("/")
                if p.exists():
                    continue
            asset = ITEM_ASSET.get(iid)
            if asset and asset in results:
                item["image"] = results[asset]
                updated += 1
            elif asset:
                missing_items.append(iid)
            # fries / shisha / celestial already have images in json

    MENU.write_text(json.dumps(menu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWired {updated} items. Assets ok={len(results)}/{len(ASSETS)}")
    if missing_items:
        print("Still missing assets for:", missing_items)
    failed = [k for k in ASSETS if k not in results]
    if failed:
        print("Failed assets:", failed)


if __name__ == "__main__":
    main()

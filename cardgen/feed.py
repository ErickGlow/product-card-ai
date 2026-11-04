"""Импорт товаров из YML-фида (формат Яндекс.Маркета) во входной JSON сервиса.

python -m cardgen.feed https://site/feed.xml --search манометр --limit 2 --out examples/from_feed.json
Фид читается потоково (iterparse), поэтому подходит и для больших каталогов.
"""
import argparse
import html
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

TAG = re.compile(r"<[^>]+>")
SERVICE_PARAMS = {"артикул", "код товара", "штрихкод", "ean"}  # не технические характеристики


def clean_text(text: str | None) -> str:
    """Описания в YML часто содержат HTML — оставляем чистый текст."""
    if not text:
        return ""
    text = html.unescape(TAG.sub(" ", text))
    return " ".join(text.split())


def category_path(cats: dict, cid: str | None) -> list[str]:
    """Цепочка категорий от корня до листа: ['КИП', 'Давление', 'Манометры']."""
    path, seen = [], set()
    while cid and cid in cats and cid not in seen:
        seen.add(cid)
        name, cid = cats[cid]
        path.append(name)
    return path[::-1]


def offer_to_product(offer: ET.Element, cats: dict | None = None) -> dict:
    get = lambda tag: (offer.findtext(tag) or "").strip()
    prefix, base = get("typePrefix"), get("name") or " ".join(x for x in (get("vendor"), get("model")) if x)
    # в названии часто только код модели — тип прибора берём из typePrefix
    name = f"{prefix[:1].upper()}{prefix[1:]} {base}".strip() if prefix and prefix.lower() not in base.lower() else base
    specs = {}
    for p in offer.findall("param"):
        key = (p.get("name") or "").strip()
        value = (p.text or "").strip()
        unit = (p.get("unit") or "").strip()
        if key and key.lower() not in SERVICE_PARAMS:
            specs[key] = f"{value} {unit}".strip() if value and unit and unit not in value else value
    path = category_path(cats or {}, get("categoryId"))
    return {
        "name": name,
        "category": " / ".join(path),
        "manufacturer": get("vendor"),
        "specs": specs,
        "description": clean_text(offer.findtext("description")),
        "_source": {"offer_id": offer.get("id"), "url": get("url")},
    }


def iter_offers(path: Path, cats: dict):
    """Категории в YML идут до товаров, поэтому к моменту разбора offer дерево уже собрано."""
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "category" and el.get("id"):
            cats[el.get("id")] = ((el.text or "").strip(), el.get("parentId"))
        elif el.tag == "offer":
            yield el
            el.clear()


def download(url: str) -> Path:
    tmp = Path(tempfile.gettempdir()) / "cardgen_feed.xml"
    # некоторые сайты отдают 403 запросам без браузерного User-Agent
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
    with httpx.stream("GET", url, timeout=120, follow_redirects=True, headers=headers) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return tmp


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Товары из YML-фида → входной JSON")
    ap.add_argument("source", help="путь к feed.xml или URL")
    ap.add_argument("--search", default="", help="подстрока в названии, категории или производителе")
    ap.add_argument("--limit", type=int, default=2, help="сколько товаров взять (по умолчанию 2)")
    ap.add_argument("--min-specs", type=int, default=0, help="брать только товары с N+ характеристиками")
    ap.add_argument("--out", default="examples/from_feed.json")
    args = ap.parse_args(argv)

    try:
        path = download(args.source) if args.source.startswith(("http://", "https://")) else Path(args.source)
        needle, found, scanned, cats = args.search.lower(), [], 0, {}
        for offer in iter_offers(path, cats):
            scanned += 1
            product = offer_to_product(offer, cats)
            haystack = " ".join((product["name"], product["category"], product["manufacturer"])).lower()
            if needle in haystack and len(product["specs"]) >= args.min_specs:
                found.append(product)
                if len(found) >= args.limit:
                    break
    except (OSError, httpx.HTTPError, ET.ParseError) as e:
        print(f"Ошибка чтения фида: {e}", file=sys.stderr)
        return 2

    if not found:
        print(f"Не найдено товаров по «{args.search}» (просмотрено {scanned})", file=sys.stderr)
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    for p in found:
        print(f"· {p['name']} [{p['category'] or 'без категории'}] — "
              f"характеристик: {len(p['specs'])}, описание: {len(p['description'])} симв.")
    print(f"Сохранено {len(found)} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

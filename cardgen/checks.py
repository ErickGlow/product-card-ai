"""Проверки ответа модели: формат, длины и отсутствие выдуманных фактов."""
import json
import re

from .config import DESC_MAX, DESC_MIN, QUERIES_MAX, QUERIES_MIN, TITLE_MAX
from .schema import Product

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# Утверждения, которые модели любят «дорисовывать». Если их нет во входе — это выдумка.
RISKY = {
    r"\bip\s?\d{2}\b": "степень защиты IP",
    r"взрывозащ|\bex\b": "взрывозащита",
    r"гост": "ГОСТ",
    r"госреестр|реестр си": "Госреестр СИ",
    r"поверк|поверен": "поверка",
    r"сертифик": "сертификация",
    r"гаранти": "гарантия",
    r"нержаве": "материал (нержавеющая сталь)",
    r"срок службы": "срок службы",
}


def extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа, даже если модель обернула его в ```json ... ``` или текст."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("в ответе нет JSON-объекта")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON не разбирается: {e.msg}") from e
    if not isinstance(data, dict):
        raise ValueError("ответ должен быть JSON-объектом")
    return data


def _str_list(v) -> list[str]:
    if isinstance(v, str):
        v = [v]
    return [" ".join(str(x).split()) for x in v or [] if str(x).strip()] if isinstance(v, list) else []


def normalize(data: dict) -> dict:
    commercial = data.get("commercial") if isinstance(data.get("commercial"), dict) else {}
    return {
        "seo_title": " ".join(str(data.get("seo_title") or "").split()),
        "seo_description": str(data.get("seo_description") or "").strip(),
        "search_queries": _str_list(data.get("search_queries")),
        "commercial": {
            "audience": _str_list(commercial.get("audience")),
            "tasks": _str_list(commercial.get("tasks")),
        },
        "missing_characteristics": _str_list(data.get("missing_characteristics"))[:6],
    }


def _canon(n: str) -> str:
    return format(float(n.replace(",", ".")), "g")


def source_text(p: Product) -> str:
    return " ".join([p.name, p.category, p.manufacturer, p.description, *p.specs.keys(), *p.specs.values()])


def generated_text(card: dict) -> str:
    c = card["commercial"]
    text = " ".join([card["seo_title"], card["seo_description"], *card["search_queries"],
                     *c["audience"], *c["tasks"]])
    return re.sub(r"\bb2b\b", "", text, flags=re.IGNORECASE)  # «B2B» — не техническое число


def check(card: dict, p: Product) -> list[str]:
    problems = []
    t, d, q = card["seo_title"], card["seo_description"], card["search_queries"]
    if not t:
        problems.append("seo_title пустой")
    elif len(t) > TITLE_MAX:
        problems.append(f"seo_title {len(t)} симв., нужно не больше {TITLE_MAX} — сократи")
    if not DESC_MIN <= len(d) <= DESC_MAX:
        hint = "расширь" if len(d) < DESC_MIN else "сократи"
        problems.append(f"seo_description {len(d)} симв., нужно {DESC_MIN}–{DESC_MAX} — {hint} "
                        f"(без новых фактов: подробнее раскрой назначение и применение)")
    if not QUERIES_MIN <= len(q) <= QUERIES_MAX:
        problems.append(f"search_queries: {len(q)} шт., нужно {QUERIES_MIN}–{QUERIES_MAX}")
    if not card["commercial"]["audience"] or not card["commercial"]["tasks"]:
        problems.append("commercial: заполни audience и tasks")

    src, gen = source_text(p), generated_text(card)
    allowed = {_canon(n) for n in NUMBER.findall(src)}
    invented = sorted({n for n in NUMBER.findall(gen) if _canon(n) not in allowed})
    if invented:
        problems.append("числа, которых нет во входных данных: " + ", ".join(invented) + " — удали их")

    src_l, gen_l = src.lower(), gen.lower()
    for pattern, label in RISKY.items():
        if re.search(pattern, gen_l) and not re.search(pattern, src_l):
            problems.append(f"упомянуто «{label}», но во входных данных этого нет — удали")
    return problems

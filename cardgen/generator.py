from .checks import check, extract_json, normalize
from .config import NO_DATA
from .prompts import build_messages, feedback
from .schema import Product, Validation


class GenerationError(RuntimeError):
    pass


def _key_specs(p: Product, missing: list[str]) -> list[dict]:
    """Таблицу характеристик собирает код, а не модель: значения только из входа."""
    rows = [{"name": "Производитель", "value": p.manufacturer or NO_DATA}]
    rows += [{"name": k, "value": v or NO_DATA} for k, v in p.specs.items()]
    known = {r["name"].lower() for r in rows}
    for name in missing:
        low = name.lower()
        if not any(low in k or k in low for k in known):
            rows.append({"name": name, "value": NO_DATA})
            known.add(low)
    return rows


def generate(validation: Validation, llm, max_attempts: int = 3, log=None) -> dict:
    log = log or (lambda msg: None)
    p = validation.product
    if p is None:
        raise GenerationError("; ".join(validation.errors))

    base = build_messages(p)
    messages, card, card_problems = base, None, []
    for attempt in range(1, max_attempts + 1):
        log(f"генерация, попытка {attempt}/{max_attempts}")
        raw = llm.complete(messages)
        try:
            candidate = normalize(extract_json(raw))
        except ValueError as e:
            problems = [f"ответ не в формате JSON ({e})"]
        else:
            problems = check(candidate, p)
            card, card_problems = candidate, problems
            if not problems:
                break
        log("замечания проверки: " + "; ".join(problems))
        # следующая попытка: исходный запрос + последний ответ + конкретные замечания
        messages = base + [{"role": "assistant", "content": raw}, {"role": "user", "content": feedback(problems)}]

    if card is None:
        raise GenerationError(f"Модель не вернула корректный JSON за {max_attempts} попытки")

    added = [r["name"] for r in _key_specs(p, card["missing_characteristics"])
             if r["value"] == NO_DATA and r["name"] not in p.specs and r["name"] != "Производитель"]
    clarify = list(validation.warnings)
    if added:
        clarify.append("Рекомендуется уточнить у поставщика: " + ", ".join(added))

    return {
        "status": "ready" if not card_problems else "needs_review",
        "product": p.name,
        "seo_title": card["seo_title"],
        "seo_title_length": len(card["seo_title"]),
        "seo_description": card["seo_description"],
        "seo_description_length": len(card["seo_description"]),
        "key_specs": _key_specs(p, card["missing_characteristics"]),
        "search_queries": card["search_queries"],
        "commercial": card["commercial"],
        "needs_clarification": clarify,
        "quality_warnings": card_problems,  # что не удалось исправить автоматически — проверить вручную
    }


def to_markdown(r: dict) -> str:
    status = "✅ готово к проверке" if r["status"] == "ready" else "⚠️ требует ручной проверки"
    lines = [f"# {r['product']}", "", f"**Статус:** {status}", "",
             f"## SEO-заголовок ({r['seo_title_length']} симв.)", "", r["seo_title"], "",
             f"## SEO-описание ({r['seo_description_length']} симв.)", "", r["seo_description"], "",
             "## Ключевые характеристики", "", "| Характеристика | Значение |", "|---|---|"]
    lines += [f"| {s['name']} | {s['value']} |" for s in r["key_specs"]]
    lines += ["", "## Поисковые запросы", ""] + [f"- {q}" for q in r["search_queries"]]
    lines += ["", "## Для менеджера", "", "**Кому подходит:**", ""]
    lines += [f"- {a}" for a in r["commercial"]["audience"]]
    lines += ["", "**Какие задачи решает:**", ""] + [f"- {t}" for t in r["commercial"]["tasks"]]
    if r["needs_clarification"]:
        lines += ["", "## Требует уточнения", ""] + [f"- {c}" for c in r["needs_clarification"]]
    if r["quality_warnings"]:
        lines += ["", "## Замечания проверки", ""] + [f"- {w}" for w in r["quality_warnings"]]
    return "\n".join(lines) + "\n"

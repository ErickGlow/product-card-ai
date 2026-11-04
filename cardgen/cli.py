"""Запуск: python -m cardgen.cli examples/products.json --out results"""
import argparse
import json
import re
import sys
from pathlib import Path

from .config import llm_settings
from .generator import GenerationError, generate, to_markdown
from .llm import LLMClient, LLMError
from .schema import InputError, parse_json, validate


def slug(text: str, i: int) -> str:
    s = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", "_", text).strip("_")[:40]
    return f"{i:02d}_{s or 'product'}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Черновики карточек товаров КИП через LLM")
    ap.add_argument("input", help="JSON-файл: объект товара или массив товаров")
    ap.add_argument("--out", default="results", help="папка для результатов (JSON + Markdown)")
    ap.add_argument("--timeout", type=float, default=90, help="таймаут одного запроса к LLM, сек")
    args = ap.parse_args(argv)

    try:
        items = parse_json(Path(args.input).read_text(encoding="utf-8"))
        log = lambda msg: print(f"    {msg}", flush=True)
        llm = LLMClient(llm_settings(), timeout=args.timeout, log=log)
    except (OSError, InputError, RuntimeError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 2

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for i, raw in enumerate(items, 1):
        v = validate(raw)
        title = (raw.get("name") if isinstance(raw, dict) else None) or f"товар {i}"
        print(f"[{i}/{len(items)}] {title}", flush=True)
        if v.errors:
            failed += 1
            print("  ✗ входные данные: " + "; ".join(v.errors))
            continue
        try:
            result = generate(v, llm, log=log)
        except (LLMError, GenerationError) as e:
            failed += 1
            print(f"  ✗ {e}")
            continue
        name = slug(title, i)
        (out / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / f"{name}.md").write_text(to_markdown(result), encoding="utf-8")
        mark = "✓" if result["status"] == "ready" else "⚠ требует проверки"
        print(f"  {mark} → {out / name}.md")
        for c in result["needs_clarification"]:
            print(f"    · {c}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

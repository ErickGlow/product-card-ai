"""Простая веб-форма: python -m cardgen.web → http://127.0.0.1:5000"""
import html
import json

from flask import Flask, jsonify, request

from .config import llm_settings
from .generator import GenerationError, generate, to_markdown
from .llm import LLMClient, LLMError
from .schema import InputError, parse_json, validate

app = Flask(__name__)

EXAMPLE = json.dumps({
    "name": "Манометр показывающий DM 02",
    "manufacturer": "Манотомь",
    "specs": {"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5",
              "присоединение": "G1/2", "диаметр корпуса": "100 мм"},
    "description": "Прибор предназначен для измерения избыточного давления.",
}, ensure_ascii=False, indent=2)

PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Карточка товара КИП</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#1d2433}}
textarea{{width:100%;height:260px;font:13px/1.4 ui-monospace,monospace;padding:10px;box-sizing:border-box}}
button{{padding:9px 18px;font-size:15px;cursor:pointer}} pre{{white-space:pre-wrap;background:#f4f6fa;padding:12px;border-radius:8px}}
.err{{color:#b00020}} .row{{display:flex;justify-content:space-between;align-items:center}}
</style></head><body>
<h1>AI-помощник: черновик карточки товара</h1>
<form method="post" action="/"><p>JSON товара (объект или массив):</p>
<textarea name="data">{data}</textarea><p><button>Сформировать</button></p></form>
{result}
<script>function copy(id){{navigator.clipboard.writeText(document.getElementById(id).innerText)}}</script>
</body></html>"""


def run(text: str) -> list[dict]:
    """Возвращает по каждому товару либо result, либо error."""
    items = parse_json(text)
    llm = LLMClient(llm_settings())
    out = []
    for raw in items:
        v = validate(raw)
        if v.errors:
            out.append({"error": "; ".join(v.errors)})
            continue
        try:
            out.append({"result": generate(v, llm)})
        except (LLMError, GenerationError) as e:
            out.append({"error": str(e)})
    return out


@app.route("/", methods=["GET", "POST"])
def index():
    data = request.form.get("data", EXAMPLE)
    blocks = []
    if request.method == "POST":
        try:
            for i, item in enumerate(run(data)):
                if "error" in item:
                    blocks.append(f'<p class="err">Товар {i + 1}: {html.escape(item["error"])}</p>')
                    continue
                r = item["result"]
                md = html.escape(to_markdown(r))
                js = html.escape(json.dumps(r, ensure_ascii=False, indent=2))
                blocks.append(
                    f'<div class="row"><h2>{html.escape(r["product"])}</h2>'
                    f'<span><button onclick="copy(\'md{i}\')">Копировать Markdown</button> '
                    f'<button onclick="copy(\'js{i}\')">Копировать JSON</button></span></div>'
                    f'<pre id="md{i}">{md}</pre><details><summary>JSON</summary><pre id="js{i}">{js}</pre></details>')
        except (InputError, RuntimeError) as e:
            blocks.append(f'<p class="err">{html.escape(str(e))}</p>')
    return PAGE.format(data=html.escape(data), result="".join(blocks))


@app.post("/api/generate")
def api_generate():
    try:
        return jsonify(run(request.get_data(as_text=True)))
    except (InputError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=False)

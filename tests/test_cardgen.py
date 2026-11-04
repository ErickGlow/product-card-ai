import json

import pytest

from cardgen.checks import check, extract_json, normalize
from cardgen.generator import generate, to_markdown
from cardgen.schema import InputError, parse_json, validate

PRODUCT = {
    "name": "Манометр показывающий DM 02",
    "manufacturer": "Манотомь",
    "specs": {"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5",
              "присоединение": "G1/2", "диаметр корпуса": "100 мм"},
    "description": "Прибор предназначен для измерения избыточного давления.",
}


def card(**over):
    desc = ("Манометр показывающий DM 02 производства Манотомь предназначен для измерения избыточного давления. "
            "Диапазон измерений 0–1,6 МПа, класс точности 1,5, присоединение G1/2, диаметр корпуса 100 мм. ")
    desc = (desc * 6)[:1000]
    data = {
        "seo_title": "Манометр DM 02 Манотомь 0–1,6 МПа",
        "seo_description": desc,
        "search_queries": ["манометр DM 02", "манометр Манотомь", "манометр 1,6 МПа купить"],
        "commercial": {"audience": ["службы КИПиА"], "tasks": ["контроль избыточного давления"]},
        "missing_characteristics": ["рабочая среда", "класс точности"],
    }
    data.update(over)
    return json.dumps(data, ensure_ascii=False)


class FakeLLM:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def complete(self, messages):
        self.calls.append(messages)
        return self.answers.pop(0)


def test_invalid_json_has_position():
    with pytest.raises(InputError, match="строка 1"):
        parse_json('{"name": "x",}')


def test_missing_name_is_error_and_empty_values_are_warnings():
    assert validate({"specs": {}}).errors
    v = validate({"name": "Датчик", "manufacturer": " ", "specs": {"класс точности": "—"}})
    assert v.product and v.product.specs["класс точности"] == ""
    assert any("производитель" in w for w in v.warnings)
    assert any("класс точности" in w for w in v.warnings)


def test_specs_wrong_type_is_error():
    assert validate({"name": "x", "specs": ["a"]}).errors


def test_extract_json_from_markdown_fence():
    assert extract_json('Вот ответ:\n```json\n{"a": 1}\n```')["a"] == 1


def test_detects_invented_numbers_and_claims():
    p = validate(PRODUCT).product
    bad = normalize(json.loads(card(seo_title="Манометр DM 02 IP65, 2,5 МПа")))
    problems = " ".join(check(bad, p))
    assert "2,5" in problems and "IP" in problems
    assert check(normalize(json.loads(card())), p) == []


def test_numbers_are_compared_semantically():
    p = validate(PRODUCT).product  # «1,5» во входе == «1.5» в тексте
    assert check(normalize(json.loads(card(seo_title="Манометр DM 02, класс 1.5"))), p) == []


def test_retry_with_feedback_then_ready():
    llm = FakeLLM("не JSON", card(seo_title="Манометр DM 02 класс 0,6"), card())
    r = generate(validate(PRODUCT), llm)
    assert r["status"] == "ready" and len(llm.calls) == 3
    assert "0,6" in llm.calls[2][-1]["content"]  # модель получила конкретную обратную связь


def test_specs_table_built_from_input_only():
    r = generate(validate(PRODUCT), FakeLLM(card()))
    specs = {s["name"]: s["value"] for s in r["key_specs"]}
    assert specs["диапазон измерений"] == "0–1,6 МПа"
    assert specs["рабочая среда"] == "данных нет"
    assert list(specs).count("класс точности") == 1  # уже есть во входе — не дублируется
    assert "рабочая среда" in " ".join(r["needs_clarification"])


def test_unfixed_problems_marked_needs_review():
    llm = FakeLLM(*[card(seo_description="коротко")] * 3)
    r = generate(validate(PRODUCT), llm)
    assert r["status"] == "needs_review" and r["quality_warnings"]
    assert "требует ручной проверки" in to_markdown(r)


def test_word_net_is_a_value_not_missing():
    v = validate({"name": "Модуль", "specs": {"Гальваническая развязка": "нет", "Класс": "-"}})
    assert v.product.specs == {"Гальваническая развязка": "нет", "Класс": ""}

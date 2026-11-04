import json

from cardgen.feed import main
from cardgen.schema import validate

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog date="2026-11-03 12:00"><shop><name>Test</name>
<categories><category id="1">КИП</category><category id="2" parentId="1">Манометры</category></categories><offers>
<offer id="101" available="true"><url>https://example.com/101</url><price>1500</price>
  <name>Термометр биметаллический ТБ</name><vendor>Вендор</vendor>
  <description><![CDATA[<p>Для измерения <b>температуры</b> &amp; среды.</p>]]></description>
  <param name="Диапазон" unit="°C">0...120</param><param name="Класс точности">1,5</param></offer>
<offer id="102"><typePrefix>Манометр</typePrefix><vendor>Манотомь</vendor><model>DM 02</model>
  <param name="Диаметр корпуса" unit="мм">100</param></offer>
<offer id="103"><name>Манометр электроконтактный</name></offer>
<offer id="104"><name>ДМ 2010</name><typePrefix>манометр показывающий</typePrefix><categoryId>2</categoryId>
  <param name="Класс">1,5</param><param name="Артикул">58953</param></offer>
</offers></shop></yml_catalog>"""


def test_import_search_limit_and_html_cleanup(tmp_path):
    src, out = tmp_path / "feed.xml", tmp_path / "out.json"
    src.write_text(FEED, encoding="utf-8")
    assert main([str(src), "--search", "манометр", "--limit", "5", "--out", str(out)]) == 0
    items = json.loads(out.read_text(encoding="utf-8"))
    assert [i["name"] for i in items] == ["Манометр Манотомь DM 02", "Манометр электроконтактный", "Манометр показывающий ДМ 2010"]
    assert items[2]["category"] == "КИП / Манометры"  # найден по категории, хотя в названии только код
    assert items[2]["specs"] == {"Класс": "1,5"}  # «Артикул» — служебный, не характеристика
    assert items[0]["specs"] == {"Диаметр корпуса": "100 мм"}
    assert not validate(items[0]).errors

    assert main([str(src), "--search", "термометр", "--out", str(out)]) == 0
    t = json.loads(out.read_text(encoding="utf-8"))[0]
    assert t["description"] == "Для измерения температуры & среды."
    assert t["specs"]["Диапазон"] == "0...120 °C" and t["_source"]["offer_id"] == "101"
    assert not any("Неизвестные" in w for w in validate(t).warnings)


def test_nothing_found(tmp_path):
    src = tmp_path / "feed.xml"; src.write_text(FEED, encoding="utf-8")
    assert main([str(src), "--search", "расходомер", "--out", str(tmp_path / "o.json")]) == 1


def test_min_specs_filter(tmp_path):
    src, out = tmp_path / "feed.xml", tmp_path / "o.json"
    src.write_text(FEED, encoding="utf-8")
    assert main([str(src), "--min-specs", "2", "--limit", "5", "--out", str(out)]) == 0  # 104: 1 характеристика после фильтра
    assert [i["_source"]["offer_id"] for i in json.loads(out.read_text(encoding="utf-8"))] == ["101"]

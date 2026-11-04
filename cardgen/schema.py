"""Разбор и проверка входных данных. Ничего не дополняет — только чистит и сообщает о пробелах."""
import json
from dataclasses import dataclass, field

KNOWN_FIELDS = {"name", "category", "manufacturer", "specs", "description"}
EMPTY_MARKERS = {"", "-", "—", "–", "n/a", "na", "null", "none", "?"}  # «нет» — это значение, а не пропуск


class InputError(ValueError):
    pass


@dataclass
class Product:
    name: str
    manufacturer: str
    specs: dict[str, str]  # пустая строка = значение не указано
    description: str
    category: str = ""  # раздел каталога: подсказывает тип прибора, если название — только код модели


@dataclass
class Validation:
    product: Product | None
    errors: list[str] = field(default_factory=list)    # генерация невозможна
    warnings: list[str] = field(default_factory=list)  # генерация возможна, но данных не хватает


def parse_json(text: str) -> list[dict]:
    """Принимает один товар (объект) или несколько (массив)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InputError(f"Некорректный JSON: {e.msg} (строка {e.lineno}, столбец {e.colno})") from e
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and data:
        return data
    raise InputError("Ожидается JSON-объект товара или непустой массив товаров")


def _clean(value) -> str | None:
    """Строка без мусора; '' — значение отсутствует; None — недопустимый тип."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        s = " ".join(value.split())
        return "" if s.lower() in EMPTY_MARKERS else s
    return None


def validate(raw) -> Validation:
    v = Validation(product=None)
    if not isinstance(raw, dict):
        v.errors.append("Товар должен быть JSON-объектом")
        return v

    fields = {}
    for key in ("name", "category", "manufacturer", "description"):
        value = _clean(raw.get(key))
        if value is None:
            v.errors.append(f"Поле «{key}» должно быть строкой")
            value = ""
        fields[key] = value

    if not fields["name"]:
        v.errors.append("Не указано название товара (name) — без него карточку не сформировать")
    if not fields["manufacturer"]:
        v.warnings.append("Не указан производитель (manufacturer)")
    if not fields["description"]:
        v.warnings.append("Нет текстового описания (description): текст будет построен только по характеристикам")

    specs: dict[str, str] = {}
    raw_specs = raw.get("specs")
    if raw_specs is None:
        v.warnings.append("Нет характеристик (specs)")
    elif not isinstance(raw_specs, dict):
        v.errors.append("Поле «specs» должно быть объектом вида {\"характеристика\": \"значение\"}")
    else:
        for k, val in raw_specs.items():
            name = _clean(k)
            if not name:
                v.warnings.append("Пропущена характеристика с пустым названием")
                continue
            value = _clean(val)
            if value is None:
                v.warnings.append(f"Значение «{name}» не строка и не число — проигнорировано")
                value = ""
            elif not value:
                v.warnings.append(f"Не указано значение характеристики «{name}»")
            specs[name] = value
        if not specs:
            v.warnings.append("Список характеристик (specs) пуст")

    unknown = {k for k in raw if not k.startswith("_")} - KNOWN_FIELDS
    if unknown:
        v.warnings.append("Неизвестные поля проигнорированы: " + ", ".join(sorted(unknown)))

    if not v.errors:
        v.product = Product(fields["name"], fields["manufacturer"], specs, fields["description"], fields["category"])
    return v

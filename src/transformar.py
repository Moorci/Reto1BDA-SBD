from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import date, datetime
from itertools import product
from typing import Any, Dict, Iterable, Mapping

import pandas as pd

try:
    from .config import COLUMN_ALIASES, NORMALIZATION_RULES, NON_EMPTY_VALUES
except ImportError:  # pragma: no cover
    from config import COLUMN_ALIASES, NORMALIZATION_RULES, NON_EMPTY_VALUES


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if value is pd.NA or value is pd.NaT:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(result, bool) and result


def normalize_string(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    if text.casefold() in NON_EMPTY_VALUES:
        return None
    return text or None


def normalize_column_name(column: Any) -> str:
    if column is None:
        return ""
    text = unicodedata.normalize("NFKD", str(column))
    text = text.encode("ascii", "ignore").decode("ascii").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return COLUMN_ALIASES.get(text, text)


def ensure_unique_columns(columns: Iterable[Any]) -> list[str]:
    seen: Dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        raw = normalize_column_name(column)
        base = raw or "col"
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.append(base if count == 0 else f"{base}_{count + 1}")
    return result


def normalize_municipio(value: Any) -> str | None:
    text = normalize_string(value)
    if text is None:
        return None
    text = re.sub(r"\s*/\s*", " / ", text)
    return re.sub(r"\s+", " ", text).strip()


def to_float(value: Any) -> float | None:
    if _is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if not isinstance(value, str):
        return None

    text = unicodedata.normalize("NFKC", value).strip()
    if not text or text.casefold() in NON_EMPTY_VALUES:
        return None
    text = text.replace("\u2212", "-").replace("\u00a0", "").replace(" ", "")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    for symbol in ("€", "$", "£", "%"):
        text = text.replace(symbol, "")
    text = text.replace("'", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if re.search(r",\d{1,2}$", text):
            text = text.replace(",", ".")
        elif text.count(",") > 1:
            text = text.replace(",", "")
        else:
            text = text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    elif re.search(r"\.\d{3}$", text):
        text = text.replace(".", "")

    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return -parsed if negative else parsed


def parse_date(value: Any) -> datetime | str | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = normalize_string(value)
    if text is None:
        return None
    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    )
    for date_format in formats:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    return text


def normalize_scalar(
    field_name: str,
    value: Any,
    issues: list[str] | None = None,
) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, (list, tuple)):
        return [normalize_scalar(field_name, item, issues) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            field = normalize_column_name(key)
            normalized[field or "col"] = normalize_scalar(field, item, issues)
        return normalized

    field = normalize_column_name(field_name)
    if field in NORMALIZATION_RULES["municipio_fields"]:
        return normalize_municipio(value)
    if field in NORMALIZATION_RULES["number_fields"]:
        parsed = to_float(value)
        if parsed is None:
            original = normalize_string(value)
            if original is not None and issues is not None:
                issues.append(f"{field}: valor numérico no interpretable {original!r}")
            return original
        if (
            field in NORMALIZATION_RULES["non_negative_fields"]
            and parsed < 0
            and issues is not None
        ):
            issues.append(f"{field}: valor negativo incoherente {parsed}")
        return parsed
    if field in NORMALIZATION_RULES["date_fields"]:
        parsed_date = parse_date(value)
        if (
            isinstance(parsed_date, str)
            and not re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", parsed_date)
            and issues is not None
        ):
            issues.append(f"{field}: fecha no interpretable {parsed_date!r}")
        return parsed_date
    return normalize_string(value)


def normalize_record_with_issues(
    record: Mapping[str, Any],
    *,
    dataset_hint: str = "",
) -> tuple[Dict[str, Any], list[str]]:
    if not isinstance(record, Mapping):
        return {}, ["registro que no es un objeto"]

    raw_fields = [
        (raw_key, normalize_column_name(raw_key))
        for raw_key in record
    ]
    normalized_names = {name for _, name in raw_fields if name}
    result: Dict[str, Any] = {}
    issues: list[str] = []
    for raw_key, normalized_name in raw_fields:
        if not normalized_name:
            issues.append(f"encabezado vacío descartado: {raw_key!r}")
            continue
        alias = COLUMN_ALIASES.get(normalized_name, normalized_name)
        field = (
            normalized_name
            if alias != normalized_name and alias in normalized_names
            else alias
        )
        if field in result:
            suffix = 2
            while f"{field}_{suffix}" in result:
                suffix += 1
            issues.append(f"colisión de columnas normalizada: {field!r}")
            field = f"{field}_{suffix}"
        result[field] = normalize_scalar(field, record[raw_key], issues)

    hint = dataset_hint.casefold()
    if "vivienda" in hint or "alquiler" in hint:
        for field in ("municipio", "localidad", "territorio"):
            if field in result and result[field] is not None:
                result[field] = normalize_municipio(result[field])
    return result, issues


def normalize_record(
    record: Mapping[str, Any],
    *,
    dataset_hint: str = "",
) -> Dict[str, Any]:
    normalized, _ = normalize_record_with_issues(record, dataset_hint=dataset_hint)
    return normalized


def normalize_dataset_records(
    records: Iterable[Mapping[str, Any]],
    *,
    dataset_hint: str = "",
) -> list[dict]:
    cleaned: list[dict] = []
    for entry in records:
        if not isinstance(entry, Mapping):
            continue
        normalized = normalize_record(entry, dataset_hint=dataset_hint)
        if normalized:
            cleaned.append(normalized)
    return cleaned


def flatten_eustat_table(data: Any) -> list[dict] | None:
    if not isinstance(data, dict):
        return None
    dimensions = data.get("dimension")
    values = data.get("value")
    if not isinstance(dimensions, dict) or not isinstance(values, list):
        return None

    categories: list[tuple[str, list[tuple[str, str]]]] = []
    for dimension, definition in dimensions.items():
        if dimension in {"id", "size", "role"} or not isinstance(definition, dict):
            continue
        category = definition.get("category")
        if not isinstance(category, dict):
            continue
        indexes = category.get("index")
        labels = category.get("label")
        if not isinstance(indexes, dict) or not isinstance(labels, dict):
            continue
        ordered_codes = sorted(indexes, key=lambda code: indexes[code])
        categories.append(
            (dimension, [(str(code), str(labels.get(code, code))) for code in ordered_codes])
        )

    expected_count = math.prod(len(items) for _, items in categories)
    if not categories or expected_count != len(values):
        return None

    status = data.get("status")
    records: list[dict] = []
    for observation_index, coordinate in enumerate(product(*(items for _, items in categories))):
        record: dict[str, Any] = {
            "indice_observacion": observation_index,
            "descripcion_tabla": data.get("label"),
            "fuente_estadistica": data.get("source"),
            "actualizado_fuente": data.get("updated"),
            "valor": values[observation_index],
        }
        for (dimension, _), (code, label) in zip(categories, coordinate):
            field = normalize_column_name(dimension) or "dimension"
            record[field] = label
            record[f"{field}_codigo"] = code
        if isinstance(status, dict) and str(observation_index) in status:
            record["estado_valor"] = status[str(observation_index)]
        records.append(record)
    return records


def flatten_json_records(data: Any) -> list[dict]:
    if data is None:
        return []
    eustat_records = flatten_eustat_table(data)
    if eustat_records is not None:
        return eustat_records
    if isinstance(data, list):
        result: list[dict] = []
        for item in data:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, list):
                result.extend(flatten_json_records(item))
        return result
    if isinstance(data, dict):
        candidate_keys = (
            "datos",
            "data",
            "results",
            "records",
            "items",
            "series",
            "observaciones",
        )
        for key in candidate_keys:
            if key in data:
                flattened = flatten_json_records(data[key])
                if flattened:
                    return flattened
        return [dict(data)]
    return []


def source_key(
    record: Mapping[str, Any],
    *,
    fallback_fields: Iterable[str] | None = None,
) -> str | None:
    if not isinstance(record, Mapping) or not record:
        return None
    fields = sorted(record)
    if fallback_fields:
        fields = sorted(set(fields).union(fallback_fields))
    payload = json.dumps(
        {field: record.get(field) for field in fields},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def serialize_doc(document: Mapping[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, default=str)

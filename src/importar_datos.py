from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import logging
import re
import warnings
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
from pymongo import MongoClient, UpdateOne, errors

try:
    from .config import (
        BASE_DIR,
        CSV_DELIMITERS,
        DATA_ROOTS,
        DATASET_RULES,
        DEFAULT_ENCODINGS,
        EXCLUDED_DIR_NAMES,
        MONGO_URI,
        PHASE3_DATABASE_NAME,
        SUPPORTED_EXTENSIONS,
        DB_NAME,
    )
    from .transformar import (
        ensure_unique_columns,
        flatten_json_records,
        normalize_record_with_issues,
        serialize_doc,
        to_float,
    )
except ImportError:  # pragma: no cover
    from config import (
        BASE_DIR,
        CSV_DELIMITERS,
        DATA_ROOTS,
        DATASET_RULES,
        DEFAULT_ENCODINGS,
        EXCLUDED_DIR_NAMES,
        MONGO_URI,
        PHASE3_DATABASE_NAME,
        SUPPORTED_EXTENSIONS,
        DB_NAME,
    )
    from transformar import (
        ensure_unique_columns,
        flatten_json_records,
        normalize_record_with_issues,
        serialize_doc,
        to_float,
    )


LOGGER = logging.getLogger("importar_datos")
DEFAULT_BATCH_SIZE = 500
YEAR_COLUMN = re.compile(
    r"^(.*?)(?:_)?((?:19|20)\d{2})(?:_(I|II|III|IV|[1-4]))?$",
    re.IGNORECASE,
)
YEAR_VALUE = re.compile(r"^(?:19|20)\d{2}$")
QUARTER_VALUE = re.compile(r"^(?:I|II|III|IV|1|2|3|4)$", re.IGNORECASE)


@dataclass(frozen=True)
class SourceRecord:
    values: dict[str, Any]
    row_number: int
    sheet_name: str | None = None
    period_context: str | None = None


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def discover_data_files(project_root: Path | str = BASE_DIR) -> list[Path]:
    root = Path(project_root).expanduser().resolve()
    seen: set[Path] = set()
    files: list[Path] = []
    for folder_name in DATA_ROOTS:
        data_root = root / DATA_ROOTS[folder_name].name
        if not data_root.exists():
            continue
        for path in data_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    return sorted(files, key=lambda item: str(item).casefold())


def _decode_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    last_error: UnicodeDecodeError | None = None
    for encoding in DEFAULT_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is None:
        raise UnicodeError(f"No se pudo seleccionar una codificación para {path}")
    raise UnicodeError(f"No se pudo decodificar {path}: {last_error}") from last_error


def guess_delimiter(sample: str) -> str:
    sample = sample[:65536]
    if not sample.strip():
        return ";"
    scores: list[tuple[int, int, int, str]] = []
    for delimiter in CSV_DELIMITERS:
        try:
            rows = list(csv.reader(io.StringIO(sample), delimiter=delimiter))[:80]
        except csv.Error:
            continue
        widths = [len(row) for row in rows if any(cell.strip() for cell in row)]
        if not widths:
            continue
        frequencies = Counter(width for width in widths if width > 1)
        if frequencies:
            modal_width, modal_count = frequencies.most_common(1)[0]
            scores.append((modal_width, modal_count, max(widths), delimiter))
        else:
            scores.append((1, len(widths), max(widths), delimiter))
    if not scores:
        return ";"
    return max(scores)[-1]


def _nonempty(row: Sequence[Any]) -> list[str]:
    return [str(value).strip() for value in row if value is not None and str(value).strip()]


def _header_index(rows: Sequence[Sequence[Any]]) -> int:
    for index in range(1, min(len(rows), 50)):
        quarter_count = sum(
            bool(QUARTER_VALUE.fullmatch(cell)) for cell in _nonempty(rows[index])
        )
        previous_year_count = sum(
            bool(YEAR_VALUE.fullmatch(cell)) for cell in _nonempty(rows[index - 1])
        )
        if quarter_count >= 3 and previous_year_count >= 3:
            return index

    year_headers = [
        (sum(bool(YEAR_VALUE.fullmatch(cell)) for cell in _nonempty(row)), index)
        for index, row in enumerate(rows[:50])
    ]
    year_count, year_index = max(year_headers, default=(0, 0))
    if year_count >= 3:
        return year_index

    keywords = (
        "municipio",
        "territorio",
        "salario",
        "renta",
        "remuneracion",
        "precio",
        "fecha",
        "periodo",
        "indicador",
        "sexo",
        "edad",
        "provincia",
        "codigo",
        "trimestre",
        "anio",
        "poblacion",
        "valor",
        "total",
        "alquiler",
        "vivienda",
    )
    best_index = 0
    best_score = float("-inf")
    for index, row in enumerate(rows[:50]):
        cells = _nonempty(row)
        if not cells:
            continue
        text_cells = sum(bool(re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", cell)) for cell in cells)
        keyword_cells = sum(
            any(keyword in cell.casefold() for keyword in keywords) for cell in cells
        )
        next_rows = rows[index + 1 : index + 4]
        matching_rows = sum(
            abs(len(_nonempty(next_row)) - len(cells)) <= max(2, len(cells) // 5)
            for next_row in next_rows
            if _nonempty(next_row)
        )
        score = len(cells) * 1.8 + keyword_cells * 2.5 + text_cells * 0.25 + matching_rows
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def _make_headers(rows: Sequence[Sequence[Any]], header_index: int) -> list[str]:
    current = list(rows[header_index])
    previous = list(rows[header_index - 1]) if header_index > 0 else []
    current += [None] * max(0, len(previous) - len(current))
    previous += [None] * max(0, len(current) - len(previous))

    parent_has_labels = (
        bool(previous)
        and not str(previous[0] or "").strip()
        and sum(bool(str(value or "").strip()) for value in previous) >= 2
        and not any(str(value or "").strip() for value in current[:1])
    )
    headers: list[str] = []
    parent = ""
    for index, value in enumerate(current):
        child = str(value or "").strip()
        parent_value = str(previous[index] or "").strip() if parent_has_labels else ""
        if parent_value:
            parent = parent_value
        if parent_has_labels and parent:
            if child:
                headers.append(f"{parent}_{child}")
            else:
                headers.append(parent)
        else:
            headers.append(child)

    if headers and not headers[0].strip():
        headers[0] = "entidad"
    return ensure_unique_columns(headers)


def _rows_to_source_records(
    rows: Sequence[Sequence[Any]],
    *,
    sheet_name: str | None = None,
) -> list[SourceRecord]:
    if not rows:
        return []
    header_index = _header_index(rows)
    headers = _make_headers(rows, header_index)
    records: list[SourceRecord] = []
    year_context: str | None = None

    for row_index in range(header_index + 1, len(rows)):
        row = list(rows[row_index])
        values = [str(value).strip() if value is not None else "" for value in row]
        nonempty = [value for value in values if value]
        if not nonempty:
            continue
        if (
            len(nonempty) == 1
            and not YEAR_VALUE.fullmatch(nonempty[0])
            and not QUARTER_VALUE.fullmatch(nonempty[0])
        ):
            continue
        if len(nonempty) == 1 and YEAR_VALUE.fullmatch(nonempty[0]):
            year_context = nonempty[0]
            continue

        period_context = None
        if year_context and values and QUARTER_VALUE.fullmatch(values[0]):
            quarter = values[0].upper()
            period_context = f"{year_context}-{quarter}"

        if len(values) > len(headers):
            extra_headers = [
                f"col_{index + 1}" for index in range(len(headers), len(values))
            ]
            headers.extend(extra_headers)
        padded = values + [None] * max(0, len(headers) - len(values))
        record = {
            headers[index]: padded[index] or None
            for index in range(len(headers))
        }
        records.append(
            SourceRecord(
                values=record,
                row_number=row_index + 1,
                sheet_name=sheet_name,
                period_context=period_context,
            )
        )
    return records


def _read_csv_source_records(path: Path) -> list[SourceRecord]:
    raw_text, encoding = _decode_text(path)
    if not raw_text.strip():
        return []
    delimiter = guess_delimiter(raw_text)
    try:
        rows = list(csv.reader(io.StringIO(raw_text, newline=""), delimiter=delimiter))
    except csv.Error as exc:
        raise ValueError(f"CSV no válido con separador {delimiter!r}: {exc}") from exc
    records = _rows_to_source_records(rows)
    LOGGER.debug(
        "%s: separador=%r codificación=%s registros=%d",
        path,
        delimiter,
        encoding,
        len(records),
    )
    return records


def read_csv_records(path: Path) -> list[dict]:
    return [record.values for record in _read_csv_source_records(path)]


def extract_dataframe_records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    rows = frame.astype(object).where(pd.notna(frame), None).values.tolist()
    return [
        record.values
        for record in _rows_to_source_records(rows)
    ]


def _read_excel_source_records(path: Path) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        workbook = pd.ExcelFile(path)
        for sheet_name in workbook.sheet_names:
            frame = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                header=None,
                dtype=object,
            )
            if frame.empty:
                continue
            rows = frame.astype(object).where(pd.notna(frame), None).values.tolist()
            records.extend(
                _rows_to_source_records(rows, sheet_name=sheet_name)
            )
    for warning in caught:
        LOGGER.warning(
            "%s: aviso al leer Excel (%s): %s",
            path.name,
            warning.category.__name__,
            warning.message,
        )
    return records


def read_excel_records(path: Path) -> list[dict]:
    return [record.values for record in _read_excel_source_records(path)]


def read_json_records(path: Path) -> list[dict]:
    text, _ = _decode_text(path)
    if not text.strip():
        return []
    data = json.loads(text)
    return flatten_json_records(data)


class _ScriptJSONParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[tuple[dict[str, str], str]] = []
        self._active_attributes: dict[str, str] | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "script":
            self._active_attributes = {
                key.casefold(): value or "" for key, value in attrs
            }
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_attributes is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._active_attributes is not None:
            self.scripts.append((self._active_attributes, "".join(self._active_text)))
            self._active_attributes = None
            self._active_text = []


def _period_from_fotocasa(value: Any) -> str | None:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return text
    return None


def read_html_records(path: Path) -> list[dict]:
    text, _ = _decode_text(path)
    parser = _ScriptJSONParser()
    parser.feed(text)
    initial_props: dict[str, Any] | None = None
    json_records: list[dict] = []

    for attrs, script_text in parser.scripts:
        script_id = attrs.get("id", "")
        content_type = attrs.get("type", "").casefold()
        if not script_text.strip() or not (
            script_id in {"__initial_props__", "__NEXT_DATA__"}
            or content_type == "application/ld+json"
        ):
            continue
        try:
            payload = json.loads(script_text)
        except json.JSONDecodeError as exc:
            if script_id == "__initial_props__":
                raise ValueError(
                    f"JSON embebido inválido en {path.name}: {exc}"
                ) from exc
            LOGGER.warning("%s: se omite un bloque JSON-LD mal formado: %s", path.name, exc)
            continue

        if script_id == "__initial_props__" and isinstance(payload, dict):
            initial_props = payload
        elif isinstance(payload, dict):
            json_records.extend(flatten_json_records(payload))

    if initial_props is None:
        return json_records

    municipality = initial_props.get("municipality")
    if not isinstance(municipality, dict):
        return json_records
    common = {
        "municipio": municipality.get("name"),
        "municipio_codigo": municipality.get("id"),
        "provincia": municipality.get("provinceName"),
    }
    evolution = municipality.get("priceEvolution")
    if isinstance(evolution, dict):
        for operation, points in evolution.items():
            if not isinstance(points, list):
                continue
            for point in points:
                if not isinstance(point, dict):
                    continue
                period = _period_from_fotocasa(point.get("period"))
                value = point.get("meanPriceSqm")
                if period is None or value is None:
                    continue
                json_records.append(
                    {
                        **common,
                        "tipo_operacion": operation,
                        "periodo": period,
                        "precio_eur_m2": value,
                    }
                )
    if not json_records:
        summary = {
            **common,
            "precio_medio_eur_m2": municipality.get("meanPriceSqm"),
            "precio_mediano_eur_m2": municipality.get("medianPriceSqm"),
            "alquiler_mediano_eur_m2": municipality.get("medianRentPriceSqm"),
        }
        json_records.append(summary)
    return json_records


def read_file_records(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return read_csv_records(path)
    if suffix == ".json":
        return read_json_records(path)
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return read_excel_records(path)
    if suffix == ".html":
        return read_html_records(path)
    return []


def _measure_for_file(path: Path, column_prefix: str = "") -> tuple[str, str | None]:
    name = path.name.casefold()
    prefix = column_prefix.casefold()
    if "xls0017789" in name:
        return "renta_mensual_media_eur", "euros/mes"
    if "xls0017999" in name:
        return "renta_mensual_eur_m2", "euros/m2"
    if name == "remumedia.csv":
        if "hora" in prefix:
            return "remuneracion_neta_hora_eur", "euros/hora"
        return "remuneracion_neta_mensual_eur", "euros/mes"
    if "remumediatotal" in name:
        if "hora" in prefix:
            return "remuneracion_neta_hora_eur", "euros/hora"
        return "remuneracion_neta_mensual_eur", "euros/mes"
    if "sincontratos" in name:
        return "porcentaje_sin_contrato_indefinido", "%"
    if "preciom2" in name:
        return "precio_venta_eur_m2", "euros/m2"
    if "renta_anual" in name:
        return "renta_anual_eur", "euros/anio"
    if prefix:
        return prefix, None
    return "valor", None


def _period_column(name: str) -> tuple[str, str] | None:
    match = YEAR_COLUMN.fullmatch(name)
    if match is None:
        return None
    prefix, year, quarter = match.groups()
    if re.search(r"(?:^|_)a_31_12_$", prefix):
        return None
    period = year if quarter is None else f"{year}-{quarter.upper()}"
    return prefix.rstrip("_"), period


def _expand_wide_record(
    record: dict[str, Any],
    path: Path,
    period_context: str | None,
    *,
    current_sex: str | None = None,
) -> list[dict[str, Any]]:
    if "preciom2" in path.name.casefold() and period_context:
        territory_tokens = (
            ("c_a_de_euskadi", "C.A. de Euskadi"),
            ("araba_alava", "Araba/Álava"),
            ("bizkaia", "Bizkaia"),
            ("gipuzkoa", "Gipuzkoa"),
        )
        dwelling_types = (
            ("viviendas_nuevas", "nueva"),
            ("viviendas_usadas", "usada"),
            ("total", "total"),
        )
        expanded = []
        for key, value in record.items():
            parsed = to_float(value)
            if parsed is None:
                continue
            territory = next(
                (label for token, label in territory_tokens if key.startswith(token)),
                None,
            )
            dwelling_type = next(
                (label for token, label in dwelling_types if key.endswith(token)),
                None,
            )
            if territory is None or dwelling_type is None:
                continue
            expanded.append(
                {
                    "territorio": territory,
                    "tipo_vivienda": dwelling_type,
                    "periodo": period_context,
                    "indicador": "precio_venta_eur_m2",
                    "valor": parsed,
                    "unidad": "euros/m2",
                }
            )
        return expanded

    period_columns = {
        key: _period_column(key)
        for key in record
    }
    period_columns = {
        key: period for key, period in period_columns.items() if period is not None
    }
    if not period_columns and period_context is None:
        return [record]

    label = record.get("entidad")
    base = {
        key: value
        for key, value in record.items()
        if key not in period_columns
    }
    if label is not None:
        base.setdefault("grupo", label)

    hint = path.name.casefold()
    if "remumedia" in hint:
        if label and str(label).casefold() in {"hombre", "mujer"}:
            current_sex = str(label).capitalize()
        base["sexo"] = current_sex or "Total"
        if label and re.fullmatch(r"\d{2}-\d{2}", str(label)):
            base["edad"] = str(label)
        else:
            base.setdefault("edad", "Total")
    elif "renta_anual_hombres" in hint:
        base["sexo"] = "Hombres"
    elif "renta_anual_mujeres" in hint:
        base["sexo"] = "Mujeres"

    expanded: list[dict[str, Any]] = []
    if period_columns:
        for column, period in period_columns.items():
            assert period is not None
            prefix, period_label = period
            indicator, unit = _measure_for_file(path, prefix)
            value = to_float(record[column])
            if value is None and record[column] is not None:
                continue
            item = {
                **base,
                "periodo": period_label,
                "indicador": indicator,
                "valor": value,
            }
            if unit is not None:
                item["unidad"] = unit
            expanded.append(item)
        return expanded

    indicator, unit = _measure_for_file(path)
    item = {
        **base,
        "periodo": period_context,
        "indicador": indicator,
        "valor": to_float(record.get("valor")),
    }
    if unit is not None:
        item["unidad"] = unit
    return [item]


def choose_collection(path: Path, records: Sequence[dict]) -> str:
    path_text = str(path).casefold()
    keys = {
        str(key).casefold()
        for record in records[:10]
        for key in record
    }
    operation_values = {
        str(record.get("tipo_operacion", record.get("tipo", ""))).casefold()
        for record in records[:20]
    }
    if "viviendometro-ccaa.csv" in path_text:
        return "indicadores_geograficos"
    if "series_historicas" in path_text:
        return "precios_vivienda"
    if operation_values.intersection({"alquiler", "rent"}):
        return "alquiler_vivienda"
    if operation_values.intersection({"venta", "sale", "sell", "compra"}):
        return "vivienda_venta"

    combined = f"{path_text} {' '.join(keys)}"
    for rule in DATASET_RULES:
        if any(pattern in combined for pattern in rule["patterns"]):
            return str(rule["collection"])
    if {"precio_eur", "metros_m2"}.issubset(keys) or "url" in keys:
        return "vivienda_venta"
    if {"municipio", "total"}.issubset(keys) and any(
        word in combined for word in ("demandantes", "empadronado", "etxebide")
    ):
        return "vivienda_protegida"
    if any(key in keys for key in ("municipio", "municipio_codigo", "territorio")):
        return "indicadores_geograficos"
    return "datos_genericos"


def _identity_for_record(
    record: dict[str, Any],
    source_file: str,
    source_row: int,
    source_sheet: str | None,
) -> str:
    identity = {
        "source_file": source_file,
        "source_row": source_row,
        "source_sheet": source_sheet,
        "record": record,
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metadata_field(document: dict[str, Any]) -> str:
    field = "_import_metadata"
    suffix = 2
    while field in document:
        field = f"_import_metadata_{suffix}"
        suffix += 1
    return field


def build_document(
    record: dict,
    path: Path,
    collection_name: str,
    *,
    project_root: Path = BASE_DIR,
    source_row: int = 0,
    source_sheet: str | None = None,
    imported_at: datetime | None = None,
) -> dict:
    document = dict(record)
    source_file = _relative_path(path, project_root)
    source_id = _identity_for_record(document, source_file, source_row, source_sheet)
    if "id" in document:
        original_id_field = "id_origen"
        suffix = 2
        while original_id_field in document:
            original_id_field = f"id_origen_{suffix}"
            suffix += 1
        document[original_id_field] = document.pop("id")

    metadata_key = _metadata_field(document)
    metadata: dict[str, Any] = {
        "source_id": source_id,
        "source_file": source_file,
        "source_row": source_row,
        "collection": collection_name,
    }
    if source_sheet is not None:
        metadata["source_sheet"] = source_sheet
    if imported_at is not None:
        metadata["imported_at"] = imported_at
    document[metadata_key] = metadata
    document["_source_id"] = source_id
    document["_id"] = source_id
    return document


def _write_batch(collection: Any, operations: list[UpdateOne]) -> tuple[int, int, int, int]:
    try:
        result = collection.bulk_write(operations, ordered=False)
        return (
            int(result.upserted_count),
            int(result.modified_count),
            int(result.matched_count),
            0,
        )
    except errors.BulkWriteError as exc:
        details = exc.details or {}
        return (
            int(details.get("nUpserted", 0)),
            int(details.get("nModified", 0)),
            int(details.get("nMatched", 0)),
            len(details.get("writeErrors", [])),
        )


def _process_file_records(
    source_records: Sequence[SourceRecord],
    path: Path,
) -> tuple[list[tuple[dict[str, Any], int, str | None]], Counter[str], int]:
    prepared: list[tuple[dict[str, Any], int, str | None]] = []
    warnings_count: Counter[str] = Counter()
    exact_rows: set[str] = set()
    duplicate_rows = 0
    current_sex: str | None = None

    for source_record in source_records:
        normalized, issues = normalize_record_with_issues(
            source_record.values,
            dataset_hint=path.name.lower(),
        )
        for issue in issues:
            warnings_count[issue.split(":", 1)[0]] += 1
        if not normalized:
            warnings_count["registro vacío"] += 1
            continue
        period = normalized.get("fecha")
        if (
            "series_historicas" in path.name.casefold()
            and isinstance(period, str)
            and re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", period)
        ):
            normalized["periodo"] = period

        row_signature = serialize_doc(normalized)
        if row_signature in exact_rows:
            duplicate_rows += 1
        else:
            exact_rows.add(row_signature)

        if "remumedia" in path.name.casefold():
            label = normalized.get("entidad")
            if isinstance(label, str) and label.casefold() in {"hombre", "mujer"}:
                current_sex = label.capitalize()
        expanded = _expand_wide_record(
            normalized,
            path,
            source_record.period_context,
            current_sex=current_sex,
        )
        if not expanded:
            warnings_count["registro sin medidas importables"] += 1
            continue

        for document in expanded:
            if document.get("municipio") is None:
                official_name = document.get("municipio_oficial")
                if official_name is not None:
                    document["municipio"] = official_name
            prepared.append((document, source_record.row_number, source_record.sheet_name))

    if duplicate_rows:
        warnings_count["filas idénticas conservadas"] += duplicate_rows
    return prepared, warnings_count, duplicate_rows


def import_collection(
    client: MongoClient | None,
    path: Path,
    database_name: str = DB_NAME,
    *,
    project_root: Path = BASE_DIR,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    source_records = _read_source_records(path)
    if not source_records:
        return {
            "archivo": _relative_path(path, project_root),
            "collection": "skip",
            "registros_leidos": 0,
            "inserciones": 0,
            "actualizaciones": 0,
            "sin_cambios": 0,
            "omitidos": 0,
            "errores": 0,
            "advertencias": 0,
        }

    collection_name = choose_collection(path, [record.values for record in source_records])
    prepared, warning_counts, _ = _process_file_records(
        source_records,
        path,
    )
    stats: dict[str, Any] = {
        "archivo": _relative_path(path, project_root),
        "collection": collection_name,
        "registros_leidos": len(source_records),
        "registros_transformados": len(prepared),
        "inserciones": 0,
        "actualizaciones": 0,
        "sin_cambios": 0,
        "omitidos": max(len(source_records) - len(prepared), 0),
        "errores": 0,
        "advertencias": sum(warning_counts.values()),
    }

    if warning_counts:
        summary = ", ".join(
            f"{name}: {count}"
            for name, count in warning_counts.most_common(5)
        )
        LOGGER.warning("%s: advertencias de calidad: %s", stats["archivo"], summary)

    if dry_run:
        stats["omitidos"] = 0
        return stats
    if client is None:
        raise ValueError("Se necesita una conexión MongoDB para importar.")

    collection = client[database_name][collection_name]
    now = datetime.now(timezone.utc)
    for start in range(0, len(prepared), batch_size):
        batch = prepared[start : start + batch_size]
        operations: list[UpdateOne] = []
        for record, row_number, sheet_name in batch:
            try:
                document = build_document(
                    record,
                    path,
                    collection_name,
                    project_root=project_root,
                    source_row=row_number,
                    source_sheet=sheet_name,
                    imported_at=now,
                )
                source_id = document.pop("_id")
                metadata_key = next(
                    key
                    for key, value in document.items()
                    if key.startswith("_import_metadata")
                    and isinstance(value, dict)
                    and value.get("source_id") == source_id
                )
                metadata = document[metadata_key]
                imported_at = metadata.pop("imported_at")
                document.pop(metadata_key)
                metadata["imported_at"] = imported_at
                operations.append(
                    UpdateOne(
                        {"_id": source_id},
                        {
                            "$set": document,
                            "$setOnInsert": {
                                "_id": source_id,
                                metadata_key: metadata,
                            },
                        },
                        upsert=True,
                    )
                )
            except Exception as exc:
                stats["errores"] += 1
                LOGGER.error(
                    "%s, fila %s: no se pudo preparar el registro: %s",
                    stats["archivo"],
                    row_number,
                    exc,
                )

        if not operations:
            continue
        inserted, modified, matched, write_errors = _write_batch(collection, operations)
        stats["inserciones"] += inserted
        stats["actualizaciones"] += modified
        stats["sin_cambios"] += max(matched - modified, 0)
        stats["errores"] += write_errors
        if write_errors:
            LOGGER.error(
                "%s: %d errores de escritura en un lote de %d registros",
                stats["archivo"],
                write_errors,
                len(operations),
            )
        stats["omitidos"] = max(
            stats["registros_leidos"]
            - stats["inserciones"]
            - stats["actualizaciones"]
            - stats["sin_cambios"]
            - stats["errores"],
            0,
        )

    collection.create_index(
        [("_import_metadata.source_file", 1)],
        name="source_file_lookup",
        background=True,
    )
    return stats


def _read_source_records(path: Path) -> list[SourceRecord]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return _read_csv_source_records(path)
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return _read_excel_source_records(path)
    if suffix == ".json":
        text, _ = _decode_text(path)
        if not text.strip():
            return []
        values = flatten_json_records(json.loads(text))
        return [SourceRecord(value, index + 1) for index, value in enumerate(values)]
    if suffix == ".html":
        values = read_html_records(path)
        return [SourceRecord(value, index + 1) for index, value in enumerate(values)]
    return []


def _source_filter(filename: str) -> dict[str, Any]:
    return {
        "_import_metadata.source_file": {
            "$regex": re.escape(filename) + "$",
            "$options": "i",
        }
    }


def analysis_pipelines() -> dict[str, tuple[str, list[dict[str, Any]]]]:
    fotocasa_match = {
        **_source_filter("series_historicas_251_municipios.csv"),
        "tipo": {"$in": ["alquiler", "rent"]},
        "precio_eur_m2": {"$type": "number", "$gt": 0},
        "periodo": {"$type": "string"},
    }
    sale_match = {
        **fotocasa_match,
        "tipo": {"$in": ["venta", "sale", "sell", "compra"]},
    }
    emal_match = {
        **_source_filter("xls0017789_c.csv"),
        "entidad": {"$regex": "^\\s*(euskadi|c\\.a\\. de euskadi)$", "$options": "i"},
        "indicador": "renta_mensual_media_eur",
        "valor": {"$type": "number", "$gt": 0},
        "periodo": {"$type": "string"},
    }
    salary_match = {
        **_source_filter("remuMedia.csv"),
        "edad": "16-29",
        "indicador": "remuneracion_neta_mensual_eur",
        "valor": {"$type": "number", "$gt": 0},
        "periodo": {"$type": "string"},
    }
    demand_match = {
        **_source_filter("Demandantes-Etxebide-Municipio-2026-07-01_limpio.csv"),
        "municipio": {"$type": "string"},
        "grupo": {"$regex": "^\\s*TOTAL\\s*$", "$options": "i"},
        "literal": {
            "$regex": "^\\s*Kopuru absolutua\\s*/\\s*No Absoluto\\s*$",
            "$options": "i",
        },
        "total": {"$type": "number", "$gte": 0},
    }
    return {
        "alquiler_fotocasa": (
            "precios_vivienda",
            [
                {"$match": fotocasa_match},
                {
                    "$group": {
                        "_id": "$periodo",
                        "precio_medio_eur_m2": {"$avg": "$precio_eur_m2"},
                        "municipios": {"$addToSet": "$municipio_codigo"},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "periodo": "$_id",
                        "precio_medio_eur_m2": 1,
                        "municipios": {"$size": "$municipios"},
                    }
                },
                {"$sort": {"periodo": 1}},
            ],
        ),
        "venta_fotocasa": (
            "precios_vivienda",
            [
                {"$match": sale_match},
                {
                    "$group": {
                        "_id": "$periodo",
                        "precio_medio_eur_m2": {"$avg": "$precio_eur_m2"},
                        "municipios": {"$addToSet": "$municipio_codigo"},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "periodo": "$_id",
                        "precio_medio_eur_m2": 1,
                        "municipios": {"$size": "$municipios"},
                    }
                },
                {"$sort": {"periodo": 1}},
            ],
        ),
        "alquiler_emal_euskadi": (
            "alquiler_vivienda",
            [
                {"$match": emal_match},
                {
                    "$group": {
                        "_id": "$periodo",
                        "renta_mensual_media_eur": {"$avg": "$valor"},
                        "observaciones": {"$sum": 1},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "periodo": "$_id",
                        "renta_mensual_media_eur": 1,
                        "observaciones": 1,
                    }
                },
                {"$sort": {"periodo": 1}},
            ],
        ),
        "salario_joven": (
            "salarios",
            [
                {"$match": salary_match},
                {
                    "$group": {
                        "_id": {"periodo": "$periodo", "sexo": "$sexo"},
                        "remuneracion_neta_mensual_eur": {"$avg": "$valor"},
                        "observaciones": {"$sum": 1},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "periodo": "$_id.periodo",
                        "sexo": "$_id.sexo",
                        "remuneracion_neta_mensual_eur": 1,
                        "observaciones": 1,
                    }
                },
                {"$sort": {"periodo": 1, "sexo": 1}},
            ],
        ),
        "demanda_vpo_municipal": (
            "vivienda_protegida",
            [
                {"$match": demand_match},
                {
                    "$group": {
                        "_id": "$municipio",
                        "solicitudes_publicadas": {"$sum": "$total"},
                        "filas_publicadas": {"$sum": 1},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "municipio": "$_id",
                        "solicitudes_publicadas": 1,
                        "filas_publicadas": 1,
                    }
                },
                {"$sort": {"solicitudes_publicadas": -1}},
                {"$limit": 20},
            ],
        ),
    }


def run_analysis(database: Any) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    for name, (collection_name, pipeline) in analysis_pipelines().items():
        results[name] = list(
            database[collection_name].aggregate(pipeline, allowDiskUse=True)
        )
    return results


def _svg_chart(
    title: str,
    rows: Sequence[dict[str, Any]],
    *,
    x_key: str,
    y_keys: Sequence[tuple[str, str]],
    y_unit: str,
) -> str:
    width, height = 780, 330
    left, right, top, bottom = 64, 18, 38, 74
    chart_width = width - left - right
    chart_height = height - top - bottom
    svg: list[str] = [
        f'<svg role="img" aria-label="{html.escape(title)}" '
        f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="{width / 2}" y="22" text-anchor="middle" class="chart-title">'
        f"{html.escape(title)}</text>",
    ]
    numeric_values = [
        float(row[key])
        for row in rows
        for key, _ in y_keys
        if isinstance(row.get(key), (int, float))
    ]
    if not numeric_values:
        return (
            f'<figure><figcaption>{html.escape(title)}</figcaption>'
            '<p>Sin observaciones válidas en MongoDB para este indicador.</p></figure>'
        )
    minimum, maximum = min(numeric_values), max(numeric_values)
    if minimum == maximum:
        minimum = min(0.0, minimum)
        maximum = maximum or 1.0
    padding = (maximum - minimum) * 0.08
    minimum -= padding
    maximum += padding
    svg.append(
        f'<line x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" '
        f'y2="{top + chart_height}" stroke="#64748b"/>'
    )
    svg.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}" '
        f'stroke="#64748b"/>'
    )
    for grid in range(5):
        value = minimum + (maximum - minimum) * grid / 4
        y = top + chart_height - chart_height * grid / 4
        svg.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_width}" '
            f'y2="{y:.1f}" stroke="#e2e8f0"/>'
        )
        svg.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">'
            f"{value:.1f}</text>"
        )
    svg.append(
        f'<text x="16" y="{top + chart_height / 2:.1f}" '
        f'transform="rotate(-90 16 {top + chart_height / 2:.1f})" '
        f'text-anchor="middle">{html.escape(y_unit)}</text>'
    )
    points_count = max(len(rows), 1)
    x_values = [str(row.get(x_key, "")) for row in rows]
    for series_index, (key, label) in enumerate(y_keys):
        color = ("#2563eb", "#dc2626", "#059669", "#7c3aed")[series_index % 4]
        points: list[str] = []
        for index, row in enumerate(rows):
            value = row.get(key)
            if not isinstance(value, (int, float)):
                continue
            x = left + (chart_width * index / max(points_count - 1, 1))
            y = top + chart_height - chart_height * (float(value) - minimum) / (
                maximum - minimum
            )
            points.append(f"{x:.1f},{y:.1f}")
            svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.8" fill="{color}"/>')
        if len(points) > 1:
            svg.append(
                f'<polyline points="{" ".join(points)}" fill="none" '
                f'stroke="{color}" stroke-width="2"/>'
            )
        svg.append(
            f'<line x1="{left + 12 + series_index * 155}" y1="{height - 30}" '
            f'x2="{left + 30 + series_index * 155}" y2="{height - 30}" '
            f'stroke="{color}" stroke-width="3"/>'
        )
        svg.append(
            f'<text x="{left + 36 + series_index * 155}" y="{height - 26}">'
            f"{html.escape(label)}</text>"
        )
    if x_values:
        for index in sorted({0, len(x_values) // 2, len(x_values) - 1}):
            x = left + chart_width * index / max(points_count - 1, 1)
            svg.append(
                f'<text x="{x:.1f}" y="{height - 52}" text-anchor="middle">'
                f"{html.escape(x_values[index])}</text>"
            )
    svg.append("</svg>")
    return "<figure>" + "".join(svg) + f"<figcaption>Unidad: {html.escape(y_unit)}.</figcaption></figure>"


def _svg_bar_chart(
    title: str,
    rows: Sequence[dict[str, Any]],
    *,
    label_key: str,
    value_key: str,
    y_unit: str,
) -> str:
    valid_rows = [
        row
        for row in rows
        if isinstance(row.get(value_key), (int, float))
    ]
    if not valid_rows:
        return (
            f'<figure><figcaption>{html.escape(title)}</figcaption>'
            '<p>Sin observaciones válidas en MongoDB para este indicador.</p></figure>'
        )

    width = 900
    left, right, top, row_height = 230, 90, 46, 30
    height = top + row_height * len(valid_rows) + 24
    max_value = max(float(row[value_key]) for row in valid_rows) or 1.0
    chart_width = width - left - right
    svg = [
        f'<svg role="img" aria-label="{html.escape(title)}" '
        f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="{width / 2}" y="24" text-anchor="middle" class="chart-title">'
        f"{html.escape(title)}</text>",
    ]
    for index, row in enumerate(valid_rows):
        y = top + index * row_height
        value = float(row[value_key])
        bar_width = chart_width * value / max_value
        label = html.escape(str(row.get(label_key, "")))
        svg.extend(
            [
                f'<text x="{left - 10}" y="{y + 17}" text-anchor="end">{label}</text>',
                f'<rect x="{left}" y="{y}" width="{bar_width:.1f}" height="20" '
                'fill="#2563eb" rx="3"/>',
                f'<text x="{left + bar_width + 6:.1f}" y="{y + 16}">{value:,.0f}</text>',
            ]
        )
    svg.append("</svg>")
    return (
        "<figure>" + "".join(svg)
        + f"<figcaption>Unidad: {html.escape(y_unit)}.</figcaption></figure>"
    )


def _affordability_indicators(
    results: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    def annual_price_means(name: str) -> dict[str, float]:
        yearly_values: dict[str, list[float]] = {}
        for row in results.get(name, []):
            period = row.get("periodo")
            value = row.get("precio_medio_eur_m2")
            if (
                isinstance(period, str)
                and re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", period)
                and isinstance(value, (int, float))
                and value > 0
            ):
                yearly_values.setdefault(period[:4], []).append(float(value))
        return {
            year: sum(values) / len(values)
            for year, values in yearly_values.items()
        }

    rent_by_year = annual_price_means("alquiler_fotocasa")
    sale_by_year = annual_price_means("venta_fotocasa")
    salary_by_year_sex: dict[str, dict[str, float]] = {}
    for row in results.get("salario_joven", []):
        year = row.get("periodo")
        sex = str(row.get("sexo", "")).casefold()
        salary = row.get("remuneracion_neta_mensual_eur")
        series_key = {"hombre": "hombres", "mujer": "mujeres"}.get(sex)
        if (
            isinstance(year, str)
            and re.fullmatch(r"(?:19|20)\d{2}", year)
            and series_key is not None
            and isinstance(salary, (int, float))
            and salary > 0
        ):
            salary_by_year_sex.setdefault(year, {})[series_key] = float(salary)

    effort_rows: list[dict[str, Any]] = []
    purchase_rows: list[dict[str, Any]] = []
    for year in sorted(set(rent_by_year) & set(sale_by_year) & set(salary_by_year_sex)):
        salaries = salary_by_year_sex[year]
        if not {"hombres", "mujeres"}.issubset(salaries):
            continue
        monthly_rent = rent_by_year[year] * 60
        purchase_price = sale_by_year[year] * 60
        effort_row: dict[str, Any] = {"periodo": year}
        purchase_row: dict[str, Any] = {"periodo": year}
        for sex, salary in salaries.items():
            effort_row[sex] = monthly_rent / salary * 100
            purchase_row[sex] = purchase_price / (salary * 12)
        effort_rows.append(effort_row)
        purchase_rows.append(purchase_row)

    if not effort_rows:
        return effort_rows, purchase_rows, (
            "No hay años comunes entre las series Fotocasa de alquiler/venta y "
            "la remuneración neta de 16-29 años para estimar esfuerzo y compra."
        )

    latest = effort_rows[-1]
    year = str(latest["periodo"])
    monthly_rent = rent_by_year[year] * 60
    entry_savings = sale_by_year[year] * 60 * 0.20
    required_salary_30 = monthly_rent / 0.30
    required_salary_35 = monthly_rent / 0.35
    return effort_rows, purchase_rows, (
        f"Estimación para {year}: alquiler mensual de una vivienda tipo de 60 m² "
        f"≈ {monthly_rent:,.0f} €, salario neto mínimo para no superar el 30 % "
        f"≈ {required_salary_30:,.0f} €/mes (35 %: {required_salary_35:,.0f} €/mes), "
        f"y entrada del 20 % para compra ≈ {entry_savings:,.0f} € antes de gastos."
    )


def write_analysis_report(
    results: dict[str, list[dict[str, Any]]],
    output_path: Path,
) -> Path:
    effort_rows, purchase_rows, affordability_note = _affordability_indicators(results)
    salary_by_period: dict[str, dict[str, Any]] = {}
    for row in results.get("salario_joven", []):
        period = row.get("periodo")
        sex = str(row.get("sexo", "")).casefold()
        if not isinstance(period, str):
            continue
        series_key = {"hombre": "hombres", "mujer": "mujeres"}.get(sex)
        value = row.get("remuneracion_neta_mensual_eur")
        if series_key is None or not isinstance(value, (int, float)):
            continue
        salary_by_period.setdefault(period, {"periodo": period})[series_key] = value
    salary_rows = [
        salary_by_period[period]
        for period in sorted(salary_by_period)
    ]

    charts = [
        _svg_chart(
            "Alquiler anunciado por Fotocasa: media municipal (2020-2026)",
            results.get("alquiler_fotocasa", []),
            x_key="periodo",
            y_keys=[("precio_medio_eur_m2", "EUR/m2")],
            y_unit="EUR/m2",
        ),
        _svg_chart(
            "Alquiler libre en Euskadi: contratos nuevos (EMAL)",
            results.get("alquiler_emal_euskadi", []),
            x_key="periodo",
            y_keys=[("renta_mensual_media_eur", "EUR/mes")],
            y_unit="EUR/mes",
        ),
        _svg_chart(
            "Remuneración neta mensual de personas de 16-29 años",
            salary_rows,
            x_key="periodo",
            y_keys=[
                ("hombres", "Hombres"),
                ("mujeres", "Mujeres"),
            ],
            y_unit="EUR netos/mes",
        ),
        _svg_bar_chart(
            "Municipios con mayor demanda registrada de vivienda protegida",
            results.get("demanda_vpo_municipal", []),
            label_key="municipio",
            value_key="solicitudes_publicadas",
            y_unit="solicitudes (suma de filas)",
        ),
        _svg_chart(
            "Alquiler estimado de 60 m² como porcentaje del salario neto joven",
            effort_rows,
            x_key="periodo",
            y_keys=[("hombres", "Hombres"), ("mujeres", "Mujeres")],
            y_unit="% del salario neto mensual",
        ),
        _svg_chart(
            "Precio estimado de compra de 60 m² en años de salario neto",
            purchase_rows,
            x_key="periodo",
            y_keys=[("hombres", "Hombres"), ("mujeres", "Mujeres")],
            y_unit="años de salario",
        ),
    ]
    demand_note = (
        "Etxebide se filtra al grupo TOTAL y al literal No Absoluto para no sumar "
        "porcentajes ni desglose por ingresos, genero o colectivos. La suma "
        "municipal no garantiza personas unicas entre municipios."
    )
    methodology = (
        "Los agregados se calculan con MongoDB Aggregation Pipeline sobre una "
        "fuente y unidad identificadas. La serie Fotocasa es una media simple "
        "entre municipios con dato, no ponderada por población ni por anuncios. "
        "Las remuneraciones de 16-29 anos son una referencia de Euskadi y no "
        "salarios por municipio. El esfuerzo, los anos de salario y la entrada "
        "son estimaciones con alquiler/venta Fotocasa medio municipal simple "
        "para 60 m2 y remuneracion neta media por sexo; no incorporan ponderacion "
        "por poblacion, hipoteca, gastos de compra ni capacidad real de ahorro."
    )
    sections = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Reto 1: vivienda y emancipacion juvenil</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;"
        "margin:2rem auto;padding:0 1rem;color:#172033;background:#f8fafc}"
        "h1,h2{color:#0f3b67}figure{background:white;border:1px solid #dbe3ee;"
        "border-radius:8px;padding:1rem;margin:1.2rem 0}svg{width:100%;height:auto}"
        ".chart-title{font-size:15px;font-weight:600}svg text{font-size:11px;"
        "fill:#334155}li{margin:.5rem 0}</style></head><body>",
        "<h1>¿Dónde pueden vivir los jóvenes en Euskadi?</h1>",
        "<p>Informe generado desde consultas de agregación en MongoDB. "
        f"Fecha de ejecución: {datetime.now().astimezone().isoformat(timespec='minutes')}.</p>",
        "<h2>Indicadores</h2>",
        *charts,
        f"<p><strong>Acceso orientativo:</strong> {html.escape(affordability_note)}</p>",
        f"<p><strong>Nota de lectura:</strong> {html.escape(demand_note)}</p>",
        f"<h2>Metodologia y limites</h2><p>{html.escape(methodology)}</p>",
        "<p>Los gráficos describen los datos incorporados; no prueban por sí solos "
        "causalidad ni permiten inferir que todas las personas jóvenes tengan "
        "el mismo acceso a vivienda.</p>",
        "</body></html>",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(sections), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa datos del reto en MongoDB y genera agregaciones analíticas."
    )
    parser.add_argument("--mongo-uri", default=MONGO_URI, help="URI de conexión a MongoDB.")
    parser.add_argument("--database", default=DB_NAME, help="Nombre de la base de datos.")
    parser.add_argument("--ruta", default=str(BASE_DIR), help="Raíz del proyecto.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lee y transforma todos los archivos sin escribir en MongoDB.",
    )
    parser.add_argument(
        "--permitir-importacion-generica",
        action="store_true",
        help=(
            "Habilita explícitamente el escaneo de fuentes originales y copias. "
            "Para la carga canónica usa src.cargar_mongodb_fase3."
        ),
    )
    parser.add_argument(
        "--analizar",
        action="store_true",
        help="Ejecuta pipelines y genera un informe HTML tras la importación.",
    )
    parser.add_argument(
        "--solo-analisis",
        action="store_true",
        help="Ejecuta los pipelines sin volver a importar los archivos.",
    )
    parser.add_argument(
        "--salida-informe",
        default="resultados/analisis_reto1.html",
        help="Ruta del informe HTML, relativa a --ruta si no es absoluta.",
    )
    parser.add_argument(
        "--lote",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Número de operaciones MongoDB por lote.",
    )
    parser.add_argument("--verbose", action="store_true", help="Muestra detalles de depuración.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    project_root = Path(args.ruta).expanduser().resolve()
    if not project_root.is_dir():
        parser.error(f"La raíz indicada no es una carpeta: {project_root}")
    if args.lote <= 0:
        parser.error("--lote debe ser un entero mayor que cero.")
    if args.dry_run and (args.analizar or args.solo_analisis):
        parser.error("--dry-run no se puede combinar con opciones de análisis MongoDB.")
    if args.solo_analisis and args.analizar:
        parser.error("Usa --solo-analisis o --analizar, no ambos.")
    if not args.dry_run and not args.solo_analisis:
        if args.database == PHASE3_DATABASE_NAME:
            parser.error(
                f"La carga genérica no puede escribir en {PHASE3_DATABASE_NAME}; "
                "usa src.cargar_mongodb_fase3."
            )
        if not args.permitir_importacion_generica:
            parser.error(
                "La importación genérica está desactivada por seguridad. "
                "Usa src.cargar_mongodb_fase3 para cargar los datos canónicos, "
                "o añade --permitir-importacion-generica para el flujo heredado."
            )

    client: MongoClient | None = None
    try:
        if not args.dry_run:
            client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            LOGGER.info("Conectado a MongoDB; base de datos %s.", args.database)

        if not args.solo_analisis:
            files = discover_data_files(project_root)
            if not files:
                raise FileNotFoundError(
                    f"No se encontraron archivos compatibles bajo {project_root}."
                )
            LOGGER.info("Archivos compatibles descubiertos: %d.", len(files))
            for path in files:
                try:
                    result = import_collection(
                        client,
                        path,
                        database_name=args.database,
                        project_root=project_root,
                        dry_run=args.dry_run,
                        batch_size=args.lote,
                    )
                    LOGGER.info(
                        "%s -> %s | leídos=%d | transformados=%d | insertados=%d | "
                        "actualizados=%d | omitidos=%d | errores=%d | advertencias=%d",
                        result["archivo"],
                        result["collection"],
                        result["registros_leidos"],
                        result.get("registros_transformados", 0),
                        result["inserciones"],
                        result["actualizaciones"],
                        result["omitidos"],
                        result["errores"],
                        result["advertencias"],
                    )
                except Exception:
                    LOGGER.exception("Error al procesar %s; se continúa con el siguiente archivo.", path)

        if args.analizar or args.solo_analisis:
            if client is None:
                raise RuntimeError("No hay conexión MongoDB para ejecutar el análisis.")
            results = run_analysis(client[args.database])
            output_path = Path(args.salida_informe)
            if not output_path.is_absolute():
                output_path = project_root / output_path
            report_path = write_analysis_report(results, output_path)
            LOGGER.info("Informe analítico generado: %s", report_path)
    except errors.ServerSelectionTimeoutError as exc:
        LOGGER.error("MongoDB no disponible en %s: %s", args.mongo_uri, exc)
        raise SystemExit(1) from exc
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()

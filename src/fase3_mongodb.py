from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pymongo import UpdateOne
from pymongo.database import Database

try:
    from .config import BASE_DIR, PHASE3_DATABASE_NAME
    from .transformar import normalize_string, to_float
except ImportError:  # pragma: no cover
    from config import BASE_DIR, PHASE3_DATABASE_NAME
    from transformar import normalize_string, to_float


DATABASE_NAME = PHASE3_DATABASE_NAME
MUNICIPALITY_CATALOG = Path(
    "DatosIker", "originales", "fotocasa", "catalogo_municipios_fotocasa.csv"
)


@dataclass(frozen=True)
class SourceSpec:
    relative_path: Path
    kind: str
    collection: str
    source_name: str
    delimiter: str = ","

    @property
    def path(self) -> Path:
        return BASE_DIR / self.relative_path

    @property
    def relative_name(self) -> str:
        return self.relative_path.as_posix()


SOURCE_SPECS = (
    SourceSpec(
        MUNICIPALITY_CATALOG,
        "catalog",
        "municipios",
        "Fotocasa",
        delimiter=";",
    ),
    SourceSpec(
        Path(
            "DatosIker",
            "procesados",
            "fotocasa",
            "series_historicas_251_municipios.csv",
        ),
        "fotocasa",
        "precios_fotocasa",
        "Índice Inmobiliario Fotocasa",
        delimiter=";",
    ),
    SourceSpec(
        Path("DatosIker", "procesados", "pisoscom", "pisos_euskadi_geolocalizado.csv"),
        "pisoscom",
        "anuncios_pisoscom",
        "Pisos.com",
    ),
    SourceSpec(
        Path("DatosIker", "procesados", "emal_alquiler_anual_municipios.json"),
        "emal_anual",
        "alquiler_emal",
        "EMAL",
    ),
    SourceSpec(
        Path("DatosIker", "procesados", "emal_alquiler_vigente_municipios.json"),
        "emal_vigente",
        "alquiler_emal",
        "EMAL",
    ),
    *(
        SourceSpec(
            Path("DatosIker", "procesados", "eustat", filename),
            "eustat",
            "renta_personal_eustat",
            "Eustat",
        )
        for filename in (
            "renta_personal_municipal.json",
            "indicadores_renta_personal_municipal.json",
            "percentiles_renta_personal_municipal.json",
            "distribucion_renta_personal_municipal.json",
        )
    ),
    *(
        SourceSpec(
            Path("DatosIker", "procesados", "etxebide", filename),
            "etxebide",
            "demanda_vpo",
            "Etxebide",
        )
        for filename in (
            "Demandantes-Etxebide-Municipio-2026-04-01_con_codigo.csv",
            "Demandantes-Etxebide-Municipio-2026-07-01_con_codigo.csv",
        )
    ),
)

CANONICAL_COLLECTIONS = frozenset(spec.collection for spec in SOURCE_SPECS)
ALLOWED_COLLECTIONS = CANONICAL_COLLECTIONS | {
    "_metadata",
    "crud_demostracion",
    "anuncios_stream_fase5",
}


ETXEBIDE_METRICS = {
    "Empadronado_Compra": "empadronado_compra",
    "Empadronado_Alquiler": "empadronado_alquiler",
    "Empadronados": "empadronados",
    "NoEmpadronado_Compra": "no_empadronado_compra",
    "NoEmpadronado_Alquiler": "no_empadronado_alquiler",
    "NoEmpadronados": "no_empadronados",
    "Total": "total",
}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return normalize_string(value)


def _number(value: Any, field: str) -> int | float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field}: no se acepta un booleano como número.")
    parsed = to_float(value)
    if parsed is None or not math.isfinite(parsed):
        raise ValueError(f"{field}: valor numérico no interpretable: {value!r}")
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _municipality_code(value: Any, *, allow_missing: bool = False) -> str | None:
    code = _optional_text(value)
    if code is None and allow_missing:
        return None
    if code is None or not re.fullmatch(r"\d{5}", code):
        raise ValueError(f"Código municipal inválido: {value!r}")
    return code


def _required_municipality_code(value: Any) -> str:
    code = _municipality_code(value)
    if code is None:
        raise ValueError("Falta un código municipal obligatorio.")
    return code


def _preserve_status(value: Any) -> str | None:
    if value is None:
        return None
    status = str(value).strip()
    return status or None


def _identity(spec: SourceSpec, key: Any) -> str:
    payload = json.dumps(
        [spec.relative_name, key],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _document(
    spec: SourceSpec,
    key: Any,
    row_number: int,
    fields: dict[str, Any],
) -> dict[str, Any]:
    natural_key = _identity(spec, key)
    return {
        **fields,
        "_id": natural_key,
        "clave_natural": natural_key,
        "fuente": spec.source_name,
        "archivo_procesado": spec.relative_name,
        "fila_origen": row_number,
    }


def _iter_source_rows(spec: SourceSpec) -> Iterator[tuple[int, dict[str, Any]]]:
    if not spec.path.is_file():
        raise FileNotFoundError(f"No se encuentra la fuente canónica: {spec.path}")

    if spec.kind in {"catalog", "fotocasa", "pisoscom", "etxebide"}:
        with spec.path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, delimiter=spec.delimiter)
            if not reader.fieldnames:
                raise ValueError(f"CSV sin cabecera: {spec.relative_name}")
            for row_number, row in enumerate(reader, start=2):
                yield row_number, row
        return

    with spec.path.open(encoding="utf-8-sig") as source:
        data = json.load(source)
    if not isinstance(data, list):
        raise ValueError(f"Se esperaba una lista JSON: {spec.relative_name}")
    for row_number, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            raise ValueError(
                f"Registro JSON no válido en {spec.relative_name}, "
                f"posición {row_number}"
            )
        yield row_number, row


def _catalog_document(
    spec: SourceSpec, row: dict[str, Any], row_number: int
) -> dict[str, Any]:
    code = _required_municipality_code(row.get("municipio_codigo"))
    name = _optional_text(row.get("municipio_oficial"))
    territory = _optional_text(row.get("provincia"))
    if name is None or territory is None:
        raise ValueError(f"Nombre o territorio ausente en catálogo, fila {row_number}.")
    fields = {
        "_id": code,
        "municipio_codigo": code,
        "nombre": name,
        "territorio_historico": territory,
        "catalogo_fotocasa": {
            "id": _optional_text(row.get("fotocasa_id")),
            "slug": _optional_text(row.get("fotocasa_slug")),
            "nombre": _optional_text(row.get("nombre_fotocasa")),
            "url": _optional_text(row.get("url")),
            "estado": _optional_text(row.get("estado")),
            "series_alquiler": _number(row.get("registros_alquiler"), "registros_alquiler"),
            "series_venta": _number(row.get("registros_venta"), "registros_venta"),
        },
    }
    document = _document(spec, code, row_number, fields)
    document["_id"] = code
    document["clave_natural"] = code
    return document


def _fotocasa_document(
    spec: SourceSpec, row: dict[str, Any], row_number: int
) -> dict[str, Any]:
    code = _required_municipality_code(row.get("municipio_codigo"))
    property_type = _optional_text(row.get("tipo"))
    month = _optional_text(row.get("fecha"))
    if property_type not in {"alquiler", "venta"}:
        raise ValueError(f"Tipo Fotocasa no reconocido en fila {row_number}.")
    if month is None or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month):
        raise ValueError(f"Periodo Fotocasa no válido en fila {row_number}: {month!r}")
    price = _number(row.get("precio_eur_m2"), "precio_eur_m2")
    if price is None:
        raise ValueError(f"Precio Fotocasa ausente en fila {row_number}.")
    return _document(
        spec,
        (code, property_type, month),
        row_number,
        {
            "municipio_codigo": code,
            "municipio": _optional_text(row.get("municipio_oficial")),
            "fotocasa_id": _optional_text(row.get("fotocasa_id")),
            "tipo": property_type,
            "fecha": month,
            "precio_eur_m2": price,
            "unidad": "EUR/m²",
        },
    )


def _pisoscom_document(
    spec: SourceSpec, row: dict[str, Any], row_number: int
) -> dict[str, Any]:
    code = _municipality_code(row.get("municipio_codigo"), allow_missing=True)
    url = _optional_text(row.get("url"))
    if not url:
        raise ValueError(f"Anuncio sin URL en fila {row_number}.")
    fields = {
        "municipio_codigo": code,
        "municipio": _optional_text(row.get("municipio_oficial_fotocasa")),
        "operacion": _optional_text(row.get("operacion")),
        "provincia": _optional_text(row.get("provincia")),
        "titulo": _optional_text(row.get("titulo")),
        "localidad_zona": _optional_text(row.get("localidad_zona")),
        "precio_eur": _number(row.get("precio_eur"), "precio_eur"),
        "habitaciones": _number(row.get("habitaciones"), "habitaciones"),
        "banos": _number(row.get("banos"), "banos"),
        "metros_m2": _number(row.get("metros_m2"), "metros_m2"),
        "precio_m2": _number(row.get("precio_m2"), "precio_m2"),
        "url": url,
        "fecha_extraccion": _optional_text(row.get("fecha_extraccion")),
        "fila_original": _optional_text(row.get("fila_original")),
        "municipio_extraido": _optional_text(row.get("municipio_extraido")),
        "estado_correspondencia": _optional_text(
            row.get("estado_correspondencia")
        ),
    }
    return _document(spec, url, row_number, fields)


def _emal_document(
    spec: SourceSpec, row: dict[str, Any], row_number: int
) -> dict[str, Any]:
    code = _required_municipality_code(row.get("municipio_codigo"))
    fields = dict(row)
    fields["municipio_codigo"] = code
    fields["municipio"] = _optional_text(row.get("municipio"))
    for name in (
        "renta_mensual_media_eur",
        "renta_mensual_media_eur_m2",
        "numero_fianzas_depositadas",
        "numero_alquileres_vigentes",
    ):
        if name in row:
            fields[name] = _number(row[name], name)
    if spec.kind == "emal_anual":
        year = _number(row.get("anio"), "anio")
        if not isinstance(year, int):
            raise ValueError(f"Año EMAL no válido en fila {row_number}.")
        fields["anio"] = year
        key: Any = (code, year)
        fields["periodicidad"] = "anual"
    else:
        reference_date = _optional_text(row.get("fecha_referencia"))
        if reference_date is None:
            raise ValueError(f"Fecha EMAL ausente en fila {row_number}.")
        date.fromisoformat(reference_date)
        fields["fecha_referencia"] = reference_date
        fields["periodicidad"] = "vigente"
        key = (code, reference_date)
    return _document(spec, key, row_number, fields)


def _eustat_document(
    spec: SourceSpec, row: dict[str, Any], row_number: int
) -> dict[str, Any]:
    code = _required_municipality_code(row.get("municipio_codigo"))
    if row.get("nivel_geografico") != "municipio":
        raise ValueError(f"Nivel geográfico inesperado en {spec.relative_name}.")
    observation = row.get("indice_observacion")
    if not isinstance(observation, int):
        raise ValueError(f"Índice Eustat no válido en fila {row_number}.")
    fields = dict(row)
    fields["municipio_codigo"] = code
    fields["municipio"] = _optional_text(row.get("municipio"))
    fields["tabla_eustat"] = spec.path.stem
    value = row.get("valor")
    if value is not None and not isinstance(value, (int, float)):
        raise ValueError(f"Valor Eustat no numérico en fila {row_number}.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Valor Eustat no finito en fila {row_number}.")
    return _document(
        spec,
        (spec.path.name, observation),
        row_number,
        fields,
    )


def _etxebide_document(
    spec: SourceSpec, row: dict[str, Any], row_number: int
) -> dict[str, Any]:
    code = _required_municipality_code(row.get("municipio_codigo"))
    snapshot = _optional_text(row.get("fecha_fotografia"))
    if snapshot is None:
        raise ValueError(f"Fecha de fotografía ausente en fila {row_number}.")
    date.fromisoformat(snapshot)
    group = _optional_text(row.get("Grupo"))
    category = _optional_text(row.get("Literal"))
    if group is None or category is None:
        raise ValueError(f"Categoría Etxebide ausente en fila {row_number}.")

    values = {
        target: _number(row.get(source), source)
        for source, target in ETXEBIDE_METRICS.items()
    }
    statuses = {
        target: _preserve_status(row.get(f"{source}_estado"))
        for source, target in ETXEBIDE_METRICS.items()
    }
    fields = {
        "municipio_codigo": code,
        "municipio": _optional_text(row.get("Municipio")),
        "municipio_bilingue": _optional_text(row.get("Municipio_bilingue")),
        "fecha_fotografia": snapshot,
        "grupo": group,
        "categoria": category,
        "valores": values,
        "estados": statuses,
    }
    return _document(
        spec,
        (code, snapshot, group, category),
        row_number,
        fields,
    )


def prepare_document(
    spec: SourceSpec, row: dict[str, Any], row_number: int
) -> dict[str, Any]:
    builders = {
        "catalog": _catalog_document,
        "fotocasa": _fotocasa_document,
        "pisoscom": _pisoscom_document,
        "emal_anual": _emal_document,
        "emal_vigente": _emal_document,
        "eustat": _eustat_document,
        "etxebide": _etxebide_document,
    }
    try:
        builder = builders[spec.kind]
    except KeyError as exc:
        raise ValueError(f"Tipo de fuente no configurado: {spec.kind}") from exc
    return builder(spec, row, row_number)


def preflight_sources() -> tuple[list[dict[str, Any]], set[str]]:
    summaries: list[dict[str, Any]] = []
    municipality_codes: set[str] = set()

    for spec in SOURCE_SPECS:
        seen_keys: set[str] = set()
        codes_in_source: set[str] = set()
        missing_code_count = 0
        count = 0
        for row_number, row in _iter_source_rows(spec):
            document = prepare_document(spec, row, row_number)
            natural_key = document["clave_natural"]
            if natural_key in seen_keys:
                raise ValueError(
                    f"Clave natural duplicada en {spec.relative_name}, "
                    f"fila {row_number}."
                )
            seen_keys.add(natural_key)
            code = document.get("municipio_codigo")
            if code is None:
                missing_code_count += 1
            else:
                codes_in_source.add(code)
            count += 1

        if count == 0:
            raise ValueError(f"La fuente canónica está vacía: {spec.relative_name}")
        if spec.kind == "catalog":
            municipality_codes = codes_in_source
            if len(municipality_codes) != count:
                raise ValueError("El catálogo no tiene un código único por municipio.")
        elif any(code not in municipality_codes for code in codes_in_source):
            unknown_codes = sorted(codes_in_source - municipality_codes)
            raise ValueError(
                f"Códigos no incluidos en el catálogo en {spec.relative_name}: "
                f"{unknown_codes[:10]}"
            )

        summaries.append(
            {
                "archivo": spec.relative_name,
                "coleccion": spec.collection,
                "registros": count,
                "municipios": len(codes_in_source),
                "sin_codigo_municipal": missing_code_count,
            }
        )

    if not municipality_codes:
        raise ValueError("El catálogo municipal canónico está vacío.")
    return summaries, municipality_codes


def _create_indexes(database: Database) -> None:
    database["municipios"].create_index(
        [("territorio_historico", 1)], name="territorio_historico"
    )
    database["precios_fotocasa"].create_index(
        [("municipio_codigo", 1), ("tipo", 1), ("fecha", 1)],
        name="municipio_tipo_fecha",
    )
    database["anuncios_pisoscom"].create_index(
        [("municipio_codigo", 1), ("operacion", 1)],
        name="municipio_operacion",
    )
    database["anuncios_pisoscom"].create_index(
        [("url", 1)], name="url_unica", unique=True
    )
    database["alquiler_emal"].create_index(
        [("municipio_codigo", 1), ("periodicidad", 1), ("anio", 1)],
        name="municipio_periodo_emal",
    )
    database["renta_personal_eustat"].create_index(
        [("municipio_codigo", 1), ("tabla_eustat", 1), ("periodo", 1)],
        name="municipio_tabla_periodo",
    )
    database["demanda_vpo"].create_index(
        [("municipio_codigo", 1), ("fecha_fotografia", 1), ("grupo", 1)],
        name="municipio_fecha_grupo",
    )
    for collection_name in {
        spec.collection for spec in SOURCE_SPECS if spec.collection != "municipios"
    }:
        database[collection_name].create_index(
            [("clave_natural", 1)], name="clave_natural_unica", unique=True
        )


def ensure_database_marker(database: Database) -> None:
    marker_collection = database["_metadata"]
    existing_collections = set(database.list_collection_names())
    unexpected = existing_collections - ALLOWED_COLLECTIONS
    if unexpected:
        raise RuntimeError(
            "La base aislada contiene colecciones no reconocidas; no se modificará: "
            + ", ".join(sorted(unexpected))
        )

    marker = marker_collection.find_one({"_id": "fase3_schema"})
    if marker is not None:
        if marker.get("version") != 1:
            raise RuntimeError("La versión del esquema MongoDB no es compatible.")
        return

    if existing_collections:
        raise RuntimeError(
            "La base aislada tiene colecciones pero carece del marcador de esquema; "
            "se cancela por seguridad."
        )
    marker_collection.insert_one(
        {
            "_id": "fase3_schema",
            "version": 1,
            "creado_en": datetime.now(timezone.utc),
            "colecciones": sorted(CANONICAL_COLLECTIONS),
        }
    )


def load_sources(
    database: Database,
    *,
    batch_size: int = 1000,
) -> dict[str, dict[str, int]]:
    if batch_size <= 0:
        raise ValueError("El tamaño del lote debe ser mayor que cero.")

    _create_indexes(database)
    now = datetime.now(timezone.utc)
    results: dict[str, dict[str, int]] = {}

    for spec in SOURCE_SPECS:
        collection = database[spec.collection]
        operations: list[UpdateOne] = []
        inserted = modified = matched = processed = 0

        for row_number, row in _iter_source_rows(spec):
            document = prepare_document(spec, row, row_number)
            source_id = document["_id"]
            update_fields = {
                key: value for key, value in document.items() if key != "_id"
            }
            operations.append(
                UpdateOne(
                    {"_id": source_id},
                    {
                        "$set": update_fields,
                        "$setOnInsert": {
                            "_id": source_id,
                            "fecha_ingesta": now,
                        },
                    },
                    upsert=True,
                )
            )
            processed += 1

            if len(operations) >= batch_size:
                result = collection.bulk_write(operations, ordered=False)
                inserted += result.upserted_count
                modified += result.modified_count
                matched += result.matched_count
                operations.clear()

        if operations:
            result = collection.bulk_write(operations, ordered=False)
            inserted += result.upserted_count
            modified += result.modified_count
            matched += result.matched_count

        results[spec.relative_name] = {
            "procesados": processed,
            "insertados": inserted,
            "actualizados": modified,
            "sin_cambios": max(matched - modified, 0),
        }

    return results


def verify_loaded_data(
    database: Database,
    summaries: list[dict[str, Any]],
    municipality_codes: set[str],
) -> None:
    expected: dict[str, int] = {}
    for summary in summaries:
        collection_name = summary["coleccion"]
        expected[collection_name] = (
            expected.get(collection_name, 0) + summary["registros"]
        )

    for collection_name, expected_count in expected.items():
        actual_count = database[collection_name].count_documents({})
        if actual_count != expected_count:
            raise RuntimeError(
                f"{collection_name}: se esperaban {expected_count} documentos, "
                f"se encontraron {actual_count}."
            )
        referenced_codes = {
            code
            for code in database[collection_name].distinct("municipio_codigo")
            if code is not None
        }
        unknown_codes = referenced_codes - municipality_codes
        if unknown_codes:
            raise RuntimeError(
                f"{collection_name} contiene referencias municipales sin maestro: "
                f"{sorted(unknown_codes)[:10]}"
            )

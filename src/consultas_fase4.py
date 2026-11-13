from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

try:
    from .config import MONGO_URI
    from .fase3_mongodb import DATABASE_NAME
except ImportError:  # pragma: no cover
    from config import MONGO_URI
    from fase3_mongodb import DATABASE_NAME


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "resultados" / "fase4" / "consultas_y_agregaciones.json"
CAPITAL_CODES = ("01059", "48020", "20069")
LATEST_FOTOCASA_MONTH = "2026-10"
LATEST_EMAL_DATE = "2026-03-31"
LATEST_ETXEBIDE_DATE = "2026-07-01"
UNDER_36_CATEGORY = "3. 36 urtetik beherakoak / Menores 36 años"


def query_specs() -> dict[str, dict[str, Any]]:
    return {
        "Q1_evolucion_alquiler_capitales": {
            "collection": "precios_fotocasa",
            "filter": {
                "municipio_codigo": {"$in": list(CAPITAL_CODES)},
                "tipo": "alquiler",
                "fecha": {"$gte": "2025-11", "$lte": LATEST_FOTOCASA_MONTH},
            },
            "projection": {
                "_id": 0,
                "municipio_codigo": 1,
                "municipio": 1,
                "tipo": 1,
                "fecha": 1,
                "precio_eur_m2": 1,
                "unidad": 1,
            },
            "sort": [("municipio_codigo", 1), ("fecha", 1)],
            "limit": 36,
        },
        "Q2_anuncios_venta_con_limites": {
            "collection": "anuncios_pisoscom",
            "filter": {
                "$and": [
                    {"municipio_codigo": {"$in": list(CAPITAL_CODES)}},
                    {"operacion": "venta"},
                    {"precio_eur": {"$gt": 0, "$lte": 300000}},
                    {"metros_m2": {"$gte": 60}},
                ]
            },
            "projection": {
                "_id": 0,
                "municipio_codigo": 1,
                "municipio": 1,
                "provincia": 1,
                "operacion": 1,
                "precio_eur": 1,
                "metros_m2": 1,
                "precio_m2": 1,
                "estado_correspondencia": 1,
            },
            "sort": [("precio_m2", 1)],
            "limit": 10,
        },
        "Q3_alquiler_emal_vigente": {
            "collection": "alquiler_emal",
            "filter": {
                "municipio_codigo": {"$in": list(CAPITAL_CODES)},
                "periodicidad": "vigente",
                "fecha_referencia": LATEST_EMAL_DATE,
                "renta_mensual_media_eur_m2": {"$type": "number", "$gt": 0},
            },
            "projection": {
                "_id": 0,
                "municipio_codigo": 1,
                "municipio": 1,
                "fecha_referencia": 1,
                "numero_alquileres_vigentes": 1,
                "renta_mensual_media_eur": 1,
                "renta_mensual_media_eur_m2": 1,
                "fuente": 1,
            },
            "sort": [("municipio_codigo", 1)],
            "limit": 10,
        },
        "Q4_renta_personal_disponible_eustat": {
            "collection": "renta_personal_eustat",
            "filter": {
                "municipio_codigo": {"$in": list(CAPITAL_CODES)},
                "tabla_eustat": "renta_personal_municipal",
                "tipo_de_renta": "Renta disponible",
                "sexo": "Total",
                "periodo": "2024",
                "valor": {"$type": "number", "$gt": 0},
            },
            "projection": {
                "_id": 0,
                "municipio_codigo": 1,
                "municipio": 1,
                "periodo": 1,
                "tipo_de_renta": 1,
                "sexo": 1,
                "valor": 1,
                "descripcion_tabla": 1,
            },
            "sort": [("valor", -1)],
            "limit": 10,
        },
        "Q5_demanda_vpo_menores_36": {
            "collection": "demanda_vpo",
            "filter": {
                "fecha_fotografia": LATEST_ETXEBIDE_DATE,
                "grupo": "CUPO",
                "categoria": UNDER_36_CATEGORY,
                "valores.total": {"$type": "number", "$gte": 0},
                "estados.total": "disponible",
            },
            "projection": {
                "_id": 0,
                "municipio_codigo": 1,
                "municipio": 1,
                "fecha_fotografia": 1,
                "grupo": 1,
                "categoria": 1,
                "valores.total": 1,
                "estados.total": 1,
            },
            "sort": [("valores.total", -1), ("municipio_codigo", 1)],
            "limit": 10,
        },
    }


def pipeline_specs() -> dict[str, tuple[str, list[dict[str, Any]]]]:
    fotocasa_ranking = [
        {
            "$match": {
                "tipo": "alquiler",
                "fecha": LATEST_FOTOCASA_MONTH,
                "precio_eur_m2": {"$type": "number", "$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "precio_oferta_eur_m2": {"$avg": "$precio_eur_m2"},
                "observaciones": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "municipios",
                "localField": "_id",
                "foreignField": "_id",
                "as": "municipio",
            }
        },
        {"$unwind": "$municipio"},
        {
            "$project": {
                "_id": 0,
                "municipio_codigo": "$_id",
                "municipio": "$municipio.nombre",
                "territorio_historico": "$municipio.territorio_historico",
                "periodo": {"$literal": LATEST_FOTOCASA_MONTH},
                "precio_oferta_eur_m2": 1,
                "observaciones": 1,
            }
        },
        {"$sort": {"precio_oferta_eur_m2": 1}},
        {"$limit": 20},
    ]

    capital_history = [
        {
            "$match": {
                "municipio_codigo": {"$in": list(CAPITAL_CODES)},
                "tipo": "alquiler",
                "fecha": {"$gte": "2020-01", "$lte": LATEST_FOTOCASA_MONTH},
            }
        },
        {
            "$group": {
                "_id": {
                    "municipio_codigo": "$municipio_codigo",
                    "periodo": "$fecha",
                },
                "precio_oferta_eur_m2": {"$avg": "$precio_eur_m2"},
                "observaciones": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "municipios",
                "localField": "_id.municipio_codigo",
                "foreignField": "_id",
                "as": "municipio",
            }
        },
        {"$unwind": "$municipio"},
        {
            "$project": {
                "_id": 0,
                "municipio_codigo": "$_id.municipio_codigo",
                "municipio": "$municipio.nombre",
                "periodo": "$_id.periodo",
                "precio_oferta_eur_m2": 1,
                "observaciones": 1,
            }
        },
        {"$sort": {"municipio_codigo": 1, "periodo": 1}},
    ]

    emal_fotocasa_comparison = [
        {
            "$match": {
                "periodicidad": "vigente",
                "fecha_referencia": LATEST_EMAL_DATE,
                "renta_mensual_media_eur_m2": {
                    "$type": "number",
                    "$gt": 0,
                },
            }
        },
        {
            "$lookup": {
                "from": "precios_fotocasa",
                "let": {"codigo": "$municipio_codigo"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$municipio_codigo", "$$codigo"]},
                                    {"$eq": ["$tipo", "alquiler"]},
                                    {"$eq": ["$fecha", LATEST_FOTOCASA_MONTH]},
                                    {"$gt": ["$precio_eur_m2", 0]},
                                ]
                            }
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "fecha": 1,
                            "precio_eur_m2": 1,
                        }
                    },
                ],
                "as": "fotocasa",
            }
        },
        {"$unwind": "$fotocasa"},
        {
            "$lookup": {
                "from": "municipios",
                "localField": "municipio_codigo",
                "foreignField": "_id",
                "as": "municipio",
            }
        },
        {"$unwind": "$municipio"},
        {
            "$project": {
                "_id": 0,
                "municipio_codigo": 1,
                "municipio": "$municipio.nombre",
                "fecha_emal": "$fecha_referencia",
                "fecha_fotocasa": "$fotocasa.fecha",
                "alquiler_registrado_eur_m2": "$renta_mensual_media_eur_m2",
                "precio_oferta_fotocasa_eur_m2": "$fotocasa.precio_eur_m2",
                "diferencia_descriptiva_eur_m2": {
                    "$subtract": [
                        "$fotocasa.precio_eur_m2",
                        "$renta_mensual_media_eur_m2",
                    ]
                },
            }
        },
        {"$sort": {"diferencia_descriptiva_eur_m2": -1}},
    ]

    return {
        "P1_alquiler_municipios_octubre_2026": (
            "precios_fotocasa",
            fotocasa_ranking,
        ),
        "P2_evolucion_alquiler_tres_capitales": (
            "precios_fotocasa",
            capital_history,
        ),
        "P3_oferta_fotocasa_vs_alquiler_emal": (
            "alquiler_emal",
            emal_fotocasa_comparison,
        ),
    }


def _stage_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        stage = value.get("stage")
        if isinstance(stage, str):
            names.add(stage)
        for nested in value.values():
            names.update(_stage_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(_stage_names(nested))
    return names


def explain_index_comparison(database: Database) -> dict[str, Any]:
    query = {
        "municipio_codigo": "48020",
        "tipo": "alquiler",
        "fecha": {"$gte": "2026-01", "$lte": LATEST_FOTOCASA_MONTH},
    }
    results: dict[str, Any] = {}
    for label, hint in (
        ("barrido_forzado", {"$natural": 1}),
        ("indice_municipio_tipo_fecha", "municipio_tipo_fecha"),
    ):
        explain = database.command(
            "explain",
            {
                "find": "precios_fotocasa",
                "filter": query,
                "hint": hint,
            },
            verbosity="executionStats",
        )
        stats = explain["executionStats"]
        plan = explain["queryPlanner"]["winningPlan"]
        results[label] = {
            "etapas_plan": sorted(_stage_names(plan)),
            "registros_devueltos": stats["nReturned"],
            "documentos_examinados": stats["totalDocsExamined"],
            "claves_examinadas": stats["totalKeysExamined"],
        }

    scan = results["barrido_forzado"]
    indexed = results["indice_municipio_tipo_fecha"]
    if "COLLSCAN" not in scan["etapas_plan"]:
        raise RuntimeError("El plan de control no produjo COLLSCAN.")
    if "IXSCAN" not in indexed["etapas_plan"]:
        raise RuntimeError("El índice no aparece como IXSCAN en explain().")
    if scan["registros_devueltos"] != indexed["registros_devueltos"]:
        raise RuntimeError("Los planes con y sin índice devolvieron resultados distintos.")
    if indexed["documentos_examinados"] >= scan["documentos_examinados"]:
        raise RuntimeError("El índice no redujo los documentos examinados.")
    return results


def _write_results(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=".fase4_",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            json.dump(
                payload,
                output,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
                default=str,
            )
            output.write("\n")
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def run(database: Database) -> dict[str, Any]:
    marker = database["_metadata"].find_one({"_id": "fase3_schema"})
    if marker is None or marker.get("version") != 1:
        raise RuntimeError(
            f"La base {DATABASE_NAME} no tiene el esquema de Fase 3 inicializado."
        )

    municipalities = {
        row["_id"]: row["nombre"]
        for row in database["municipios"].find(
            {"_id": {"$in": list(CAPITAL_CODES)}},
            {"_id": 1, "nombre": 1},
        )
    }
    if set(municipalities) != set(CAPITAL_CODES):
        raise RuntimeError("No se encontraron los tres municipios de comparación.")

    query_results: dict[str, list[dict[str, Any]]] = {}
    for name, spec in query_specs().items():
        cursor = (
            database[spec["collection"]]
            .find(spec["filter"], spec["projection"])
            .sort(spec["sort"])
            .limit(spec["limit"])
        )
        query_results[name] = list(cursor)
        if not query_results[name]:
            raise RuntimeError(f"La consulta {name} no devolvió resultados.")

    pipeline_results: dict[str, list[dict[str, Any]]] = {}
    for name, (collection_name, pipeline) in pipeline_specs().items():
        pipeline_results[name] = list(
            database[collection_name].aggregate(pipeline, allowDiskUse=True)
        )
        if not pipeline_results[name]:
            raise RuntimeError(f"El pipeline {name} no devolvió resultados.")

    return {
        "base_datos": DATABASE_NAME,
        "municipios_comparados": municipalities,
        "consultas": query_results,
        "agregaciones": pipeline_results,
        "explain_indice": explain_index_comparison(database),
        "notas": [
            "La renta disponible Eustat es renta personal, no salario juvenil.",
            (
                "El pipeline P3 mantiene separados el alquiler registrado EMAL "
                "y el precio de oferta Fotocasa; sus fechas de referencia no "
                "coinciden y la diferencia es descriptiva."
            ),
            (
                "El pipeline de Etxebide usa solo valores publicados; las "
                "supresiones impiden interpretar su suma como un total completo."
            ),
        ],
    }


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        payload = run(client[DATABASE_NAME])
        _write_results(payload, OUTPUT_PATH)
        for name, rows in payload["consultas"].items():
            print(f"{name}: {len(rows)} resultados")
        for name, rows in payload["agregaciones"].items():
            print(f"{name}: {len(rows)} resultados")
        print("Comparación explain():")
        for name, result in payload["explain_indice"].items():
            print(
                f"{name}: etapas={result['etapas_plan']}, "
                f"docs={result['documentos_examinados']}, "
                f"claves={result['claves_examinadas']}, "
                f"devueltos={result['registros_devueltos']}"
            )
        print(f"Resultados guardados en {OUTPUT_PATH}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from pymongo import MongoClient
from pymongo.database import Database

try:
    from .config import DB_NAME, MONGO_URI, PHASE3_DATABASE_NAME
    from .importar_datos import _svg_bar_chart, _svg_chart
except ImportError:  # pragma: no cover
    from config import DB_NAME, MONGO_URI, PHASE3_DATABASE_NAME
    from importar_datos import _svg_bar_chart, _svg_chart


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "resultados" / "fase6"
CAPITALS = {
    "01059": "Vitoria-Gasteiz",
    "48020": "Bilbao",
    "20069": "Donostia / San Sebastián",
}
VPO_UNDER_36_CATEGORY = "3. 36 urtetik beherakoak / Menores 36 años"
MUNICIPAL_CODE = re.compile(r"\d{5}\Z")
MUNICIPAL_WORK_INCOME_PERIOD = "2024"
EMAL_ANNUAL_INCOME_YEAR = 2024

INDICATOR_DEFINITIONS = [
    {
        "id": "fotocasa_alquiler_eur_m2",
        "nombre": "Precio de oferta de alquiler Fotocasa",
        "fuente": "Índice Inmobiliario Fotocasa",
        "unidad": "EUR/m²/mes",
        "periodo": "Último mes disponible",
    },
    {
        "id": "fotocasa_venta_eur_m2",
        "nombre": "Precio de oferta de compraventa Fotocasa",
        "fuente": "Índice Inmobiliario Fotocasa",
        "unidad": "EUR/m²",
        "periodo": "Último mes disponible",
    },
    {
        "id": "emal_alquiler_registrado_eur_m2",
        "nombre": "Alquiler registrado vigente EMAL",
        "fuente": "EMAL",
        "unidad": "EUR/m²/mes",
        "periodo": "Última fecha de referencia disponible",
    },
    {
        "id": "pisoscom_alquiler_mediana_eur_m2",
        "nombre": "Mediana de anuncios de alquiler Pisos.com",
        "fuente": "Pisos.com",
        "unidad": "EUR/m²/mes",
        "periodo": "Fecha de extracción disponible",
    },
    {
        "id": "eustat_renta_personal_disponible_eur",
        "nombre": "Renta personal media disponible Eustat",
        "fuente": "Eustat",
        "unidad": "EUR",
        "periodo": "Último periodo disponible",
    },
    {
        "id": "eustat_renta_trabajo_municipal_eur",
        "nombre": "Renta personal media municipal procedente del trabajo",
        "fuente": "Eustat",
        "unidad": "EUR/persona/año",
        "periodo": "2024; sin desglose por edad",
    },
    {
        "id": "emal_sobre_renta_trabajo_municipal_pct",
        "nombre": "Alquiler EMAL anualizado sobre renta personal del trabajo",
        "fuente": "EMAL y Eustat",
        "unidad": "% de renta personal anual",
        "periodo": "2024; municipios con datos en ambas fuentes",
    },
    {
        "id": "fotocasa_alquiler_variacion_pct",
        "nombre": "Variación nominal del alquiler de oferta Fotocasa",
        "fuente": "Índice Inmobiliario Fotocasa",
        "unidad": "%",
        "periodo": "Desde el primer mes de la serie hasta el último",
    },
    {
        "id": "fotocasa_emal_diferencia_eur_m2",
        "nombre": "Diferencia descriptiva Fotocasa menos EMAL",
        "fuente": "Fotocasa y EMAL",
        "unidad": "EUR/m²/mes",
        "periodo": "Periodos de referencia propios de cada fuente",
    },
    {
        "id": "esfuerzo_alquiler_salario_regional_pct",
        "nombre": "Alquiler de 60 m² sobre remuneración neta regional 16-29",
        "fuente": "Fotocasa y Encuesta de Condiciones de Trabajo",
        "unidad": "% de la remuneración neta mensual regional",
        "periodo": "2024",
    },
]


def _required_code(value: Any) -> str:
    if not isinstance(value, str) or not MUNICIPAL_CODE.fullmatch(value):
        raise ValueError(f"Código municipal inválido: {value!r}")
    return value


def _latest_period(
    database: Database,
    collection_name: str,
    query: dict[str, Any],
    period_field: str,
) -> str:
    document = database[collection_name].find_one(
        {**query, period_field: {"$type": "string"}},
        {period_field: 1},
        sort=[(period_field, -1)],
    )
    if document is None:
        raise RuntimeError(
            f"No hay periodo disponible en {collection_name}.{period_field}."
        )
    return document[period_field]


def _fotocasa_values(
    database: Database, operation: str, month: str
) -> dict[str, dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "tipo": operation,
                "fecha": month,
                "precio_eur_m2": {"$type": "number", "$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "observaciones": {"$sum": 1},
                "valor": {"$avg": "$precio_eur_m2"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    values = {}
    for row in database["precios_fotocasa"].aggregate(pipeline):
        code = _required_code(row["_id"])
        values[code] = {
            "valor": row["valor"],
            "observaciones": row["observaciones"],
        }
    return values


def _emal_values(
    database: Database, reference_date: str
) -> dict[str, dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "periodicidad": "vigente",
                "fecha_referencia": reference_date,
                "renta_mensual_media_eur_m2": {
                    "$type": "number",
                    "$gt": 0,
                },
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "municipio": {"$first": "$municipio"},
                "valor": {"$avg": "$renta_mensual_media_eur_m2"},
                "alquileres_registrados": {
                    "$max": "$numero_alquileres_vigentes"
                },
                "observaciones": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    values = {}
    for row in database["alquiler_emal"].aggregate(pipeline):
        code = _required_code(row["_id"])
        values[code] = {
            "valor": row["valor"],
            "alquileres_registrados": row.get("alquileres_registrados"),
            "observaciones": row["observaciones"],
        }
    return values


def _municipal_work_income_values(
    database: Database, period: str
) -> dict[str, dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "tabla_eustat": "renta_personal_municipal",
                "nivel_geografico": "municipio",
                "tipo_de_renta": "Renta del trabajo",
                "sexo": "Total",
                "periodo": period,
                "valor": {"$type": "number", "$gt": 0},
                "municipio_codigo": {"$type": "string"},
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "municipio": {"$first": "$municipio"},
                "valor": {"$avg": "$valor"},
                "observaciones": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    values = {}
    for row in database["renta_personal_eustat"].aggregate(pipeline):
        code = _required_code(row["_id"])
        if row["observaciones"] != 1:
            raise RuntimeError(
                f"Eustat tiene {row['observaciones']} observaciones de renta "
                f"del trabajo para el municipio {code} en {period}."
            )
        values[code] = {
            "valor": row["valor"],
            "observaciones": row["observaciones"],
        }
    if not values:
        raise RuntimeError(
            f"No hay renta personal municipal del trabajo para {period}."
        )
    return values


def _emal_annual_rent_values(
    database: Database, year: int
) -> dict[str, dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "periodicidad": "anual",
                "anio": year,
                "renta_mensual_media_eur": {
                    "$type": "number",
                    "$gt": 0,
                },
                "municipio_codigo": {"$type": "string"},
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "municipio": {"$first": "$municipio"},
                "renta_mensual_media_eur": {
                    "$avg": "$renta_mensual_media_eur"
                },
                "numero_fianzas_depositadas": {
                    "$max": "$numero_fianzas_depositadas"
                },
                "observaciones": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    values = {}
    for row in database["alquiler_emal"].aggregate(pipeline):
        code = _required_code(row["_id"])
        if row["observaciones"] != 1:
            raise RuntimeError(
                f"EMAL tiene {row['observaciones']} alquileres anuales para "
                f"el municipio {code} en {year}."
            )
        values[code] = {
            "renta_mensual_media_eur": row["renta_mensual_media_eur"],
            "numero_fianzas_depositadas": row.get(
                "numero_fianzas_depositadas"
            ),
            "observaciones": row["observaciones"],
        }
    if not values:
        raise RuntimeError(f"No hay alquiler anual EMAL disponible para {year}.")
    return values


def _pisoscom_rental_values(
    database: Database, extraction_date: str
) -> dict[str, dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "operacion": "alquiler",
                "fecha_extraccion": extraction_date,
                "municipio_codigo": {"$type": "string"},
                "precio_m2": {"$type": "number", "$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "precios_m2": {"$push": "$precio_m2"},
                "anuncios": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    values = {}
    for row in database["anuncios_pisoscom"].aggregate(pipeline):
        code = _required_code(row["_id"])
        prices = row["precios_m2"]
        if not prices:
            continue
        values[code] = {
            "valor": median(prices),
            "anuncios": row["anuncios"],
        }
    return values


def _eustat_values(
    database: Database, period: str
) -> dict[str, dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "tabla_eustat": "renta_personal_municipal",
                "tipo_de_renta": "Renta disponible",
                "sexo": "Total",
                "periodo": period,
                "valor": {"$type": "number", "$gt": 0},
                "municipio_codigo": {"$type": "string"},
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "municipio": {"$first": "$municipio"},
                "valor": {"$avg": "$valor"},
                "observaciones": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    values = {}
    for row in database["renta_personal_eustat"].aggregate(pipeline):
        code = _required_code(row["_id"])
        values[code] = {
            "valor": row["valor"],
            "observaciones": row["observaciones"],
        }
    return values


def _regional_salary_reference(database: Database) -> dict[str, Any]:
    salary_rows = list(
        database["salarios"].aggregate(
            [
                {
                    "$match": {
                        "_import_metadata.source_file": (
                            "DatosAlvaro/Salario/remuMedia.csv"
                        ),
                        "indicador": "remuneracion_neta_mensual_eur",
                        "edad": "16-29",
                        "periodo": "2024",
                        "sexo": {"$in": ["Hombre", "Mujer"]},
                        "valor": {"$type": "number", "$gt": 0},
                    }
                },
                {
                    "$group": {
                        "_id": "$sexo",
                        "valor": {"$avg": "$valor"},
                        "observaciones": {"$sum": 1},
                    }
                },
            ]
        )
    )
    salaries = {
        row["_id"]: row["valor"]
        for row in salary_rows
        if row.get("_id") in {"Hombre", "Mujer"}
        and isinstance(row.get("valor"), (int, float))
        and row["valor"] > 0
    }
    if set(salaries) != {"Hombre", "Mujer"}:
        raise RuntimeError(
            "Faltan las dos referencias salariales regionales 16-29 de 2024 "
            "en la colección salarios."
        )
    if any(row.get("observaciones") != 1 for row in salary_rows):
        raise RuntimeError(
            "La fuente remuMedia.csv no tiene exactamente una observación "
            "por sexo para 2024 y 16-29."
        )

    iovj = database["indicadores_laborales"].find(
        {
            "_import_metadata.source_file": (
                "DatosAlvaro/Salario/iovj-empleo-economico.csv"
            ),
            "indicador": (
                "Salario mensual neto medio, según sexo, grupos de edad y TTHH"
            ),
            "periodo": "2024",
            "categoria_1_valor": "18-29 años",
            "categoria_2_valor": "Salario neto medio mensual",
            "valor": {"$type": "number", "$gt": 0},
        },
        {"_id": 0, "valor": 1},
    ).limit(2)
    iovj_rows = list(iovj)
    if len(iovj_rows) != 1:
        raise RuntimeError(
            "Se esperaba una única referencia IOVJ de salario neto mensual "
            "para 18-29 años en 2024."
        )

    return {
        "periodo": "2024",
        "geografia": "C.A. de Euskadi",
        "fuente": "Encuesta de Condiciones de Trabajo (remuMedia.csv)",
        "edad": "16-29",
        "poblacion": "Personas asalariadas y asimiladas",
        "unidad": "EUR netos/mes",
        "remuneracion_neta_media_por_sexo": salaries,
        "referencia_iovj": {
            "periodo": "2024",
            "edad": "18-29",
            "valor": iovj_rows[0]["valor"],
            "unidad": "Salario neto medio mensual, según el indicador IOVJ",
            "geografia": "Euskadi; referencia agregada, no municipal",
        },
    }


def _fotocasa_annual_rents(
    database: Database, year: str
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    pipeline = [
        {
            "$match": {
                "tipo": "alquiler",
                "fecha": {"$gte": "2020-01", "$lte": "2026-10"},
                "precio_eur_m2": {"$type": "number", "$gt": 0},
                "municipio_codigo": {"$type": "string"},
            }
        },
        {"$sort": {"municipio_codigo": 1, "fecha": 1}},
        {
            "$group": {
                "_id": "$municipio_codigo",
                "puntos": {
                    "$push": {
                        "fecha": "$fecha",
                        "precio_eur_m2": "$precio_eur_m2",
                    }
                },
            }
        },
        {"$sort": {"_id": 1}},
    ]
    series: dict[str, list[dict[str, Any]]] = {}
    for row in database["precios_fotocasa"].aggregate(pipeline):
        code = _required_code(row["_id"])
        series[code] = row["puntos"]
    signatures: Counter[tuple[tuple[str, float], ...]] = Counter(
        tuple(
            (point["fecha"], float(point["precio_eur_m2"]))
            for point in points
        )
        for points in series.values()
    )
    values: dict[str, dict[str, Any]] = {}
    for code, points in series.items():
        annual_values = [
            float(point["precio_eur_m2"])
            for point in points
            if point["fecha"].startswith(f"{year}-")
        ]
        if not annual_values:
            continue
        signature = tuple(
            (point["fecha"], float(point["precio_eur_m2"]))
            for point in points
        )
        values[code] = {
            "precio_medio_eur_m2": sum(annual_values) / len(annual_values),
            "meses_con_dato": len(annual_values),
            "municipios_serie_identica": signatures[signature],
        }
    if not values:
        raise RuntimeError(
            f"No hay precios de alquiler Fotocasa para {year}."
        )
    shared_groups = sum(count > 1 for count in signatures.values())
    return values, {
        "municipios_con_serie": len(series),
        "series_distintas": len(signatures),
        "grupos_de_serie_compartida": shared_groups,
        "municipios_en_series_compartidas": sum(
            count for count in signatures.values() if count > 1
        ),
    }


def _regional_effort_rows(
    municipalities: list[dict[str, Any]],
    annual_rents: dict[str, dict[str, Any]],
    salary_reference: dict[str, Any],
) -> list[dict[str, Any]]:
    salaries = salary_reference["remuneracion_neta_media_por_sexo"]
    municipality_by_code = {
        _required_code(row["_id"]): row for row in municipalities
    }
    rows = []
    for code, rent in annual_rents.items():
        municipality = municipality_by_code.get(code)
        if municipality is None:
            raise RuntimeError(
                f"El precio Fotocasa {code} no tiene municipio en el catálogo."
            )
        price_per_square_metre = rent["precio_medio_eur_m2"]
        monthly_rent_60m2 = price_per_square_metre * 60
        rows.append(
            {
                "municipio_codigo": code,
                "municipio": municipality["nombre"],
                "territorio_historico": municipality.get(
                    "territorio_historico"
                ),
                "periodo": salary_reference["periodo"],
                "fotocasa_meses_con_dato": rent["meses_con_dato"],
                "fotocasa_municipios_serie_identica": (
                    rent["municipios_serie_identica"]
                ),
                "fotocasa_alquiler_medio_eur_m2": price_per_square_metre,
                "alquiler_60m2_estimado_eur_mes": monthly_rent_60m2,
                "salario_referencia_geografia": salary_reference["geografia"],
                "salario_referencia_hombres_16_29_eur_mes": salaries["Hombre"],
                "esfuerzo_hombres_pct": (
                    monthly_rent_60m2 / salaries["Hombre"] * 100
                ),
                "salario_referencia_mujeres_16_29_eur_mes": salaries["Mujer"],
                "esfuerzo_mujeres_pct": (
                    monthly_rent_60m2 / salaries["Mujer"] * 100
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["esfuerzo_mujeres_pct"],
            row["municipio_codigo"],
        ),
    )


def _municipal_work_income_effort_rows(
    municipalities: list[dict[str, Any]],
    work_income: dict[str, dict[str, Any]],
    emal_annual_rents: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    municipality_by_code = {
        _required_code(row["_id"]): row for row in municipalities
    }
    rows = []
    for code in sorted(set(work_income) & set(emal_annual_rents)):
        municipality = municipality_by_code.get(code)
        if municipality is None:
            raise RuntimeError(
                f"El cruce Eustat-EMAL no tiene municipio en el catálogo: {code}."
            )
        annual_income = work_income[code]["valor"]
        monthly_rent = emal_annual_rents[code]["renta_mensual_media_eur"]
        if annual_income <= 0 or monthly_rent <= 0:
            raise RuntimeError(
                f"Valor no positivo en el cruce Eustat-EMAL para {code}."
            )
        annualized_rent = round(monthly_rent * 12, 2)
        rows.append(
            {
                "municipio_codigo": code,
                "municipio": municipality["nombre"],
                "territorio_historico": municipality.get(
                    "territorio_historico"
                ),
                "periodo": MUNICIPAL_WORK_INCOME_PERIOD,
                "eustat_tipo_renta": "Renta del trabajo",
                "eustat_renta_personal_trabajo_media_eur_anual": annual_income,
                "eustat_desglose_edad": False,
                "emal_renta_mensual_media_eur": monthly_rent,
                "emal_alquiler_anualizado_eur": annualized_rent,
                "emal_numero_fianzas_depositadas": (
                    emal_annual_rents[code].get(
                        "numero_fianzas_depositadas"
                    )
                ),
                "emal_observaciones": emal_annual_rents[code][
                    "observaciones"
                ],
                "eustat_observaciones": work_income[code]["observaciones"],
                "alquiler_anual_sobre_renta_trabajo_pct": (
                    round(annualized_rent / annual_income * 100, 2)
                ),
            }
        )
    if not rows:
        raise RuntimeError(
            "No hay municipios con renta Eustat y alquiler anual EMAL "
            "comparables."
        )
    return sorted(
        rows,
        key=lambda row: (
            row["alquiler_anual_sobre_renta_trabajo_pct"],
            row["municipio_codigo"],
        ),
    )


def _rent_variation(
    database: Database, latest_month: str
) -> dict[str, dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "tipo": "alquiler",
                "fecha": {"$lte": latest_month},
                "precio_eur_m2": {"$type": "number", "$gt": 0},
            }
        },
        {"$sort": {"fecha": 1}},
        {
            "$group": {
                "_id": "$municipio_codigo",
                "primer_periodo": {"$first": "$fecha"},
                "primer_precio": {"$first": "$precio_eur_m2"},
                "ultimo_periodo": {"$last": "$fecha"},
                "ultimo_precio": {"$last": "$precio_eur_m2"},
                "meses_con_dato": {"$sum": 1},
            }
        },
        {
            "$project": {
                "primer_periodo": 1,
                "primer_precio": 1,
                "ultimo_periodo": 1,
                "ultimo_precio": 1,
                "meses_con_dato": 1,
                "variacion_pct": {
                    "$cond": [
                        {"$gt": ["$primer_precio", 0]},
                        {
                            "$multiply": [
                                {
                                    "$divide": [
                                        {
                                            "$subtract": [
                                                "$ultimo_precio",
                                                "$primer_precio",
                                            ]
                                        },
                                        "$primer_precio",
                                    ]
                                },
                                100,
                            ]
                        },
                        None,
                    ]
                },
            }
        },
        {"$sort": {"_id": 1}},
    ]
    values = {}
    for row in database["precios_fotocasa"].aggregate(pipeline):
        code = _required_code(row["_id"])
        values[code] = {
            "primer_periodo": row["primer_periodo"],
            "primer_precio": row["primer_precio"],
            "ultimo_periodo": row["ultimo_periodo"],
            "ultimo_precio": row["ultimo_precio"],
            "meses_con_dato": row["meses_con_dato"],
            "variacion_pct": row.get("variacion_pct"),
        }
    return values


def _rental_history(
    database: Database, latest_month: str
) -> list[dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "municipio_codigo": {"$in": list(CAPITALS)},
                "tipo": "alquiler",
                "fecha": {"$gte": "2020-01", "$lte": latest_month},
                "precio_eur_m2": {"$type": "number", "$gt": 0},
            }
        },
        {
            "$group": {
                "_id": {
                    "municipio_codigo": "$municipio_codigo",
                    "periodo": "$fecha",
                },
                "precio_eur_m2": {"$avg": "$precio_eur_m2"},
                "observaciones": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "municipios",
                "localField": "_id.municipio_codigo",
                "foreignField": "_id",
                "as": "catalogo",
            }
        },
        {"$unwind": "$catalogo"},
        {
            "$project": {
                "_id": 0,
                "municipio_codigo": "$_id.municipio_codigo",
                "municipio": "$catalogo.nombre",
                "periodo": "$_id.periodo",
                "precio_oferta_eur_m2": "$precio_eur_m2",
                "observaciones": 1,
            }
        },
        {"$sort": {"municipio_codigo": 1, "periodo": 1}},
    ]
    rows = list(database["precios_fotocasa"].aggregate(pipeline))
    if not rows:
        raise RuntimeError("La evolución histórica de Fotocasa está vacía.")
    counts = Counter(row["municipio_codigo"] for row in rows)
    if set(counts) != set(CAPITALS) or len(set(counts.values())) != 1:
        raise RuntimeError(
            "La serie histórica no contiene el mismo número de meses "
            "para las tres capitales."
        )
    return rows


def _vpo_under_36(
    database: Database, snapshot_date: str
) -> list[dict[str, Any]]:
    pipeline = [
        {
            "$match": {
                "fecha_fotografia": snapshot_date,
                "grupo": "CUPO",
                "categoria": VPO_UNDER_36_CATEGORY,
            }
        },
        {
            "$group": {
                "_id": "$municipio_codigo",
                "municipio": {"$first": "$municipio"},
                "estado_total": {"$first": "$estados.total"},
                "valor_total": {"$first": "$valores.total"},
                "filas": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "municipio_codigo": "$_id",
                "municipio": 1,
                "estado_total": 1,
                "valor_total": 1,
                "filas": 1,
            }
        },
        {"$sort": {"municipio_codigo": 1}},
    ]
    rows = list(database["demanda_vpo"].aggregate(pipeline))
    for row in rows:
        row["municipio_codigo"] = _required_code(row["municipio_codigo"])
    if not rows:
        raise RuntimeError("No hay registros Etxebide para menores de 36 años.")
    return rows


def _merge_municipal_indicators(
    municipalities: list[dict[str, Any]],
    fotocasa_rent: dict[str, dict[str, Any]],
    fotocasa_sale: dict[str, dict[str, Any]],
    emal: dict[str, dict[str, Any]],
    pisoscom: dict[str, dict[str, Any]],
    eustat: dict[str, dict[str, Any]],
    work_income: dict[str, dict[str, Any]],
    variation: dict[str, dict[str, Any]],
    *,
    fotocasa_rent_month: str,
    fotocasa_sale_month: str,
    emal_date: str,
    pisoscom_date: str,
    eustat_period: str,
) -> list[dict[str, Any]]:
    rows = []
    seen_codes = set()
    for municipality in municipalities:
        code = _required_code(municipality["_id"])
        if code in seen_codes:
            raise RuntimeError(f"Municipio duplicado en el catálogo: {code}")
        seen_codes.add(code)
        rent = fotocasa_rent.get(code, {})
        sale = fotocasa_sale.get(code, {})
        registered = emal.get(code, {})
        listings = pisoscom.get(code, {})
        income = eustat.get(code, {})
        labor_income = work_income.get(code, {})
        change = variation.get(code, {})
        rows.append(
            {
                "municipio_codigo": code,
                "municipio": municipality.get("nombre"),
                "territorio_historico": municipality.get(
                    "territorio_historico"
                ),
                "fotocasa_alquiler_periodo": fotocasa_rent_month,
                "fotocasa_alquiler_eur_m2": rent.get("valor"),
                "fotocasa_alquiler_observaciones": rent.get("observaciones"),
                "fotocasa_venta_periodo": fotocasa_sale_month,
                "fotocasa_venta_eur_m2": sale.get("valor"),
                "fotocasa_venta_observaciones": sale.get("observaciones"),
                "emal_fecha_referencia": emal_date,
                "emal_alquiler_registrado_eur_m2": registered.get("valor"),
                "emal_alquileres_vigentes": registered.get(
                    "alquileres_registrados"
                ),
                "emal_observaciones": registered.get("observaciones"),
                "pisoscom_fecha_extraccion": pisoscom_date,
                "pisoscom_alquiler_mediana_eur_m2": listings.get("valor"),
                "pisoscom_alquiler_anuncios": listings.get("anuncios"),
                "eustat_periodo": eustat_period,
                "eustat_renta_personal_disponible_eur": income.get("valor"),
                "eustat_observaciones": income.get("observaciones"),
                "eustat_renta_trabajo_periodo": (
                    MUNICIPAL_WORK_INCOME_PERIOD
                ),
                "eustat_renta_personal_trabajo_media_eur_anual": (
                    labor_income.get("valor")
                ),
                "eustat_renta_trabajo_observaciones": (
                    labor_income.get("observaciones")
                ),
                "fotocasa_alquiler_primer_periodo": change.get(
                    "primer_periodo"
                ),
                "fotocasa_alquiler_primer_eur_m2": change.get("primer_precio"),
                "fotocasa_alquiler_ultimo_periodo": change.get(
                    "ultimo_periodo"
                ),
                "fotocasa_alquiler_ultimo_eur_m2": change.get("ultimo_precio"),
                "fotocasa_alquiler_meses_con_dato": change.get(
                    "meses_con_dato"
                ),
                "fotocasa_alquiler_variacion_pct": change.get("variacion_pct"),
                "fotocasa_emal_diferencia_eur_m2": (
                    rent["valor"] - registered["valor"]
                    if rent.get("valor") is not None
                    and registered.get("valor") is not None
                    else None
                ),
            }
        )
    return rows


def _history_chart_rows(
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_period: dict[str, dict[str, Any]] = {}
    for row in history:
        period_row = by_period.setdefault(row["periodo"], {"periodo": row["periodo"]})
        period_row[row["municipio_codigo"]] = row["precio_oferta_eur_m2"]
    return [by_period[period] for period in sorted(by_period)]


def _scatter_svg(rows: list[dict[str, Any]]) -> str:
    valid_rows = [
        row
        for row in rows
        if isinstance(row.get("fotocasa_alquiler_eur_m2"), (int, float))
        and isinstance(
            row.get("eustat_renta_personal_disponible_eur"), (int, float)
        )
    ]
    if not valid_rows:
        raise RuntimeError("No hay municipios para el gráfico de renta y alquiler.")

    width, height = 900, 520
    left, right, top, bottom = 105, 35, 55, 85
    chart_width = width - left - right
    chart_height = height - top - bottom
    x_values = [float(row["fotocasa_alquiler_eur_m2"]) for row in valid_rows]
    y_values = [
        float(row["eustat_renta_personal_disponible_eur"])
        for row in valid_rows
    ]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    x_padding = max((x_max - x_min) * 0.06, 0.5)
    y_padding = max((y_max - y_min) * 0.06, 1000.0)
    x_min -= x_padding
    x_max += x_padding
    y_min -= y_padding
    y_max += y_padding

    svg = [
        '<svg role="img" aria-label="Renta personal Eustat frente a alquiler '
        'Fotocasa por municipio" viewBox="0 0 900 520" '
        'xmlns="http://www.w3.org/2000/svg">',
        '<text x="450" y="25" text-anchor="middle" class="chart-title">'
        "Renta personal disponible 2024 y alquiler de oferta 2026-10</text>",
    ]
    for tick in range(5):
        fraction = tick / 4
        x_value = x_min + (x_max - x_min) * fraction
        y_value = y_min + (y_max - y_min) * fraction
        x = left + chart_width * fraction
        y = top + chart_height - chart_height * fraction
        svg.extend(
            [
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" '
                f'y2="{top + chart_height}" stroke="#e2e8f0"/>',
                f'<text x="{x:.1f}" y="{top + chart_height + 22}" '
                f'text-anchor="middle">{x_value:.1f}</text>',
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_width}" '
                f'y2="{y:.1f}" stroke="#e2e8f0"/>',
                f'<text x="{left - 10}" y="{y + 4:.1f}" '
                f'text-anchor="end">{y_value:,.0f}</text>',
            ]
        )
    svg.extend(
        [
            f'<line x1="{left}" y1="{top + chart_height}" '
            f'x2="{left + chart_width}" y2="{top + chart_height}" '
            'stroke="#64748b"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" '
            f'y2="{top + chart_height}" stroke="#64748b"/>',
            f'<text x="{left + chart_width / 2:.1f}" y="{height - 28}" '
            'text-anchor="middle">Alquiler Fotocasa (EUR/m²/mes)</text>',
            f'<text x="20" y="{top + chart_height / 2:.1f}" '
            f'transform="rotate(-90 20 {top + chart_height / 2:.1f})" '
            'text-anchor="middle">Renta personal disponible Eustat (EUR, 2024)'
            "</text>",
        ]
    )
    for row in valid_rows:
        rent = float(row["fotocasa_alquiler_eur_m2"])
        income = float(row["eustat_renta_personal_disponible_eur"])
        x = left + chart_width * (rent - x_min) / (x_max - x_min)
        y = top + chart_height - chart_height * (income - y_min) / (y_max - y_min)
        code = row["municipio_codigo"]
        color = "#dc2626" if code in CAPITALS else "#2563eb"
        title = html.escape(
            f"{row['municipio']}: {rent:.2f} EUR/m²/mes; {income:.0f} EUR"
        )
        svg.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}" '
            'fill-opacity="0.62"><title>'
            f"{title}</title></circle>"
        )
        if code in CAPITALS:
            svg.append(
                f'<text x="{x + 6:.1f}" y="{y - 6:.1f}">'
                f"{html.escape(row['municipio'])}</text>"
            )
    svg.append("</svg>")
    return "".join(svg)


def _grouped_capital_svg(rows: list[dict[str, Any]]) -> str:
    width, height = 980, 320
    left, right, top, row_height = 245, 90, 75, 58
    chart_width = width - left - right
    series = (
        ("fotocasa_alquiler_eur_m2", "Fotocasa oferta"),
        ("emal_alquiler_registrado_eur_m2", "EMAL registrado"),
    )
    values = [
        float(row[key])
        for row in rows
        for key, _ in series
        if isinstance(row.get(key), (int, float))
    ]
    if not rows or not values:
        raise RuntimeError("No hay datos para comparar las tres capitales.")
    max_value = max(values) * 1.15
    colors = ("#2563eb", "#059669")
    svg = [
        '<svg role="img" aria-label="Comparación de alquiler en las capitales '
        'por Fotocasa y EMAL" viewBox="0 0 980 320" '
        'xmlns="http://www.w3.org/2000/svg">',
        '<text x="490" y="25" text-anchor="middle" class="chart-title">'
        "Alquiler por m²: oferta y alquiler registrado</text>",
    ]
    for index in range(5):
        value = max_value * index / 4
        x = left + chart_width * index / 4
        svg.extend(
            [
                f'<line x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" '
                f'y2="{top + row_height * len(rows) - 6}" '
                'stroke="#e2e8f0"/>',
                f'<text x="{x:.1f}" y="{top + row_height * len(rows) + 15}" '
                f'text-anchor="middle">{value:.1f}</text>',
            ]
        )
    for row_index, row in enumerate(rows):
        y_base = top + row_index * row_height
        svg.append(
            f'<text x="{left - 12}" y="{y_base + 22}" text-anchor="end">'
            f"{html.escape(row['municipio'])}</text>"
        )
        for series_index, (key, label) in enumerate(series):
            value = row.get(key)
            if not isinstance(value, (int, float)):
                continue
            y = y_base + series_index * 22
            bar_width = chart_width * float(value) / max_value
            svg.extend(
                [
                    f'<rect x="{left}" y="{y}" width="{bar_width:.1f}" '
                    f'height="16" fill="{colors[series_index]}" rx="2"/>',
                    f'<text x="{left + bar_width + 5:.1f}" y="{y + 13}">'
                    f"{float(value):.2f}</text>",
                ]
            )
    legend_y = height - 12
    for index, (_, label) in enumerate(series):
        x = left + index * 205
        svg.extend(
            [
                f'<rect x="{x}" y="{legend_y - 10}" width="12" height="12" '
                f'fill="{colors[index]}"/>',
                f'<text x="{x + 18}" y="{legend_y}">'
                f"{html.escape(label)}</text>",
            ]
        )
    svg.extend(
        [
            f'<text x="{left + chart_width / 2}" y="{height - 28}" '
            'text-anchor="middle">EUR/m²/mes (periodos distintos; comparación descriptiva)'
            "</text>",
            "</svg>",
        ]
    )
    return "".join(svg)


def _safe_svg(figure_html: str) -> str:
    match = re.search(r"<svg\b.*?</svg>", figure_html, re.DOTALL)
    if match is None:
        raise RuntimeError("No se pudo extraer el SVG generado.")
    return match.group(0)


def _svg_figure(filename: str, title: str, note: str) -> str:
    return (
        "<figure><img "
        f"src=\"graficos/{html.escape(filename)}\" "
        f"alt=\"{html.escape(title)}\">"
        f"<figcaption>{html.escape(note)}</figcaption></figure>"
    )


def _format_number(value: Any, decimals: int = 2) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _html_table(
    headers: list[str], rows: Iterable[Iterable[Any]]
) -> str:
    output = ["<table><thead><tr>"]
    output.extend(f"<th>{html.escape(header)}</th>" for header in headers)
    output.append("</tr></thead><tbody>")
    for row in rows:
        output.append("<tr>")
        output.extend(f"<td>{html.escape(str(value))}</td>" for value in row)
        output.append("</tr>")
    output.append("</tbody></table>")
    return "".join(output)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.stem}_",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            output.write(text)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    _write_text(path, text + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"No hay filas para generar {path.name}.")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    _write_text(path, output.getvalue())


def _coverage_rows(
    municipality_rows: list[dict[str, Any]],
    *,
    rent_month: str,
    sale_month: str,
    emal_date: str,
    pisoscom_date: str,
    eustat_period: str,
    regional_effort_count: int,
    municipal_work_effort_count: int,
) -> list[dict[str, Any]]:
    indicators = (
        ("Fotocasa alquiler", "fotocasa_alquiler_eur_m2", rent_month),
        ("Fotocasa compraventa", "fotocasa_venta_eur_m2", sale_month),
        ("EMAL alquiler vigente", "emal_alquiler_registrado_eur_m2", emal_date),
        (
            "Pisos.com anuncios alquiler",
            "pisoscom_alquiler_mediana_eur_m2",
            pisoscom_date,
        ),
        (
            "Eustat renta personal disponible",
            "eustat_renta_personal_disponible_eur",
            eustat_period,
        ),
        (
            "Eustat renta personal media del trabajo (sin edad)",
            "eustat_renta_personal_trabajo_media_eur_anual",
            MUNICIPAL_WORK_INCOME_PERIOD,
        ),
        (
            "Variación Fotocasa alquiler",
            "fotocasa_alquiler_variacion_pct",
            f"{rent_month} frente al inicio de serie",
        ),
        (
            "Diferencia Fotocasa-EMAL",
            "fotocasa_emal_diferencia_eur_m2",
            f"{rent_month} frente a {emal_date}",
        ),
    )
    rows = [
        {
            "indicador": label,
            "periodo_referencia": period,
            "municipios_con_dato": sum(row[key] is not None for row in municipality_rows),
            "municipios_catalogo": len(municipality_rows),
        }
        for label, key, period in indicators
    ]
    rows.append(
        {
            "indicador": "Esfuerzo orientativo con remuneración regional",
            "periodo_referencia": "2024",
            "municipios_con_dato": regional_effort_count,
            "municipios_catalogo": len(municipality_rows),
        }
    )
    rows.append(
        {
            "indicador": "Alquiler EMAL anualizado / renta Eustat del trabajo",
            "periodo_referencia": str(EMAL_ANNUAL_INCOME_YEAR),
            "municipios_con_dato": municipal_work_effort_count,
            "municipios_catalogo": len(municipality_rows),
        }
    )
    return rows


def _build_payload(database: Database, salary_database: Database) -> dict[str, Any]:
    marker = database["_metadata"].find_one({"_id": "fase3_schema"})
    if marker is None or marker.get("version") != 1:
        raise RuntimeError("La base MongoDB no tiene el esquema de Fase 3.")

    fotocasa_rent_month = _latest_period(
        database,
        "precios_fotocasa",
        {"tipo": "alquiler", "precio_eur_m2": {"$type": "number", "$gt": 0}},
        "fecha",
    )
    fotocasa_sale_month = _latest_period(
        database,
        "precios_fotocasa",
        {"tipo": "venta", "precio_eur_m2": {"$type": "number", "$gt": 0}},
        "fecha",
    )
    emal_date = _latest_period(
        database,
        "alquiler_emal",
        {
            "periodicidad": "vigente",
            "renta_mensual_media_eur_m2": {
                "$type": "number",
                "$gt": 0,
            },
        },
        "fecha_referencia",
    )
    pisoscom_date = _latest_period(
        database,
        "anuncios_pisoscom",
        {
            "operacion": "alquiler",
            "precio_m2": {"$type": "number", "$gt": 0},
        },
        "fecha_extraccion",
    )
    eustat_period = _latest_period(
        database,
        "renta_personal_eustat",
        {
            "tabla_eustat": "renta_personal_municipal",
            "tipo_de_renta": "Renta disponible",
            "sexo": "Total",
            "valor": {"$type": "number", "$gt": 0},
        },
        "periodo",
    )
    vpo_date = _latest_period(
        database,
        "demanda_vpo",
        {
            "grupo": "CUPO",
            "categoria": VPO_UNDER_36_CATEGORY,
        },
        "fecha_fotografia",
    )

    municipalities = list(
        database["municipios"].find(
            {},
            {
                "_id": 1,
                "nombre": 1,
                "territorio_historico": 1,
            },
        ).sort("_id", 1)
    )
    if not municipalities:
        raise RuntimeError("El catálogo municipal está vacío.")

    fotocasa_rent = _fotocasa_values(
        database, "alquiler", fotocasa_rent_month
    )
    fotocasa_sale = _fotocasa_values(database, "venta", fotocasa_sale_month)
    emal = _emal_values(database, emal_date)
    pisoscom = _pisoscom_rental_values(database, pisoscom_date)
    eustat = _eustat_values(database, eustat_period)
    work_income = _municipal_work_income_values(
        database, MUNICIPAL_WORK_INCOME_PERIOD
    )
    emal_annual_rents = _emal_annual_rent_values(
        database, EMAL_ANNUAL_INCOME_YEAR
    )
    variation = _rent_variation(database, fotocasa_rent_month)
    salary_reference = _regional_salary_reference(salary_database)
    annual_rents, rent_series_quality = _fotocasa_annual_rents(
        database, salary_reference["periodo"]
    )
    municipality_rows = _merge_municipal_indicators(
        municipalities,
        fotocasa_rent,
        fotocasa_sale,
        emal,
        pisoscom,
        eustat,
        work_income,
        variation,
        fotocasa_rent_month=fotocasa_rent_month,
        fotocasa_sale_month=fotocasa_sale_month,
        emal_date=emal_date,
        pisoscom_date=pisoscom_date,
        eustat_period=eustat_period,
    )
    regional_effort_rows = _regional_effort_rows(
        municipalities,
        annual_rents,
        salary_reference,
    )
    municipal_work_effort_rows = _municipal_work_income_effort_rows(
        municipalities,
        work_income,
        emal_annual_rents,
    )

    rental_history = _rental_history(database, fotocasa_rent_month)
    capital_rows = [
        next(row for row in municipality_rows if row["municipio_codigo"] == code)
        for code in CAPITALS
    ]
    comparable_sources = [
        row
        for row in municipality_rows
        if row["fotocasa_alquiler_eur_m2"] is not None
        and row["emal_alquiler_registrado_eur_m2"] is not None
    ]
    scatter_rows = [
        row
        for row in municipality_rows
        if row["fotocasa_alquiler_eur_m2"] is not None
        and row["eustat_renta_personal_disponible_eur"] is not None
    ]
    unique_series_codes = {
        code
        for code, rent in annual_rents.items()
        if rent["municipios_serie_identica"] == 1
    }
    ranking_rows = sorted(
        (
            row
            for row in municipality_rows
            if row["fotocasa_alquiler_eur_m2"] is not None
            and row["municipio_codigo"] in unique_series_codes
        ),
        key=lambda row: (
            row["fotocasa_alquiler_eur_m2"],
            row["municipio_codigo"],
        ),
    )[:20]
    vpo_rows = _vpo_under_36(database, vpo_date)
    vpo_states = Counter(row.get("estado_total") for row in vpo_rows)

    if set(row["municipio_codigo"] for row in capital_rows) != set(CAPITALS):
        raise RuntimeError("No se encontraron las tres capitales.")
    effort_capital_codes = {
        row["municipio_codigo"]
        for row in regional_effort_rows
        if row["municipio_codigo"] in CAPITALS
    }
    if effort_capital_codes != set(CAPITALS):
        raise RuntimeError(
            "La referencia de esfuerzo 2024 debe incluir las tres capitales."
        )
    if len(comparable_sources) == 0 or len(scatter_rows) == 0:
        raise RuntimeError("Faltan cruces entre fuentes para las visualizaciones.")
    if len(INDICATOR_DEFINITIONS) < 5:
        raise RuntimeError("Faltan indicadores para el requisito de Fase 6.")

    coverage = _coverage_rows(
        municipality_rows,
        rent_month=fotocasa_rent_month,
        sale_month=fotocasa_sale_month,
        emal_date=emal_date,
        pisoscom_date=pisoscom_date,
        eustat_period=eustat_period,
        regional_effort_count=len(regional_effort_rows),
        municipal_work_effort_count=len(municipal_work_effort_rows),
    )
    return {
        "base_datos": PHASE3_DATABASE_NAME,
        "base_datos_salarios": salary_database.name,
        "periodos": {
            "fotocasa_alquiler": fotocasa_rent_month,
            "fotocasa_venta": fotocasa_sale_month,
            "emal_vigente": emal_date,
            "pisoscom_extraccion": pisoscom_date,
            "eustat_renta_personal": eustat_period,
            "eustat_renta_trabajo_municipal": MUNICIPAL_WORK_INCOME_PERIOD,
            "emal_alquiler_anual_municipal": EMAL_ANNUAL_INCOME_YEAR,
            "etxebide_menores_36": vpo_date,
            "esfuerzo_referencia_regional": salary_reference["periodo"],
        },
        "referencia_salarial_regional": salary_reference,
        "calidad_series_fotocasa_alquiler": rent_series_quality,
        "indicadores": INDICATOR_DEFINITIONS,
        "cobertura_indicadores": coverage,
        "municipios_indicadores": municipality_rows,
        "evolucion_alquiler_capitales": rental_history,
        "comparacion_tres_capitales": capital_rows,
        "comparacion_fotocasa_emal": comparable_sources,
        "renta_vs_alquiler_oferta": scatter_rows,
        "ranking_alquiler_fotocasa": ranking_rows,
        "esfuerzo_alquiler_referencia_regional": regional_effort_rows,
        "esfuerzo_alquiler_renta_trabajo_municipal_2024": (
            municipal_work_effort_rows
        ),
        "comparacion_esfuerzo_capitales": [
            next(
                row
                for row in regional_effort_rows
                if row["municipio_codigo"] == code
            )
            for code in CAPITALS
            if any(
                row["municipio_codigo"] == code
                for row in regional_effort_rows
            )
        ],
        "demanda_vpo_menores_36": vpo_rows,
        "cobertura_vpo_menores_36": {
            "municipios_registrados": len(vpo_rows),
            "estados": dict(vpo_states),
        },
    }


def _make_report(payload: dict[str, Any]) -> str:
    periods = payload["periodos"]
    capitals = payload["comparacion_tres_capitales"]
    coverage = payload["cobertura_indicadores"]
    vpo = payload["cobertura_vpo_menores_36"]
    salary_reference = payload["referencia_salarial_regional"]
    effort_capitals = payload["comparacion_esfuerzo_capitales"]
    municipal_work_effort = payload[
        "esfuerzo_alquiler_renta_trabajo_municipal_2024"
    ]
    vpo_published = vpo["estados"].get("disponible", 0)
    vpo_suppressed = vpo["estados"].get(
        "s.e. (dato no publicado/suprimido)", 0
    )
    vpo_total = vpo_published + vpo_suppressed
    vpo_published_pct = 100 * vpo_published / vpo_total if vpo_total else 0

    cheapest = min(
        capitals,
        key=lambda row: row["fotocasa_alquiler_eur_m2"] or math.inf,
    )
    highest_rent = max(
        capitals,
        key=lambda row: row["fotocasa_alquiler_eur_m2"] or -math.inf,
    )
    highest_personal_income = max(
        capitals,
        key=lambda row: (
            row["eustat_renta_personal_disponible_eur"] or -math.inf
        ),
    )
    capital_table_rows = []
    for row in capitals:
        listing_value = row["pisoscom_alquiler_mediana_eur_m2"]
        listing_n = row["pisoscom_alquiler_anuncios"] or 0
        capital_table_rows.append(
            [
                row["municipio"],
                _format_number(row["fotocasa_alquiler_eur_m2"]),
                _format_number(row["fotocasa_venta_eur_m2"]),
                _format_number(row["emal_alquiler_registrado_eur_m2"], 3),
                (
                    f"{_format_number(listing_value)} (n={listing_n})"
                    if listing_value is not None
                    else "—"
                ),
                _format_number(
                    row["eustat_renta_personal_disponible_eur"], 0
                ),
                _format_number(row["fotocasa_emal_diferencia_eur_m2"], 3),
            ]
        )

    coverage_table_rows = [
        [
            row["indicador"],
            row["periodo_referencia"],
            row["municipios_con_dato"],
            row["municipios_catalogo"],
        ]
        for row in coverage
    ]
    vpo_table_rows = [
        ["Con valor publicado", vpo_published, f"{vpo_published_pct:.1f}%"],
        [
            "Suprimido/no publicado",
            vpo_suppressed,
            f"{100 - vpo_published_pct:.1f}%",
        ],
    ]
    ranking_top = payload["ranking_alquiler_fotocasa"][:10]
    ranking_rows = [
        [
            row["municipio"],
            row["municipio_codigo"],
            row["territorio_historico"] or "—",
            _format_number(row["fotocasa_alquiler_eur_m2"]),
        ]
        for row in ranking_top
    ]
    effort_capital_rows = [
        [
            row["municipio"],
            _format_number(row["fotocasa_alquiler_medio_eur_m2"]),
            _format_number(row["alquiler_60m2_estimado_eur_mes"]),
            _format_number(row["esfuerzo_hombres_pct"]),
            _format_number(row["esfuerzo_mujeres_pct"]),
        ]
        for row in effort_capitals
    ]
    lowest_effort = min(
        effort_capitals,
        key=lambda row: row["esfuerzo_mujeres_pct"],
    )
    highest_effort = max(
        effort_capitals,
        key=lambda row: row["esfuerzo_mujeres_pct"],
    )
    lowest_municipal_work_effort = municipal_work_effort[0]
    highest_municipal_work_effort = municipal_work_effort[-1]
    municipal_work_effort_by_code = {
        row["municipio_codigo"]: row for row in municipal_work_effort
    }
    displayed_effort_codes = set(CAPITALS)
    displayed_effort_codes.update(
        row["municipio_codigo"] for row in municipal_work_effort[:3]
    )
    displayed_effort_codes.update(
        row["municipio_codigo"] for row in municipal_work_effort[-3:]
    )
    municipal_work_effort_table_rows = [
        [
            row["municipio"],
            row["municipio_codigo"],
            _format_number(
                row["eustat_renta_personal_trabajo_media_eur_anual"], 0
            ),
            _format_number(row["emal_renta_mensual_media_eur"]),
            row["emal_numero_fianzas_depositadas"] or "—",
            _format_number(row["alquiler_anual_sobre_renta_trabajo_pct"]),
        ]
        for row in sorted(
            (
                municipal_work_effort_by_code[code]
                for code in displayed_effort_codes
                if code in municipal_work_effort_by_code
            ),
            key=lambda row: row["alquiler_anual_sobre_renta_trabajo_pct"],
        )
    ]

    graph_specs = [
        (
            "evolucion_alquiler_capitales.svg",
            "Evolución mensual del alquiler Fotocasa en las tres capitales",
            (
                "Serie mensual de oferta Fotocasa. Valores nominales en EUR/m²/mes; "
                "no están ajustados por inflación."
            ),
        ),
        (
            "comparacion_alquiler_capitales.svg",
            "Alquiler por metro cuadrado: Fotocasa y EMAL en las capitales",
            (
                f"Fotocasa {periods['fotocasa_alquiler']} frente a EMAL "
                f"{periods['emal_vigente']}. Son fuentes y periodos distintos; "
                "la comparación es descriptiva."
            ),
        ),
        (
            "renta_personal_vs_alquiler.svg",
            "Renta personal disponible Eustat y alquiler Fotocasa por municipio",
            (
                f"Cada punto es un municipio con ambos datos: Eustat "
                f"{periods['eustat_renta_personal']} y Fotocasa "
                f"{periods['fotocasa_alquiler']}. No es un indicador de "
                "esfuerzo ni una relación causal."
            ),
        ),
        (
            "municipios_alquiler_mas_bajo.svg",
            "Municipios con serie Fotocasa no compartida y menor alquiler",
            (
                f"Series no compartidas con menor valor en "
                f"{periods['fotocasa_alquiler']}; no se pondera por población "
                "ni por número de anuncios."
            ),
        ),
        (
            "esfuerzo_salario_regional_hombres_capitales.svg",
            "Alquiler de 60 m² sobre remuneración regional 16-29: hombres",
            (
                "Estimación 2024: alquiler Fotocasa municipal frente a la "
                "remuneración neta media regional de hombres de 16-29 años."
            ),
        ),
        (
            "esfuerzo_salario_regional_mujeres_capitales.svg",
            "Alquiler de 60 m² sobre remuneración regional 16-29: mujeres",
            (
                "Estimación 2024: alquiler Fotocasa municipal frente a la "
                "remuneración neta media regional de mujeres de 16-29 años."
            ),
        ),
        (
            "esfuerzo_renta_trabajo_municipios_2024.svg",
            "Alquiler registrado EMAL sobre renta personal del trabajo Eustat",
            (
                "Municipios con datos de ambas fuentes en 2024. La renta Eustat "
                "no está desglosada por edad y no equivale a salario neto."
            ),
        ),
    ]
    chart_figures = "".join(
        _svg_figure(filename, title, note)
        for filename, title, note in graph_specs
    )
    methods = (
        "Los agregados se ejecutan en MongoDB mediante PyMongo y se cruzan por "
        "municipio_codigo, conservado como texto de cinco caracteres. La "
        "mediana de anuncios Pisos.com se calcula en Python sobre los valores "
        "agrupados por MongoDB; se informa el número de anuncios que la forma. "
        "Las medias municipales no están ponderadas por población. Se mantienen "
        "por separado la oferta Fotocasa, el alquiler registrado EMAL, los "
        "anuncios individuales Pisos.com y la renta personal Eustat. Para el "
        "esfuerzo orientativo se compara la media mensual municipal de Fotocasa "
        "durante 2024 para una vivienda de 60 m² con la remuneración neta media "
        "regional de 2024 para personas asalariadas y asimiladas de 16-29 años, "
        "por sexo. Además, se comparan los alquileres mensuales medios EMAL de "
        "contratos iniciados en 2024, anualizados a 12 meses, con la renta "
        "personal media Eustat de la categoría Renta del trabajo por municipio."
    )
    limitations = (
        "Los cocientes de alquiler/renta son indicadores orientativos, no "
        "salarios ni tasas observadas de esfuerzo. La Renta del trabajo de "
        "Eustat es una renta personal media anual municipal sin desglose por "
        "edad y no equivale a salario neto juvenil. EMAL mide la renta mensual "
        "media de contratos iniciados en el año y su cobertura se limita a "
        "municipios con datos disponibles; la hoja original se refiere a "
        "municipios de más de 5.000 habitantes. El escenario regional usa una media "
        "de Euskadi, no un salario municipal ni el ingreso de toda la juventud; "
        "el alquiler se supone asumido por una sola persona y no incluye gastos "
        "ni vivienda compartida. La referencia IOVJ de 18-29 años se muestra por separado "
        "porque su grupo de edad y metodología no coinciden con remuMedia. "
        "salAnual.json es nacional, no se usa como salario de Euskadi. La renta "
        "personal disponible Eustat tampoco es salario. Los valores de Etxebide "
        "suprimidos no se extrapolan. La serie Fotocasa es nominal; además, "
        f"{payload['calidad_series_fotocasa_alquiler']['municipios_en_series_compartidas']} "
        "municipios comparten trayectorias completas de alquiler con otros "
        "códigos, por lo que no se interpretan esos valores repetidos como "
        "observaciones municipales independientes. El ranking Fotocasa se "
        "limita a series no compartidas. Pisos.com tiene cobertura menor."
    )
    conclusion = (
        f"Entre las tres capitales, {cheapest['municipio']} presenta el menor "
        f"precio de oferta de alquiler Fotocasa "
        f"({_format_number(cheapest['fotocasa_alquiler_eur_m2'])} EUR/m²/mes, "
        f"{periods['fotocasa_alquiler']}); {highest_rent['municipio']} presenta "
        f"el mayor ({_format_number(highest_rent['fotocasa_alquiler_eur_m2'])} "
        f"EUR/m²/mes). La mayor renta personal disponible Eustat corresponde a "
        f"{highest_personal_income['municipio']} "
        f"({_format_number(highest_personal_income['eustat_renta_personal_disponible_eur'], 0)} "
        f"EUR en {periods['eustat_renta_personal']}), pero esto no permite "
        "concluir que las personas jóvenes puedan emanciparse allí. Entre las "
        "capitales, con la referencia regional de ingresos, el menor esfuerzo "
        f"estimado es {lowest_effort['municipio']} "
        f"({_format_number(lowest_effort['esfuerzo_mujeres_pct'])}% para la "
        "referencia femenina) y el mayor es "
        f"{highest_effort['municipio']} "
        f"({_format_number(highest_effort['esfuerzo_mujeres_pct'])}%). "
        "Es una comparación orientativa de precios de Fotocasa con ingresos "
        "regionales, no una tasa observada de esfuerzo de cada municipio. "
        f"En el cruce municipal EMAL-Eustat de {len(municipal_work_effort)} "
        "municipios, el alquiler medio anualizado más bajo frente a la renta "
        "personal del trabajo corresponde a "
        f"{lowest_municipal_work_effort['municipio']} "
        f"({_format_number(lowest_municipal_work_effort['alquiler_anual_sobre_renta_trabajo_pct'])}%) "
        "y el más alto a "
        f"{highest_municipal_work_effort['municipio']} "
        f"({_format_number(highest_municipal_work_effort['alquiler_anual_sobre_renta_trabajo_pct'])}%). "
        "Este indicador cubre ingresos de todos los grupos de edad; no responde "
        "por sí solo a la capacidad de emancipación de las personas jóvenes. "
        f"En el conjunto de 251 códigos, solo hay "
        f"{payload['calidad_series_fotocasa_alquiler']['series_distintas']} "
        "trayectorias históricas distintas."
    )

    sections = [
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Fase 6: indicadores municipales de vivienda</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1180px;"
        "margin:2rem auto;padding:0 1rem;color:#172033;background:#f8fafc}"
        "h1,h2{color:#0f3b67}figure,section{background:white;border:1px solid "
        "#dbe3ee;border-radius:8px;padding:1rem;margin:1.2rem 0}img{width:100%;"
        "height:auto}table{border-collapse:collapse;width:100%;display:block;"
        "overflow-x:auto;background:white}th,td{border:1px solid #dbe3ee;"
        "padding:.45rem;text-align:left}th{background:#eaf1f8}small,.note{"
        "color:#475569}</style></head><body>",
        "<h1>¿Dónde pueden vivir los jóvenes en Euskadi?</h1>",
        "<p>Fase 6. Análisis generado desde MongoDB "
        f"<code>{html.escape(PHASE3_DATABASE_NAME)}</code> y referencias "
        f"salariales de <code>{html.escape(salary_reference['geografia'])}</code> "
        f"desde <code>{html.escape(payload['base_datos_salarios'])}</code>, el "
        f"{html.escape(datetime.now().astimezone().isoformat(timespec='minutes'))}.</p>",
        "<h2>Indicadores y cobertura</h2>",
        _html_table(
            ["Indicador", "Periodo", "Municipios con dato", "Catálogo"],
            coverage_table_rows,
        ),
        "<h2>Comparación de las capitales</h2>",
        _html_table(
            [
                "Municipio",
                f"Fotocasa alquiler ({periods['fotocasa_alquiler']}) EUR/m²/mes",
                f"Fotocasa venta ({periods['fotocasa_venta']}) EUR/m²",
                f"EMAL ({periods['emal_vigente']}) EUR/m²/mes",
                f"Pisos.com alquiler ({periods['pisoscom_extraccion']}) EUR/m²/mes",
                f"Eustat renta personal disponible ({periods['eustat_renta_personal']}) EUR",
                "Fotocasa−EMAL EUR/m²/mes (descriptivo)",
            ],
            capital_table_rows,
        ),
        "<h2>Esfuerzo orientativo con ingresos regionales (2024)</h2>",
        (
            "<p>La remuneración neta media regional de 16-29 años en 2024 fue "
            f"{_format_number(salary_reference['remuneracion_neta_media_por_sexo']['Hombre'], 0)} "
            "EUR/mes para hombres y "
            f"{_format_number(salary_reference['remuneracion_neta_media_por_sexo']['Mujer'], 0)} "
            "EUR/mes para mujeres. La tabla compara esos valores con el alquiler "
            "Fotocasa medio de cada municipio para 60 m².</p>"
        ),
        _html_table(
            [
                "Municipio",
                "Alquiler Fotocasa 2024 EUR/m²/mes",
                "Alquiler estimado 60 m² EUR/mes",
                "Esfuerzo vs referencia hombres %",
                "Esfuerzo vs referencia mujeres %",
            ],
            effort_capital_rows,
        ),
        (
            "<p>Como contraste separado, IOVJ registra "
            f"{_format_number(salary_reference['referencia_iovj']['valor'], 0)} "
            "para el grupo 18-29 en 2024. No se mezcla con remuMedia, que "
            "utiliza 16-29 años y desglosa por sexo.</p>"
        ),
        "<h2>Comparación municipal EMAL y renta del trabajo Eustat (2024)</h2>",
        (
            "<p>Se cruzan por código municipal los contratos EMAL iniciados en "
            "2024 con la renta personal media anual Eustat de la categoría "
            "«Renta del trabajo». El cociente anualiza la renta mensual media "
            "EMAL por 12 y la divide por la renta personal del trabajo. "
            "Incluye todos los grupos de edad disponibles en Eustat: no es un "
            "salario juvenil ni una medida neta. El cruce solo incluye los "
            f"{len(municipal_work_effort)} municipios con datos válidos en "
            "ambas fuentes. La hoja EMAL de origen cubre municipios de más de "
            "5.000 habitantes.</p>"
        ),
        _html_table(
            [
                "Municipio",
                "Código",
                "Eustat renta trabajo EUR/año",
                "EMAL renta mensual EUR",
                "Fianzas EMAL",
                "Alquiler anualizado / renta trabajo %",
            ],
            municipal_work_effort_table_rows,
        ),
        f"<p>{html.escape(conclusion)}</p>",
        "<h2>Resultados preparados para visualización</h2>",
        chart_figures,
        "<h2>Municipios con series Fotocasa no compartidas y menor alquiler</h2>",
        _html_table(
            ["Municipio", "Código", "Territorio histórico", "EUR/m²/mes"],
            ranking_rows,
        ),
        "<h2>Demanda Etxebide de menores de 36 años</h2>",
        f"<p>Fotografía {html.escape(periods['etxebide_menores_36'])}, "
        f"categoría de menores de 36 años: {vpo_total} municipios. "
        "Los estados se muestran sin convertir supresiones a cero ni sumar "
        "los valores como si fueran un total completo.</p>",
        _html_table(["Estado del total", "Municipios", "Cobertura"], vpo_table_rows),
        "<h2>Metodología y límites</h2>",
        f"<p>{html.escape(methods)}</p>",
        f"<p class=\"note\">{html.escape(limitations)}</p>",
        "<p>El detalle completo, las fechas por fuente y los conjuntos CSV/JSON "
        "están en la misma carpeta que este informe.</p>",
        "</body></html>",
    ]
    return "\n".join(sections)


def _write_outputs(payload: dict[str, Any]) -> None:
    graph_directory = OUTPUT_DIR / "graficos"
    graph_directory.mkdir(parents=True, exist_ok=True)
    history_figure = _svg_chart(
        "Alquiler anunciado por Fotocasa en las tres capitales",
        _history_chart_rows(payload["evolucion_alquiler_capitales"]),
        x_key="periodo",
        y_keys=[
            (code, CAPITALS[code])
            for code in CAPITALS
        ],
        y_unit="EUR/m²/mes",
    )
    _write_text(
        graph_directory / "evolucion_alquiler_capitales.svg",
        _safe_svg(history_figure),
    )

    capitals_figure = _grouped_capital_svg(
        payload["comparacion_tres_capitales"]
    )
    _write_text(
        graph_directory / "comparacion_alquiler_capitales.svg",
        capitals_figure,
    )
    _write_text(
        graph_directory / "renta_personal_vs_alquiler.svg",
        _scatter_svg(payload["renta_vs_alquiler_oferta"]),
    )

    ranking_figure = _svg_bar_chart(
        "Municipios con serie Fotocasa no compartida y menor alquiler",
        payload["ranking_alquiler_fotocasa"],
        label_key="municipio",
        value_key="fotocasa_alquiler_eur_m2",
        y_unit="EUR/m²/mes",
    )
    _write_text(
        graph_directory / "municipios_alquiler_mas_bajo.svg",
        _safe_svg(ranking_figure),
    )
    municipal_effort_ranking = sorted(
        payload["esfuerzo_alquiler_renta_trabajo_municipal_2024"],
        key=lambda row: (
            row["alquiler_anual_sobre_renta_trabajo_pct"],
            row["municipio_codigo"],
        ),
        reverse=True,
    )[:10]
    municipal_effort_figure = _svg_bar_chart(
        "Mayor alquiler EMAL anualizado sobre renta personal del trabajo (2024)",
        municipal_effort_ranking,
        label_key="municipio",
        value_key="alquiler_anual_sobre_renta_trabajo_pct",
        y_unit="% de renta personal anual",
    )
    _write_text(
        graph_directory / "esfuerzo_renta_trabajo_municipios_2024.svg",
        _safe_svg(municipal_effort_figure),
    )
    for sex, label in (("hombres", "hombres"), ("mujeres", "mujeres")):
        effort_figure = _svg_bar_chart(
            (
                "Esfuerzo estimado del alquiler de 60 m² frente a "
                f"remuneración regional 16-29: {label}"
            ),
            payload["comparacion_esfuerzo_capitales"],
            label_key="municipio",
            value_key=f"esfuerzo_{sex}_pct",
            y_unit="% de la referencia neta mensual",
        )
        _write_text(
            graph_directory
            / f"esfuerzo_salario_regional_{sex}_capitales.svg",
            _safe_svg(effort_figure),
        )
    _write_json(OUTPUT_DIR / "resultados_fase6.json", payload)
    _write_csv(
        OUTPUT_DIR / "indicadores_municipales.csv",
        payload["municipios_indicadores"],
    )
    _write_csv(
        OUTPUT_DIR / "evolucion_alquiler_capitales.csv",
        payload["evolucion_alquiler_capitales"],
    )
    _write_csv(
        OUTPUT_DIR / "comparacion_tres_capitales.csv",
        payload["comparacion_tres_capitales"],
    )
    _write_csv(
        OUTPUT_DIR / "comparacion_fotocasa_emal.csv",
        payload["comparacion_fotocasa_emal"],
    )
    _write_csv(
        OUTPUT_DIR / "renta_vs_alquiler_oferta.csv",
        payload["renta_vs_alquiler_oferta"],
    )
    _write_csv(
        OUTPUT_DIR / "demanda_vpo_menores_36.csv",
        payload["demanda_vpo_menores_36"],
    )
    _write_csv(
        OUTPUT_DIR / "esfuerzo_alquiler_referencia_regional_2024.csv",
        payload["esfuerzo_alquiler_referencia_regional"],
    )
    _write_csv(
        OUTPUT_DIR / "esfuerzo_alquiler_renta_trabajo_municipal_2024.csv",
        payload["esfuerzo_alquiler_renta_trabajo_municipal_2024"],
    )
    _write_text(
        OUTPUT_DIR / "informe_fase6.html",
        _make_report(payload),
    )


def run(database: Database, salary_database: Database) -> dict[str, Any]:
    payload = _build_payload(database, salary_database)
    if len(payload["indicadores"]) < 5:
        raise RuntimeError("El informe no contiene cinco indicadores.")
    if len(payload["evolucion_alquiler_capitales"]) < 3:
        raise RuntimeError("La serie temporal no alcanza tres observaciones.")
    if len(payload["comparacion_tres_capitales"]) != 3:
        raise RuntimeError("La comparación debe incluir las tres capitales.")
    if len(payload["comparacion_esfuerzo_capitales"]) != 3:
        raise RuntimeError(
            "La comparación de esfuerzo debe incluir las tres capitales."
        )
    municipal_work_effort_codes = {
        row["municipio_codigo"]
        for row in payload["esfuerzo_alquiler_renta_trabajo_municipal_2024"]
    }
    if not set(CAPITALS).issubset(municipal_work_effort_codes):
        raise RuntimeError(
            "El cruce municipal Eustat-EMAL debe incluir las tres capitales."
        )
    return payload


def main() -> None:
    global OUTPUT_DIR

    parser = argparse.ArgumentParser(
        description=(
            "Genera indicadores municipales y un escenario de esfuerzo con "
                "ingresos regionales y municipales desde MongoDB."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directorio de salida (por defecto: resultados/fase6).",
    )
    args = parser.parse_args()

    OUTPUT_DIR = args.output_dir.resolve()
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        payload = run(client[PHASE3_DATABASE_NAME], client[DB_NAME])
        _write_outputs(payload)
        print(f"Base consultada: {PHASE3_DATABASE_NAME}")
        print(f"Base de referencias salariales: {DB_NAME}")
        print(f"Periodos: {payload['periodos']}")
        print(f"Indicadores: {len(payload['indicadores'])}")
        print(
            "Municipios: "
            f"{len(payload['municipios_indicadores'])}; "
            "evolución capitales: "
            f"{len(payload['evolucion_alquiler_capitales'])}; "
            "cruce EMAL-Fotocasa: "
            f"{len(payload['comparacion_fotocasa_emal'])}; "
            "renta/alquiler: "
            f"{len(payload['renta_vs_alquiler_oferta'])}; "
            "municipios con esfuerzo regional: "
            f"{len(payload['esfuerzo_alquiler_referencia_regional'])}; "
            "cruce EMAL-Eustat trabajo: "
            f"{len(payload['esfuerzo_alquiler_renta_trabajo_municipal_2024'])}."
        )
        print(f"Resultados guardados en {OUTPUT_DIR}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

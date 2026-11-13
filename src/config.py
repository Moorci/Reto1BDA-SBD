from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

BASE_DIR = Path(__file__).resolve().parent.parent

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "reto_vivienda")
PHASE3_DATABASE_NAME = "reto_vivienda_fase3"

DATA_ROOTS: Dict[str, Path] = {
    "akira": BASE_DIR / "DatosAkira",
    "alvaro": BASE_DIR / "DatosAlvaro",
    "iker": BASE_DIR / "DatosIker",
}

SUPPORTED_EXTENSIONS = {
    ".csv",
    ".json",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".txt",
    ".html",
}
DEFAULT_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
CSV_DELIMITERS = [",", ";", "\t", "|"]
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".vscode",
    ".ipynb_checkpoints",
    "informes",
}

DATASET_RULES: List[Dict[str, Any]] = [
    {
        "patterns": ["series_historicas"],
        "collection": "precios_vivienda",
        "natural_key_fields": [],
    },
    {
        "patterns": ["eustat"],
        "collection": "indicadores_economicos",
        "natural_key_fields": [],
    },
    {
        "patterns": ["demandantes-etxebide", "etxebide", "vpo"],
        "collection": "vivienda_protegida",
        "natural_key_fields": [],
    },
    {
        "patterns": ["iovj-empleo", "empleo-economico", "sincontratos"],
        "collection": "indicadores_laborales",
        "natural_key_fields": [],
    },
    {
        "patterns": ["emal", "xls0017789", "xls0017999"],
        "collection": "alquiler_vivienda",
        "natural_key_fields": [],
    },
    {
        "patterns": ["remumedia", "remuneracion", "salario"],
        "collection": "salarios",
        "natural_key_fields": [],
    },
    {
        "patterns": ["emal", "xls0017789", "xls0017999", "alquiler", "fianza"],
        "collection": "alquiler_vivienda",
        "natural_key_fields": [],
    },
    {
        "patterns": ["pisos_euskadi", "precio-compra", "preciom2", "venta"],
        "collection": "vivienda_venta",
        "natural_key_fields": ["url"],
    },
    {
        "patterns": ["promociones"],
        "collection": "vivienda_protegida",
        "natural_key_fields": ["id_prom"],
    },
    {
        "patterns": ["poblacion", "población", "demografia", "demografía"],
        "collection": "poblacion",
        "natural_key_fields": [],
    },
    {
        "patterns": ["municipio", "territorio", "eustat", "fotocasa"],
        "collection": "indicadores_geograficos",
        "natural_key_fields": [],
    },
]

COLUMN_ALIASES = {
    "codigo_municipio": "municipio_codigo",
    "municipality_code": "municipio_codigo",
    "municipio_oficial": "municipio",
    "nombre_municipio": "municipio",
    "period": "periodo",
    "year": "anio",
}

NON_EMPTY_VALUES = {
    "",
    "nan",
    "n/a",
    "na",
    "none",
    "null",
    "-",
    "--",
    ":",
    "s.e.",
    "s.e",
    "s.e. (dato no publicado/suprimido)",
}

NORMALIZATION_RULES: Dict[str, Any] = {
    "municipio_fields": {
        "municipio",
        "municipio_bilingue",
        "localidad",
        "territorio",
        "provincia",
        "comunidad",
    },
    "number_fields": {
        "precio",
        "precio_eur",
        "precio_m2",
        "precio_eur_m2",
        "precio_m2_eur",
        "renta",
        "renta_mensual_media_eur",
        "renta_mensual_eur",
        "renta_eur_m2",
        "salario",
        "salario_bruto_anual_eur",
        "remuneracion",
        "ingresos",
        "valor",
        "value",
        "total",
        "habitaciones",
        "banos",
        "metros",
        "metros_m2",
        "numviviendas",
        "empadronado_compra",
        "empadronado_alquiler",
        "empadronados",
        "noempadronado_compra",
        "noempadronado_alquiler",
        "noempadronados",
        "registros_alquiler",
        "registros_venta",
    },
    "date_fields": {
        "fecha",
        "fecha_referencia",
        "fecha_importacion",
        "fecha_extraccion",
        "fecha_inicio",
        "fecha_fin",
    },
    "period_fields": {
        "periodo",
        "anio",
        "mes",
    },
    "non_negative_fields": {
        "precio",
        "precio_eur",
        "precio_m2",
        "precio_eur_m2",
        "precio_m2_eur",
        "renta",
        "renta_mensual_media_eur",
        "renta_mensual_eur",
        "renta_eur_m2",
        "salario",
        "salario_bruto_anual_eur",
        "remuneracion",
        "ingresos",
        "habitaciones",
        "banos",
        "metros",
        "metros_m2",
        "numviviendas",
    },
}


def iter_data_roots() -> Iterable[Path]:
    for path in DATA_ROOTS.values():
        if path.exists():
            yield path


def ensure_parent_dir(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

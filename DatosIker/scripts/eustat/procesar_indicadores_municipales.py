from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from src.transformar import flatten_eustat_table, normalize_column_name

DATA_ROOT = PROJECT_ROOT / "DatosIker"
SOURCE_ROOT = DATA_ROOT / "originales"
OUTPUT_ROOT = DATA_ROOT / "procesados" / "eustat"
CATALOG_PATH = SOURCE_ROOT / "fotocasa" / "catalogo_municipios_fotocasa.csv"

TABLES = (
    ("eustat_renta_por_municipio.json", "renta_personal_municipal.json"),
    (
        "eustat_indicadores_municipales.json",
        "indicadores_renta_personal_municipal.json",
    ),
    (
        "eustat_percentiles_renta_municipales.json",
        "percentiles_renta_personal_municipal.json",
    ),
    (
        "eustat_distribucion_renta_municipal.json",
        "distribucion_renta_personal_municipal.json",
    ),
)


def load_municipality_catalog(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"No se encuentra el catálogo municipal: {path}")

    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter=";")
        required_fields = {"municipio_codigo", "municipio_oficial"}
        if not reader.fieldnames or not required_fields.issubset(reader.fieldnames):
            raise ValueError(
                f"El catálogo no contiene los campos requeridos "
                f"{sorted(required_fields)}: {reader.fieldnames}"
            )

        municipalities: dict[str, str] = {}
        for row_number, row in enumerate(reader, start=2):
            code = (row.get("municipio_codigo") or "").strip()
            name = (row.get("municipio_oficial") or "").strip()
            if not re.fullmatch(r"\d{5}", code):
                raise ValueError(
                    f"Código municipal inválido en la fila {row_number}: {code!r}"
                )
            if not name:
                raise ValueError(
                    f"Nombre municipal vacío en la fila {row_number}, código {code}"
                )
            if code in municipalities:
                raise ValueError(f"Código municipal duplicado en el catálogo: {code}")
            municipalities[code] = name

    if not municipalities:
        raise ValueError("El catálogo no contiene municipios.")
    return municipalities


def process_table(
    source_path: Path,
    municipalities: dict[str, str],
) -> list[dict[str, Any]]:
    if not source_path.is_file():
        raise FileNotFoundError(f"No se encuentra el original de Eustat: {source_path}")

    with source_path.open(encoding="utf-8-sig") as source:
        table = json.load(source)

    flattened = flatten_eustat_table(table)
    if flattened is None:
        raise ValueError(
            f"No se pudo aplanar la tabla multidimensional de {source_path.name}"
        )

    dimensions = table.get("dimension")
    territory_dimension = next(
        (
            name
            for name in dimensions
            if normalize_column_name(name) == "ambitos_territoriales"
        ),
        None,
    )
    if territory_dimension is None:
        raise ValueError(
            f"{source_path.name} no incluye la dimensión de ámbitos territoriales"
        )

    territory = dimensions[territory_dimension]["category"]
    territory_codes = {str(code) for code in territory["index"]}
    missing_codes = set(municipalities) - territory_codes
    if missing_codes:
        raise ValueError(
            f"{source_path.name} no contiene {len(missing_codes)} códigos del catálogo: "
            f"{sorted(missing_codes)[:10]}"
        )

    code_field = f"{normalize_column_name(territory_dimension)}_codigo"
    records: list[dict[str, Any]] = []
    for row in flattened:
        code = str(row.get(code_field, ""))
        if code not in municipalities:
            continue
        if not re.fullmatch(r"\d{5}", code):
            raise ValueError(
                f"Código municipal no conservado como texto de cinco dígitos: {code!r}"
            )

        row["municipio_codigo"] = code
        row["municipio"] = municipalities[code]
        row["nivel_geografico"] = "municipio"
        row["archivo_origen"] = source_path.name
        records.append(row)

    other_dimensions = [
        definition
        for name, definition in dimensions.items()
        if name not in {"id", "size", "role", territory_dimension}
        and isinstance(definition, dict)
        and isinstance(definition.get("category"), dict)
    ]
    expected_count = len(municipalities) * math.prod(
        len(definition["category"]["index"])
        for definition in other_dimensions
    )
    if len(records) != expected_count:
        raise ValueError(
            f"{source_path.name}: se esperaban {expected_count} observaciones "
            f"municipales, se obtuvieron {len(records)}"
        )

    observation_ids = [record["indice_observacion"] for record in records]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError(f"{source_path.name}: hay índices de observación duplicados")

    return records


def write_outputs(
    outputs: list[tuple[Path, list[dict[str, Any]]]],
    *,
    overwrite: bool,
) -> None:
    existing = [path for path, _ in outputs if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Ya existen resultados; no se sobrescribirán sin --sobrescribir: "
            + ", ".join(str(path) for path in existing)
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_paths: list[Path] = []
    try:
        for target, records in outputs:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=OUTPUT_ROOT,
                prefix=".eustat_",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                temporary_paths.append(temporary_path)
                json.dump(
                    records,
                    output,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                output.write("\n")

        for temporary_path, (target, _) in zip(temporary_paths, outputs):
            os.replace(temporary_path, target)
    finally:
        for temporary_path in temporary_paths:
            if temporary_path.exists():
                temporary_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prepara tablas de renta personal Eustat al nivel municipal, "
            "sin modificar los originales."
        )
    )
    parser.add_argument(
        "--sobrescribir",
        action="store_true",
        help="Permite sustituir explícitamente los JSON procesados existentes.",
    )
    args = parser.parse_args()

    municipalities = load_municipality_catalog(CATALOG_PATH)
    outputs: list[tuple[Path, list[dict[str, Any]]]] = []
    for source_name, output_name in TABLES:
        records = process_table(SOURCE_ROOT / source_name, municipalities)
        outputs.append((OUTPUT_ROOT / output_name, records))

    write_outputs(outputs, overwrite=args.sobrescribir)

    for path, records in outputs:
        missing_values = sum(record["valor"] is None for record in records)
        print(
            f"{path.relative_to(PROJECT_ROOT)}: "
            f"{len(records)} observaciones; "
            f"{len({record['municipio_codigo'] for record in records})} municipios; "
            f"{missing_values} valores ausentes conservados."
        )
    print(f"Catálogo aplicado: {len(municipalities)} códigos municipales.")


if __name__ == "__main__":
    main()

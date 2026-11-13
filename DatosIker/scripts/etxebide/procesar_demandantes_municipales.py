from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "DatosIker"
CATALOG_PATH = (
    DATA_ROOT / "originales" / "fotocasa" / "catalogo_municipios_fotocasa.csv"
)
SOURCE_ROOT = PROJECT_ROOT / "DatosAlvaro" / "Vivienda" / "VPO"
OUTPUT_ROOT = DATA_ROOT / "procesados" / "etxebide"

SNAPSHOTS = (
    (
        "Demandantes-Etxebide-Municipio-2026-04-01_limpio.csv",
        "2026-04-01",
    ),
    (
        "Demandantes-Etxebide-Municipio-2026-07-01_limpio.csv",
        "2026-07-01",
    ),
)
REQUIRED_SOURCE_FIELDS = {
    "Municipio",
    "Municipio_bilingue",
    "Grupo",
    "Literal",
    "Total",
    "Total_estado",
}
MUNICIPALITY_ALIASES = {"donostia": "donostiasansebastian"}


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFD", value.strip().casefold())
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", text)


def load_catalog(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"No se encuentra el catálogo municipal: {path}")

    municipalities: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter=";")
        required_fields = {"municipio_codigo", "municipio_oficial"}
        if not reader.fieldnames or not required_fields.issubset(reader.fieldnames):
            raise ValueError(
                f"El catálogo no contiene {sorted(required_fields)}: "
                f"{reader.fieldnames}"
            )

        for row_number, row in enumerate(reader, start=2):
            code = (row.get("municipio_codigo") or "").strip()
            name = (row.get("municipio_oficial") or "").strip()
            if not re.fullmatch(r"\d{5}", code):
                raise ValueError(
                    f"Código municipal inválido en la fila {row_number}: {code!r}"
                )
            key = normalize_name(name)
            if not key:
                raise ValueError(
                    f"Nombre municipal vacío en la fila {row_number}, código {code}"
                )
            if key in municipalities:
                raise ValueError(f"Nombre municipal ambiguo en el catálogo: {name}")
            municipalities[key] = code

    if not municipalities:
        raise ValueError("El catálogo no contiene municipios.")
    return municipalities


def prepare_snapshot(
    source_path: Path,
    snapshot_date: str,
    municipalities: dict[str, str],
) -> tuple[Path, list[dict[str, str]], list[str]]:
    if not source_path.is_file():
        raise FileNotFoundError(f"No se encuentra el CSV de Etxebide: {source_path}")

    with source_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not REQUIRED_SOURCE_FIELDS.issubset(
            reader.fieldnames
        ):
            raise ValueError(
                f"{source_path.name} no contiene los campos requeridos "
                f"{sorted(REQUIRED_SOURCE_FIELDS)}: {reader.fieldnames}"
            )
        source_fields = reader.fieldnames
        records: list[dict[str, str]] = []
        seen_keys: set[tuple[str, str, str]] = set()

        for row_number, row in enumerate(reader, start=2):
            name = (row.get("Municipio") or "").strip()
            key = MUNICIPALITY_ALIASES.get(normalize_name(name), normalize_name(name))
            code = municipalities.get(key)
            if code is None:
                raise ValueError(
                    f"Municipio sin correspondencia en {source_path.name}, "
                    f"fila {row_number}: {name!r}"
                )

            group = (row.get("Grupo") or "").strip()
            literal = (row.get("Literal") or "").strip()
            observation_key = (code, group, literal)
            if not group or not literal or observation_key in seen_keys:
                raise ValueError(
                    f"Clave municipal/grupo/categoría vacía o duplicada en "
                    f"{source_path.name}, fila {row_number}: {observation_key!r}"
                )
            seen_keys.add(observation_key)

            row["Municipio"] = name
            row["municipio_codigo"] = code
            row["fecha_fotografia"] = snapshot_date
            records.append(row)

    if len(records) != 8_085 or len({row["municipio_codigo"] for row in records}) != 245:
        raise ValueError(
            f"{source_path.name}: se esperaban 8.085 filas y 245 municipios; "
            f"se obtuvieron {len(records)} filas y "
            f"{len({row['municipio_codigo'] for row in records})} municipios"
        )

    output_fields = ["municipio_codigo", "fecha_fotografia", *source_fields]
    return (
        OUTPUT_ROOT / source_path.name.replace("_limpio.csv", "_con_codigo.csv"),
        records,
        output_fields,
    )


def write_outputs(
    outputs: list[tuple[Path, list[dict[str, str]], list[str]]],
    *,
    overwrite: bool,
) -> None:
    existing = [path for path, _, _ in outputs if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Ya existen resultados; no se sobrescribirán sin --sobrescribir: "
            + ", ".join(str(path) for path in existing)
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_paths: list[Path] = []
    try:
        for _, records, fieldnames in outputs:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="",
                dir=OUTPUT_ROOT,
                prefix=".etxebide_",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                temporary_paths.append(temporary_path)
                writer = csv.DictWriter(
                    output,
                    fieldnames=fieldnames,
                    extrasaction="raise",
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(records)

        for temporary_path, (target, _, _) in zip(temporary_paths, outputs):
            os.replace(temporary_path, target)
    finally:
        for temporary_path in temporary_paths:
            if temporary_path.exists():
                temporary_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Añade códigos municipales a las fotografías limpias de Etxebide "
            "sin modificar las fuentes."
        )
    )
    parser.add_argument(
        "--sobrescribir",
        action="store_true",
        help="Permite sustituir explícitamente los CSV procesados existentes.",
    )
    args = parser.parse_args()

    try:
        municipalities = load_catalog(CATALOG_PATH)
        outputs = [
            prepare_snapshot(SOURCE_ROOT / source_name, snapshot_date, municipalities)
            for source_name, snapshot_date in SNAPSHOTS
        ]
        if {row["municipio_codigo"] for row in outputs[0][1]} != {
            row["municipio_codigo"] for row in outputs[1][1]
        }:
            raise ValueError("Las fotografías de Etxebide no cubren los mismos municipios.")

        write_outputs(outputs, overwrite=args.sobrescribir)
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    for path, records, _ in outputs:
        print(
            f"{path.relative_to(PROJECT_ROOT)}: {len(records)} registros; "
            f"{len({row['municipio_codigo'] for row in records})} municipios; "
            f"{sum(row['Total_estado'] != 'disponible' for row in records)} "
            "valores de Total suprimidos o no disponibles."
        )
    print("Equivalencia aplicada: Donostia -> Donostia / San Sebastián (código 20069).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pymongo import MongoClient

try:
    from .config import BASE_DIR, DB_NAME, MONGO_URI
    from .importar_datos import import_collection
except ImportError:  # pragma: no cover
    from config import BASE_DIR, DB_NAME, MONGO_URI
    from importar_datos import import_collection


SOURCE_FILES = {
    Path("DatosAlvaro", "Salario", "remuMedia.csv"): "salarios",
    Path("DatosAlvaro", "Salario", "iovj-empleo-economico.csv"): (
        "indicadores_laborales"
    ),
}


def load_regional_salary_sources(
    client: MongoClient | None,
    *,
    database_name: str = DB_NAME,
    dry_run: bool = False,
    batch_size: int = 1000,
) -> list[dict[str, Any]]:
    if batch_size <= 0:
        raise ValueError("El tamaño del lote debe ser mayor que cero.")
    if not dry_run and client is None:
        raise ValueError("Se necesita una conexión MongoDB para importar.")

    results = []
    for relative_path, expected_collection in SOURCE_FILES.items():
        source_path = BASE_DIR / relative_path
        if not source_path.is_file():
            raise FileNotFoundError(
                f"No se encuentra la fuente regional: {source_path}"
            )
        result = import_collection(
            client,
            source_path,
            database_name=database_name,
            project_root=BASE_DIR,
            dry_run=dry_run,
            batch_size=batch_size,
        )
        if result["collection"] != expected_collection:
            raise RuntimeError(
                f"{relative_path}: se esperaba la colección "
                f"{expected_collection}, se obtuvo {result['collection']}."
            )
        if result["errores"] or result["registros_transformados"] == 0:
            raise RuntimeError(
                f"No se pudo validar la importación regional de {relative_path}: "
                f"{result['errores']} errores y "
                f"{result['registros_transformados']} registros transformados."
            )
        results.append(result)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Carga solo la remuneración regional y los indicadores salariales "
            "juveniles IOVJ en MongoDB."
        )
    )
    parser.add_argument("--mongo-uri", default=MONGO_URI)
    parser.add_argument("--database", default=DB_NAME)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida y transforma las dos fuentes sin escribir en MongoDB.",
    )
    parser.add_argument("--lote", type=int, default=1000)
    args = parser.parse_args()
    if args.lote <= 0:
        parser.error("--lote debe ser mayor que cero.")

    client: MongoClient | None = None
    try:
        if not args.dry_run:
            client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
        results = load_regional_salary_sources(
            client,
            database_name=args.database,
            dry_run=args.dry_run,
            batch_size=args.lote,
        )
        print(f"Base de destino: {args.database}")
        for result in results:
            print(
                f"{result['archivo']} -> {result['collection']}: "
                f"transformados={result['registros_transformados']}, "
                f"insertados={result['inserciones']}, "
                f"actualizados={result['actualizaciones']}, "
                f"sin_cambios={result['sin_cambios']}."
            )
        if args.dry_run:
            print("Dry-run completado; no se escribió en MongoDB.")
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()

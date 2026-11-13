from __future__ import annotations

import argparse
from typing import Any

from pymongo import MongoClient

try:
    from .config import MONGO_URI
    from .fase3_mongodb import (
        DATABASE_NAME,
        ensure_database_marker,
        load_sources,
        preflight_sources,
        verify_loaded_data,
    )
except ImportError:  # pragma: no cover
    from config import MONGO_URI
    from fase3_mongodb import (
        DATABASE_NAME,
        ensure_database_marker,
        load_sources,
        preflight_sources,
        verify_loaded_data,
    )


def _print_summaries(summaries: list[dict[str, Any]]) -> None:
    for summary in summaries:
        print(
            f"{summary['archivo']} -> {summary['coleccion']}: "
            f"{summary['registros']} registros, "
            f"{summary['municipios']} municipios, "
            f"{summary['sin_codigo_municipal']} sin código."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Carga únicamente los conjuntos canónicos de la fase 3 en una base "
            "MongoDB aislada, sin borrar documentos."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida todas las fuentes sin conectarse ni escribir en MongoDB.",
    )
    parser.add_argument(
        "--lote",
        type=int,
        default=1000,
        help="Operaciones por lote para bulk upsert (por defecto: 1000).",
    )
    args = parser.parse_args()
    if args.lote <= 0:
        parser.error("--lote debe ser mayor que cero.")

    summaries, municipality_codes = preflight_sources()
    print(f"Base de destino: {DATABASE_NAME}")
    _print_summaries(summaries)
    print(f"Códigos de municipio del catálogo: {len(municipality_codes)}")
    if args.dry_run:
        print("Dry-run completado; no se abrió una conexión MongoDB.")
        return

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        database = client[DATABASE_NAME]
        ensure_database_marker(database)
        results = load_sources(database, batch_size=args.lote)
        verify_loaded_data(database, summaries, municipality_codes)
        print("Carga y validación MongoDB completadas.")
        for source_file, result in results.items():
            print(
                f"{source_file}: procesados={result['procesados']}, "
                f"insertados={result['insertados']}, "
                f"actualizados={result['actualizados']}, "
                f"sin_cambios={result['sin_cambios']}."
            )
        print("Recuento final de colecciones:")
        for collection_name in sorted(
            {summary["coleccion"] for summary in summaries}
        ):
            print(
                f"{collection_name}: "
                f"{database[collection_name].count_documents({})}"
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()

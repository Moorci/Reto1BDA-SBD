from __future__ import annotations

import argparse
from typing import Any, Dict, Iterable, List

from pymongo import MongoClient

try:
    from .config import DB_NAME, MONGO_URI
except ImportError:  # pragma: no cover
    from config import DB_NAME, MONGO_URI


def get_client(uri: str | None = None) -> MongoClient:
    return MongoClient(uri or MONGO_URI, serverSelectionTimeoutMS=3000)


def get_db(uri: str | None = None, database: str | None = None):
    client = get_client(uri)
    return client[database or DB_NAME]


def listar_colecciones(uri: str | None = None, database: str | None = None) -> list[str]:
    db = get_db(uri, database)
    return sorted(db.list_collection_names())


def contar_documentos(collection_name: str, uri: str | None = None, database: str | None = None) -> int:
    db = get_db(uri, database)
    return db[collection_name].count_documents({})


def buscar_por_municipio(
    collection_name: str,
    municipio: str,
    limit: int = 10,
    uri: str | None = None,
    database: str | None = None,
) -> list[dict]:
    db = get_db(uri, database)
    return list(db[collection_name].find({"municipio": {"$regex": municipio, "$options": "i"}}).limit(limit))


def ultimo_registro(collection_name: str, uri: str | None = None, database: str | None = None) -> dict | None:
    db = get_db(uri, database)
    return db[collection_name].find_one({}, sort=[("_imported_at", -1)])


def mostrar_estadisticas(uri: str | None = None, database: str | None = None) -> Dict[str, Any]:
    db = get_db(uri, database)
    colecciones = db.list_collection_names()
    stats: Dict[str, Any] = {"database": database or DB_NAME, "colecciones": []}
    for nombre in colecciones:
        collection = db[nombre]
        stats["colecciones"].append({
            "nombre": nombre,
            "documentos": collection.count_documents({}),
            "indice_source_id": "_source_id" in [idx["key"].get("_source_id") for idx in collection.list_indexes() if idx.get("key")],
        })
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Consultas rápidas sobre MongoDB para el proyecto de vivienda y salarios.")
    parser.add_argument("--mongo-uri", default=MONGO_URI, help="URI completa de MongoDB")
    parser.add_argument("--database", default=DB_NAME, help="Base de datos")
    parser.add_argument("--coleccion", default="salarios")
    parser.add_argument("--municipio", default="")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    try:
        if args.municipio:
            docs = buscar_por_municipio(args.coleccion, args.municipio, limit=args.limit, uri=args.mongo_uri, database=args.database)
            print(docs[: args.limit])
            return

        print("Colecciones:", listar_colecciones(args.mongo_uri, args.database))
        print("Estadísticas:", mostrar_estadisticas(args.mongo_uri, args.database))
        print("Último registro:", ultimo_registro(args.coleccion, args.mongo_uri, args.database))
    except Exception as exc:
        print(f"No se pudo consultar MongoDB: {exc}")


if __name__ == "__main__":
    main()

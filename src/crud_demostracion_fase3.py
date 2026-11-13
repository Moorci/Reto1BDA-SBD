from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import uuid

from pymongo import MongoClient
from pymongo.collection import Collection

try:
    from .config import MONGO_URI
    from .fase3_mongodb import DATABASE_NAME
except ImportError:  # pragma: no cover
    from config import MONGO_URI
    from fase3_mongodb import DATABASE_NAME


def _atomic_increment_counter(
    collection: Collection,
    document_id: str,
    *,
    increments: int,
    workers: int,
) -> int:
    if increments <= 0 or workers <= 0:
        raise ValueError("Los incrementos y trabajadores deben ser mayores que cero.")

    def increment(_: int) -> None:
        result = collection.update_one(
            {"_id": document_id},
            {"$inc": {"contador": 1}},
        )
        if result.matched_count != 1:
            raise RuntimeError("No se encontró el documento para el incremento atómico.")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(increment, range(increments)))

    document = collection.find_one({"_id": document_id}, {"contador": 1})
    if document is None:
        raise RuntimeError("No se encontró el documento tras los incrementos.")
    return document.get("contador", 0)


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        database = client[DATABASE_NAME]
        marker = database["_metadata"].find_one({"_id": "fase3_schema"})
        if marker is None or marker.get("version") != 1:
            raise RuntimeError(
                "La base aislada de fase 3 no está inicializada; ejecuta primero "
                "cargar_mongodb_fase3.py."
            )

        collection = database["crud_demostracion"]
        document_id = f"crud-demo:{uuid.uuid4()}"
        inserted = False
        try:
            insert_result = collection.insert_one(
                {
                    "_id": document_id,
                    "municipio_codigo": "01001",
                    "estado": "insertado",
                    "detalle": {"fuente": "demostracion"},
                    "contador": 0,
                }
            )
            inserted = insert_result.inserted_id == document_id
            if not inserted:
                raise RuntimeError("MongoDB no confirmó la inserción de prueba.")

            found = collection.find_one({"_id": document_id})
            if found is None or found.get("estado") != "insertado":
                raise RuntimeError("Find no devolvió el documento insertado.")

            update_result = collection.update_one(
                {"_id": document_id},
                {
                    "$set": {
                        "estado": "actualizado",
                        "detalle.resultado": "CRUD verificado",
                    }
                },
            )
            if update_result.modified_count != 1:
                raise RuntimeError("Update no modificó exactamente un documento.")

            updated = collection.find_one({"_id": document_id})
            if (
                updated is None
                or updated.get("estado") != "actualizado"
                or updated.get("detalle", {}).get("resultado") != "CRUD verificado"
            ):
                raise RuntimeError("Find no verificó el documento actualizado.")

            counter = _atomic_increment_counter(
                collection,
                document_id,
                increments=200,
                workers=8,
            )
            if counter != 200:
                raise RuntimeError(
                    f"El contador atómico debería ser 200, pero se obtuvo {counter}."
                )
            print(
                "Consistencia verificada: 200 incrementos concurrentes "
                "atómicos en un documento."
            )

            delete_result = collection.delete_one({"_id": document_id})
            if delete_result.deleted_count != 1:
                raise RuntimeError("Delete no eliminó exactamente el documento de prueba.")
            if collection.find_one({"_id": document_id}) is not None:
                raise RuntimeError("El documento de prueba sigue presente tras Delete.")

            print("CRUD verificado: Insert, Find, Update y Delete.")
            print(f"Documento temporal eliminado: {document_id}")
        finally:
            if inserted:
                collection.delete_one({"_id": document_id})
    finally:
        client.close()


if __name__ == "__main__":
    main()

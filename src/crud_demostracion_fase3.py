from __future__ import annotations

import uuid

from pymongo import MongoClient

try:
    from .config import MONGO_URI
    from .fase3_mongodb import DATABASE_NAME
except ImportError:  # pragma: no cover
    from config import MONGO_URI
    from fase3_mongodb import DATABASE_NAME


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

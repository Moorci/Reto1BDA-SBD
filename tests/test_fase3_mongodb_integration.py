from __future__ import annotations

import unittest
import uuid

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src.config import MONGO_URI
from src.crud_demostracion_fase3 import _atomic_increment_counter
from src.fase3_mongodb import DATABASE_NAME


class MongoDBConsistencyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
        try:
            cls.client.admin.command("ping")
        except PyMongoError as error:
            cls.client.close()
            raise unittest.SkipTest(
                f"MongoDB de integración no disponible ({type(error).__name__})."
            ) from error

        cls.database = cls.client[DATABASE_NAME]
        if "crud_demostracion" not in cls.database.list_collection_names():
            cls.client.close()
            raise unittest.SkipTest(
                "La base de Fase 3 no tiene la colección CRUD de demostración."
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_concurrent_atomic_increments_preserve_the_exact_total(self) -> None:
        collection = self.database["crud_demostracion"]
        document_id = f"atomic-test:{uuid.uuid4()}"
        increments = 200
        collection.insert_one({"_id": document_id, "contador": 0})
        try:
            result = _atomic_increment_counter(
                collection,
                document_id,
                increments=increments,
                workers=8,
            )
            self.assertEqual(result, increments)
        finally:
            collection.delete_one({"_id": document_id})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.fase3_mongodb import (
    ALLOWED_COLLECTIONS,
    CANONICAL_COLLECTIONS,
    SourceSpec,
    ensure_database_marker,
    prepare_document,
)
from src.importar_datos import choose_collection, discover_data_files


class FakeMarkerCollection:
    def __init__(self, marker: dict | None) -> None:
        self.marker = marker
        self.find_calls = 0
        self.inserted: list[dict] = []

    def find_one(self, query: dict) -> dict | None:
        self.find_calls += 1
        return self.marker

    def insert_one(self, document: dict) -> None:
        self.inserted.append(document)


class FakeDatabase:
    def __init__(self, names: set[str], marker: dict | None) -> None:
        self.names = set(names)
        self.marker_collection = FakeMarkerCollection(marker)

    def list_collection_names(self) -> list[str]:
        return sorted(self.names)

    def __getitem__(self, name: str) -> FakeMarkerCollection:
        if name != "_metadata":
            raise AssertionError(f"Acceso inesperado a colección: {name}")
        return self.marker_collection


class Fase3MongoDBTests(unittest.TestCase):
    def test_marker_accepts_canonical_and_stream_collections_without_writes(self) -> None:
        names = set(CANONICAL_COLLECTIONS) | {
            "_metadata",
            "crud_demostracion",
            "anuncios_stream_fase5",
        }
        marker = {"_id": "fase3_schema", "version": 1}
        database = FakeDatabase(names, marker)

        ensure_database_marker(database)

        self.assertTrue(CANONICAL_COLLECTIONS.issubset(ALLOWED_COLLECTIONS))
        self.assertIn("anuncios_stream_fase5", ALLOWED_COLLECTIONS)
        self.assertEqual(database.names, names)
        self.assertEqual(database.marker_collection.inserted, [])

    def test_marker_rejects_unknown_collection_without_modifying_database(self) -> None:
        names = set(CANONICAL_COLLECTIONS) | {
            "_metadata",
            "anuncios_stream_fase5",
            "coleccion_desconocida",
        }
        database = FakeDatabase(names, {"_id": "fase3_schema", "version": 1})

        with self.assertRaisesRegex(RuntimeError, "coleccion_desconocida"):
            ensure_database_marker(database)

        self.assertEqual(database.names, names)
        self.assertEqual(database.marker_collection.find_calls, 0)
        self.assertEqual(database.marker_collection.inserted, [])

    def test_eustat_keeps_null_value_and_municipal_code_as_text(self) -> None:
        spec = SourceSpec(
            Path("DatosIker", "procesados", "eustat", "renta_personal_municipal.json"),
            "eustat",
            "renta_personal_eustat",
            "Eustat",
        )
        document = prepare_document(
            spec,
            {
                "municipio_codigo": "01001",
                "municipio": "Alegría-Dulantzi",
                "nivel_geografico": "municipio",
                "indice_observacion": 0,
                "valor": None,
            },
            1,
        )

        self.assertEqual(document["municipio_codigo"], "01001")
        self.assertIsNone(document["valor"])
        self.assertEqual(document["tabla_eustat"], "renta_personal_municipal")

    def test_etxebide_preserves_suppression_status_separately_from_value(self) -> None:
        spec = SourceSpec(
            Path(
                "DatosIker",
                "procesados",
                "etxebide",
                "Demandantes-Etxebide-Municipio-2026-04-01_con_codigo.csv",
            ),
            "etxebide",
            "demanda_vpo",
            "Etxebide",
        )
        document = prepare_document(
            spec,
            {
                "municipio_codigo": "01001",
                "Municipio": "Alegría-Dulantzi",
                "Municipio_bilingue": "Alegría-Dulantzi / Dulantzi",
                "fecha_fotografia": "2026-04-01",
                "Grupo": "CUPO",
                "Literal": "3. Menores de 36 años",
                "Total": "",
                "Total_estado": "s.e. (dato no publicado/suprimido)",
            },
            2,
        )

        self.assertIsNone(document["valores"]["total"])
        self.assertEqual(
            document["estados"]["total"],
            "s.e. (dato no publicado/suprimido)",
        )

    def test_generic_importer_routes_eustat_and_emal_separately(self) -> None:
        eustat_path = Path(
            "DatosIker", "procesados", "eustat", "renta_personal_municipal.json"
        )
        emal_path = Path(
            "DatosIker", "procesados", "emal_alquiler_anual_municipios.json"
        )

        self.assertEqual(
            choose_collection(eustat_path, [{"valor": 1000, "renta": 1000}]),
            "indicadores_economicos",
        )
        self.assertEqual(
            choose_collection(emal_path, [{"renta_mensual_media_eur": 500}]),
            "alquiler_vivienda",
        )

    def test_generic_importer_skips_report_directories(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            processed = (
                root
                / "DatosIker"
                / "procesados"
                / "eustat"
                / "renta_personal_municipal.json"
            )
            report = (
                root
                / "DatosIker"
                / "informes"
                / "investigacion_ingresos_juveniles_eustat.txt"
            )
            processed.parent.mkdir(parents=True)
            report.parent.mkdir(parents=True)
            processed.write_text("[]", encoding="utf-8")
            report.write_text("Informe de investigación.", encoding="utf-8")

            discovered = discover_data_files(root)

            self.assertEqual(discovered, [processed.resolve()])


if __name__ == "__main__":
    unittest.main()

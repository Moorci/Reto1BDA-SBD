from __future__ import annotations

import unittest
from pathlib import Path

from src.fase3_mongodb import SourceSpec, prepare_document
from src.importar_datos import choose_collection


class Fase3MongoDBTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

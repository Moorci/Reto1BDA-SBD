from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.HDFS.productor import _html_exclusion_reason
from src.fase5_streaming import _announcement, _number, _prepare_announcements, _validate_event


class Fase5StreamingTests(unittest.TestCase):
    def test_hdfs_manifest_excludes_test_and_notfound_html(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            test_html = root / "pruebas" / "test.html"
            not_found_html = root / "masiva" / "municipio.html"
            valid_html = root / "masiva" / "valido.html"
            for path in (test_html, not_found_html, valid_html):
                path.parent.mkdir(parents=True, exist_ok=True)
            test_html.write_text("<html>prueba</html>", encoding="utf-8")
            not_found_html.write_text("<html>notFound</html>", encoding="utf-8")
            valid_html.write_text("<html>municipio</html>", encoding="utf-8")

            self.assertEqual(_html_exclusion_reason(test_html, root), "pruebas")
            self.assertEqual(
                _html_exclusion_reason(not_found_html, root), "notFound"
            )
            self.assertIsNone(_html_exclusion_reason(valid_html, root))

    def test_numeric_fields_are_converted_and_empty_values_stay_missing(self) -> None:
        self.assertEqual(_number("1.234,50", "precio_eur"), 1234.5)
        self.assertIsNone(_number("", "precio_eur"))
        with self.assertRaises(ValueError):
            _number("no es un número", "precio_eur")

    def test_announcement_preserves_missing_municipal_code(self) -> None:
        event = _announcement(
            {
                "fecha_extraccion": "2026-10-01",
                "operacion": "alquiler",
                "provincia": "Bizkaia",
                "titulo": "Vivienda",
                "localidad_zona": "Centro",
                "precio_eur": "900",
                "habitaciones": "2",
                "banos": "",
                "metros_m2": "75",
                "precio_m2": "12",
                "url": "https://example.test/anuncio/1",
            },
            2,
            "/user/test/reto1/originales/pisos/pisos_euskadi.csv",
        )

        self.assertEqual(event["precio_eur"], 900)
        self.assertIsNone(event["banos"])
        self.assertNotIn("municipio_codigo", event)
        self.assertEqual(event["tipo_evento"], "reproduccion_historica")
        self.assertEqual(_validate_event(event), event)

    def test_duplicate_urls_are_rejected(self) -> None:
        row = {
            "url": "https://example.test/anuncio/1",
            "precio_eur": "",
            "habitaciones": "",
            "banos": "",
            "metros_m2": "",
            "precio_m2": "",
        }
        with self.assertRaisesRegex(ValueError, "URL duplicada"):
            _prepare_announcements(
                [row, row],
                "/user/test/reto1/originales/pisos/pisos_euskadi.csv",
            )

    def test_event_id_must_match_source_url(self) -> None:
        event = _announcement(
            {
                "url": "https://example.test/anuncio/1",
                "precio_eur": "",
                "habitaciones": "",
                "banos": "",
                "metros_m2": "",
                "precio_m2": "",
            },
            2,
            "/user/test/reto1/originales/pisos/pisos_euskadi.csv",
        )
        event["event_id"] = "invalid"
        with self.assertRaisesRegex(ValueError, "event_id"):
            _validate_event(event)


if __name__ == "__main__":
    unittest.main()

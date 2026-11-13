from __future__ import annotations

import unittest

from src.analisis_fase6 import (
    _grouped_capital_svg,
    _merge_municipal_indicators,
    _municipal_work_income_effort_rows,
    _regional_effort_rows,
    _required_code,
)


class Fase6AnalysisTests(unittest.TestCase):
    def test_merge_uses_text_municipal_codes_and_preserves_missing_sources(self) -> None:
        rows = _merge_municipal_indicators(
            [{"_id": "01002", "nombre": "Amurrio", "territorio_historico": "Álava"}],
            {"01002": {"valor": 12.5, "observaciones": 1}},
            {},
            {"01002": {"valor": 9.2, "alquileres_registrados": 7}},
            {},
            {},
            {},
            {},
            fotocasa_rent_month="2026-10",
            fotocasa_sale_month="2026-10",
            emal_date="2026-03-31",
            pisoscom_date="2026-11-06",
            eustat_period="2024",
        )

        self.assertEqual(rows[0]["municipio_codigo"], "01002")
        self.assertEqual(rows[0]["fotocasa_alquiler_eur_m2"], 12.5)
        self.assertAlmostEqual(rows[0]["fotocasa_emal_diferencia_eur_m2"], 3.3)
        self.assertIsNone(rows[0]["fotocasa_venta_eur_m2"])
        self.assertIsNone(rows[0]["pisoscom_alquiler_mediana_eur_m2"])

    def test_rejects_municipal_codes_that_lost_leading_zeroes(self) -> None:
        with self.assertRaisesRegex(ValueError, "Código municipal inválido"):
            _required_code(1002)

    def test_effort_uses_regional_salary_reference_for_municipal_rent(self) -> None:
        rows = _regional_effort_rows(
            [
                {
                    "_id": "01002",
                    "nombre": "Amurrio",
                    "territorio_historico": "Álava",
                }
            ],
            {
                "01002": {
                    "precio_medio_eur_m2": 10.0,
                    "meses_con_dato": 12,
                    "municipios_serie_identica": 1,
                }
            },
            {
                "periodo": "2024",
                "geografia": "C.A. de Euskadi",
                "remuneracion_neta_media_por_sexo": {
                    "Hombre": 1612.0,
                    "Mujer": 1545.0,
                },
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["municipio_codigo"], "01002")
        self.assertEqual(rows[0]["salario_referencia_geografia"], "C.A. de Euskadi")
        self.assertEqual(rows[0]["alquiler_60m2_estimado_eur_mes"], 600.0)
        self.assertAlmostEqual(rows[0]["esfuerzo_hombres_pct"], 600 / 1612 * 100)
        self.assertAlmostEqual(rows[0]["esfuerzo_mujeres_pct"], 600 / 1545 * 100)

    def test_municipal_effort_uses_emal_annual_rent_and_eustat_work_income(self) -> None:
        rows = _municipal_work_income_effort_rows(
            [
                {
                    "_id": "01002",
                    "nombre": "Amurrio",
                    "territorio_historico": "Álava",
                }
            ],
            {
                "01002": {
                    "valor": 12000,
                    "observaciones": 1,
                }
            },
            {
                "01002": {
                    "renta_mensual_media_eur": 500,
                    "numero_fianzas_depositadas": 80,
                    "observaciones": 1,
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["municipio_codigo"], "01002")
        self.assertEqual(rows[0]["emal_alquiler_anualizado_eur"], 6000)
        self.assertEqual(rows[0]["alquiler_anual_sobre_renta_trabajo_pct"], 50)
        self.assertFalse(rows[0]["eustat_desglose_edad"])

    def test_capital_comparison_svg_has_room_for_legend_and_monthly_units(self) -> None:
        svg = _grouped_capital_svg(
            [
                {
                    "municipio": "Vitoria-Gasteiz",
                    "fotocasa_alquiler_eur_m2": 12.76,
                    "emal_alquiler_registrado_eur_m2": 9.728,
                },
                {
                    "municipio": "Bilbao",
                    "fotocasa_alquiler_eur_m2": 16.87,
                    "emal_alquiler_registrado_eur_m2": 12.202,
                },
                {
                    "municipio": "Donostia / San Sebastián",
                    "fotocasa_alquiler_eur_m2": 18.44,
                    "emal_alquiler_registrado_eur_m2": 14.094,
                },
            ]
        )

        self.assertIn('viewBox="0 0 980 320"', svg)
        self.assertIn("EUR/m²/mes", svg)


if __name__ == "__main__":
    unittest.main()

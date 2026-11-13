from __future__ import annotations

import unittest

from src.consultas_fase4 import pipeline_specs, query_specs


class Fase4QueryTests(unittest.TestCase):
    def test_defines_five_useful_queries_including_nested_and_compound_filters(self) -> None:
        queries = query_specs()

        self.assertEqual(len(queries), 5)
        self.assertIn("$and", queries["Q2_anuncios_venta_con_limites"]["filter"])
        self.assertIn(
            "valores.total",
            queries["Q5_demanda_vpo_menores_36"]["filter"],
        )
        self.assertIn("estados.total", queries["Q5_demanda_vpo_menores_36"]["filter"])
        self.assertTrue(all(query["projection"] and query["sort"] for query in queries.values()))

    def test_aggregation_pipelines_use_group_and_lookup_or_unwind(self) -> None:
        pipelines = pipeline_specs()
        all_stages = {
            stage_name
            for _, pipeline in pipelines.values()
            for stage in pipeline
            for stage_name in stage
        }

        self.assertEqual(len(pipelines), 3)
        self.assertIn("$group", all_stages)
        self.assertTrue({"$lookup", "$unwind"}.issubset(all_stages))
        self.assertTrue({"$match", "$project", "$sort"}.issubset(all_stages))


if __name__ == "__main__":
    unittest.main()

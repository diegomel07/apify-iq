import unittest
import pandas as pd
from enrich_graduates import normalize_text, parse_names, score_candidate


class TestEnrichGraduates(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("Sebastián Páez Rojas"), "sebastian paez rojas")
        self.assertEqual(normalize_text("INGENIERÍA QUÍMICA"), "ingenieria quimica")
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text(""), "")

    def test_parse_names_iq(self):
        row = pd.Series({"Nombres": "SEBASTIAN", "Apellidos_1": "Paez", "Apellidos_2": "Rojas"})
        first, full_last, first_last = parse_names(row, "IQ")
        self.assertEqual(first, "SEBASTIAN")
        self.assertEqual(full_last, "Paez Rojas")
        self.assertEqual(first_last, "Paez")

    def test_parse_names_miq(self):
        row = pd.Series({"Nombres": "Angela Aurora", "Apellidos": "Beltrán Osuna"})
        first, full_last, first_last = parse_names(row, "MIQ")
        self.assertEqual(first, "Angela Aurora")
        self.assertEqual(full_last, "Beltrán Osuna")
        self.assertEqual(first_last, "Beltrán")

    def test_score_candidate_exact_match(self):
        candidate = {
            "firstName": "Sebastian",
            "lastName": "Paez Rojas",
            "headline": "Ingeniero Químico | Investigación y Desarrollo",
            "education": [
                {
                    "schoolName": "Universidad Nacional de Colombia",
                    "degree": "Ingeniería Química",
                    "fieldOfStudy": "Facultad de Ingeniería",
                }
            ],
        }
        score, reasons = score_candidate(candidate, "SEBASTIAN", "Paez Rojas", "IQ")
        # Debería obtener puntaje alto (>= 70)
        self.assertGreaterEqual(score, 70)
        self.assertTrue(any("UNAL" in r for r in reasons))
        self.assertTrue(any("Química" in r for r in reasons))

    def test_score_candidate_wrong_person(self):
        candidate = {
            "firstName": "Carlos",
            "lastName": "Gomez",
            "headline": "Diseñador Gráfico",
            "education": [
                {
                    "schoolName": "Universidad de los Andes",
                    "degree": "Diseño",
                }
            ],
        }
        score, _ = score_candidate(candidate, "SEBASTIAN", "Paez Rojas", "IQ")
        self.assertLess(score, 30)


if __name__ == "__main__":
    unittest.main()

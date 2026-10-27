import unittest

class TestEvidenceContract(unittest.TestCase):
    """
    Test suite specifying the evidence contract and nutrient normalization rules:
    - Normalization of label variants (Gordura, Cinza, Fibra, etc.)
    - No default-filling / imputation of missing nutrients
    - Carbs-by-difference requires protein, fat, moisture, ash, fiber
    - Dry matter conversion requires moisture
    - Taurine units distinction (% vs mg/kg)
    - Field status tracking (valid, missing, invalid, conflicting)
    """

    def test_imputation_is_rejected_when_nutrients_missing(self):
        """When moisture is missing, carbs_nfe and dry-matter conversions must be None, not default-filled."""
        # This will test our new evidence parser
        from src.scoring.evidence import normalize_nutrients, FieldStatus

        raw_text = "Proteína bruta 10.0% Gordura bruta 5.0% Fibra bruta 0.5% Cinza bruta 2.0%"
        # Notice: moisture is missing!
        parsed = normalize_nutrients(raw_text, category='wet')

        self.assertEqual(parsed['protein']['value'], 10.0)
        self.assertEqual(parsed['moisture']['status'], FieldStatus.MISSING)
        self.assertIsNone(parsed['moisture']['value'])
        
        # Dry matter percentage and carbs must be None because moisture is absent
        self.assertIsNone(parsed['dm_pct'])
        self.assertIsNone(parsed['protein_dmb'])
        self.assertIsNone(parsed['carbs_nfe'])
        self.assertIsNone(parsed['carbs_dmb'])

    def test_complete_analytical_constituents_calculation(self):
        """When all 5 macro nutrients are present, carbs and DMB are calculated accurately."""
        from src.scoring.evidence import normalize_nutrients, FieldStatus

        raw_text = "Proteína bruta 11,0 %; Matéria gorda bruta 6,0 %; Fibra bruta 0,5 %; Cinza bruta 2,0 %; Humidade 80,0 %."
        parsed = normalize_nutrients(raw_text, category='wet')

        self.assertEqual(parsed['protein']['value'], 11.0)
        self.assertEqual(parsed['fat']['value'], 6.0)
        self.assertEqual(parsed['fiber']['value'], 0.5)
        self.assertEqual(parsed['ash']['value'], 2.0)
        self.assertEqual(parsed['moisture']['value'], 80.0)

        self.assertEqual(parsed['dm_pct'], 20.0)
        self.assertEqual(parsed['protein_dmb'], 55.0)
        # Carbs: 100 - (11 + 6 + 0.5 + 2 + 80) = 0.5
        self.assertEqual(parsed['carbs_nfe'], 0.5)
        # Carbs DMB: (0.5 / 20) * 100 = 2.5
        self.assertEqual(parsed['carbs_dmb'], 2.5)

    def test_impossible_nutrient_total_is_marked_invalid(self):
        """If sum of constituents exceeds 100% (+ allowance), it must be flagged as invalid."""
        from src.scoring.evidence import normalize_nutrients, FieldStatus

        # Sum = 60 + 40 + 20 = 120% > 100%
        raw_text = "Proteína 60.0% Gordura 40.0% Humidade 20.0%"
        parsed = normalize_nutrients(raw_text, category='dry')
        self.assertEqual(parsed['status'], FieldStatus.INVALID)
        self.assertIsNone(parsed['carbs_nfe'])

    def test_taurine_units_handling(self):
        """Taurine in mg/kg vs % must be preserved without confusing 0.2% with 0.2 mg/kg."""
        from src.scoring.evidence import normalize_nutrients

        text_mg = "Taurina 1500 mg/kg"
        p_mg = normalize_nutrients(text_mg, category='wet')
        self.assertEqual(p_mg['taurine']['value'], 1500.0)
        self.assertEqual(p_mg['taurine']['unit'], 'mg/kg')

        text_pct = "Taurina 0.2%"
        p_pct = normalize_nutrients(text_pct, category='wet')
        self.assertEqual(p_pct['taurine']['value'], 0.2)
        self.assertEqual(p_pct['taurine']['unit'], '%')

    def test_scoring_readiness_gate(self):
        """A product missing essential analytical data or composition cannot be ranked."""
        from src.scoring.evidence import check_scoring_readiness

        # Product with valid composition and all analytical constituents
        ready_product = {
            'ingredients': '70% de carne de frango, 20% caldo, minerais',
            'nutrition_raw': 'Proteína: 10.5% Gordura: 6.0% Cinza: 2.0% Fibra: 0.5% Humidade: 80.0%',
            'classification': 'complete'
        }
        is_ready, reasons = check_scoring_readiness(ready_product, category='wet')
        self.assertTrue(is_ready)
        self.assertEqual(reasons, [])

        # Missing moisture and incomplete composition
        unready_product = {
            'ingredients': '',
            'nutrition_raw': 'Proteína: 10.5% Gordura: 6.0%',
            'classification': 'unknown'
        }
        is_ready2, reasons2 = check_scoring_readiness(unready_product, category='wet')
        self.assertFalse(is_ready2)
        self.assertIn('missing_composition', reasons2)
        self.assertIn('missing_analytical_constituents', reasons2)

if __name__ == '__main__':
    unittest.main()

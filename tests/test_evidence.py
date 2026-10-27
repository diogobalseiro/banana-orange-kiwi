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

    def test_dry_food_without_declared_moisture_does_not_impute(self):
        """Dry food carb calculation must not substitute 8% when moisture is undeclared."""
        from src.scoring.evidence import normalize_nutrients, FieldStatus

        raw_text = "Proteína 32.0% Gordura 15.0% Fibra 3.0% Cinza 7.0%"
        parsed = normalize_nutrients(raw_text, category='dry')
        self.assertIsNone(parsed['moisture']['value'])
        self.assertEqual(parsed['moisture']['status'], FieldStatus.MISSING)
        # Without declared moisture, carbs cannot be calculated
        self.assertIsNone(parsed['carbs_nfe'])

    def test_label_synonyms(self):
        """Synonyms like Matéria gorda bruta, Matéria inorgânica, and Matéria fibrosa are recognized."""
        from src.scoring.evidence import normalize_nutrients

        raw_text = "Proteína bruta 30% Matéria gorda bruta 12% Matéria fibrosa 2.5% Matéria inorgânica 6.5% Teor de humidade 9%"
        parsed = normalize_nutrients(raw_text, category='dry')
        self.assertEqual(parsed['protein']['value'], 30.0)
        self.assertEqual(parsed['fat']['value'], 12.0)
        self.assertEqual(parsed['fiber']['value'], 2.5)
        self.assertEqual(parsed['ash']['value'], 6.5)
        self.assertEqual(parsed['moisture']['value'], 9.0)
        self.assertEqual(parsed['carbs_nfe'], 40.0)

    def test_extract_total_meat_percentage(self):
        """extract_total_meat_percentage correctly parses and sums meat percentages."""
        from src.scoring.evidence import extract_total_meat_percentage

        # Case 1: Suffix percentage with adjectives
        acana = "Frango fresco (19%), frango desidratado (13%), arenque desidratado (13%), Peru desidratado (5%)"
        self.assertEqual(extract_total_meat_percentage(acana), 50)

        # Case 2: Explicit overall percentage
        feringa = "70% aves (frango 40%, peru 30%), 28.5% caldo, 1% minerais"
        self.assertEqual(extract_total_meat_percentage(feringa), 70)

        # Case 3: Token 4% trick
        felix = "Carnes e subprodutos animais (dos quais 4% vitela), substâncias minerais"
        self.assertEqual(extract_total_meat_percentage(felix), 4)

    def test_extract_first_ingredient(self):
        """extract_first_ingredient strips preambles and respects parenthetical nesting."""
        from src.scoring.evidence import extract_first_ingredient

        raw = "Alimento completo para gatinhos Composição: com frango: carne e subprodutos animais (20% aves, 20% frango), peixe"
        self.assertEqual(extract_first_ingredient(raw), "carne e subprodutos animais (20% aves, 20% frango)")

        dry = "Frango fresco (19%), frango desidratado (13%)"
        self.assertEqual(extract_first_ingredient(dry), "Frango fresco (19%)")

    def test_minified_keys_include_protein_and_fat(self):
        """Both wet and dry scorers must provide prot and fat in minified dict for UI display."""
        from src.scoring.dry_scorer import score_dry_product
        from src.scoring.wet_scorer import score_wet_product

        dry_p = {
            'pid': 'd1', 'name': 'Dry Test', 'brand': 'BrandX', 'price': 10.0, 'unit_price_kg': 5.0,
            'ingredients': 'Frango fresco (30%), arroz (20%)',
            'nutrition_raw': 'Proteína 32.0% Gordura 14.0% Fibra 2.5% Cinza 7.0%'
        }
        _, dry_mini = score_dry_product(dry_p)
        self.assertEqual(dry_mini['prot'], 32.0)
        self.assertEqual(dry_mini['fat'], 14.0)
        self.assertIn('(Est.)', dry_mini['cb'])

        wet_p = {
            'pid': 'w1', 'name': 'Wet Test Completo', 'brand': 'BrandX', 'price': 1.0, 'unit_price_kg': 10.0,
            'description': 'Alimento completo para gatos',
            'ingredients': 'Frango 70%, caldo 28%',
            'nutrition_raw': 'Proteína 10.0% Gordura 5.0% Fibra 0.5% Cinza 2.0% Humidade 80.0%'
        }
        _, wet_mini = score_wet_product(wet_p)
        self.assertEqual(wet_mini['prot'], 10.0)
        self.assertEqual(wet_mini['fat'], 5.0)

if __name__ == '__main__':
    unittest.main()

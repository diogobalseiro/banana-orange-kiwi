import unittest
from src.scoring.wet_scorer import score_wet_product
from src.scoring.dry_scorer import score_dry_product

class TestScoringReadiness(unittest.TestCase):
    def test_wet_product_with_missing_moisture_is_unranked(self):
        """Wet food missing analytical constituents cannot receive a ranked score."""
        p = {
            'pid': 'test-1',
            'name': 'Comida Húmida Gato Frango',
            'brand': 'TestBrand',
            'price': 1.0,
            'unit_price_kg': 10.0,
            'ingredients': 'Carnes e derivados (85% frango)',
            'nutrition_raw': 'Proteína: 10.0% Gordura: 5.0%' # missing moisture, ash, fiber
        }
        full, mini = score_wet_product(p)
        self.assertIsNotNone(full)
        self.assertIsNotNone(mini)
        self.assertFalse(full['is_ranked'])
        self.assertIsNone(full['score'])
        self.assertIsNone(full['value_ratio'])
        self.assertIn('missing_analytical_constituents', full['unranked_reasons'])
        self.assertIsNone(mini['s'])
        self.assertIsNone(mini['vr'])

    def test_wet_product_with_missing_composition_does_not_earn_free_from_claims(self):
        """Unknown composition must have has_sugar=None, not False, so it cannot earn a free-from claim."""
        p = {
            'pid': 'test-2',
            'name': 'Comida Húmida Gato',
            'brand': 'TestBrand',
            'price': 1.0,
            'unit_price_kg': 10.0,
            'ingredients': '', # Missing composition
            'nutrition_raw': 'Proteína: 10.0% Gordura: 5.0% Humidade: 80.0% Cinza: 2.0% Fibra: 0.5%'
        }
        full, mini = score_wet_product(p)
        self.assertFalse(full['is_ranked'])
        self.assertIsNone(full['score'])
        self.assertIsNone(full['has_sugar'])
        self.assertIsNone(full['has_grains'])
        self.assertIsNone(mini['sug'])

    def test_complementary_wet_food_is_retained_as_unranked(self):
        """Complementary wet food is no longer dropped as None; it is retained with unranked status."""
        p = {
            'pid': 'test-3',
            'name': 'Alimento Complementar Sopa Frango',
            'brand': 'TestBrand',
            'price': 1.2,
            'unit_price_kg': 12.0,
            'ingredients': 'Caldo de frango 90%, frango 10%',
            'nutrition_raw': 'Proteína: 5.0% Gordura: 0.5% Humidade: 92.0% Cinza: 1.0% Fibra: 0.1%'
        }
        full, mini = score_wet_product(p)
        self.assertIsNotNone(full)
        self.assertFalse(full['is_ranked'])
        self.assertIsNone(full['score'])
        self.assertEqual(full['classification'], 'Complementar')
        self.assertIn('complementary_food_excluded', full['unranked_reasons'])

    def test_dry_product_missing_moisture_does_not_impute_carbs(self):
        """Dry food missing moisture must have carbs=None and be unranked."""
        p = {
            'pid': 'test-4',
            'name': 'Ração Seca Gato Adulto',
            'brand': 'TestBrand',
            'price': 15.0,
            'unit_price_kg': 5.0,
            'ingredients': 'Frango desidratado 40%, arroz 20%',
            'nutrition_raw': 'Proteína: 32.0% Gordura: 14.0% Fibra: 2.5% Cinza: 7.0%' # missing moisture
        }
        full, mini = score_dry_product(p)
        self.assertFalse(full['is_ranked'])
        self.assertIsNone(full['score'])
        self.assertIsNone(full['nutrition_parsed']['carbs_nfe'])
        self.assertIsNone(mini['carb'])

    def test_valid_dry_product_receives_score(self):
        """A complete dry product with verified composition and all 5 macros is ranked."""
        p = {
            'pid': 'test-5',
            'name': 'Ração Seca Gato Adulto Frango',
            'brand': 'TestBrand',
            'price': 15.0,
            'unit_price_kg': 5.0,
            'ingredients': 'Frango fresco 30%, frango desidratado 25%, ervilhas, gordura de frango',
            'nutrition_raw': 'Proteína: 38.0% Gordura: 18.0% Humidade: 8.0% Fibra: 2.5% Cinza: 7.5%'
        }
        full, mini = score_dry_product(p)
        self.assertTrue(full['is_ranked'])
        self.assertIsNotNone(full['score'])
        self.assertGreater(full['score'], 0)
        self.assertIsNotNone(full['value_ratio'])
        self.assertEqual(full['nutrition_parsed']['carbs_nfe'], 26.0)

if __name__ == '__main__':
    unittest.main()

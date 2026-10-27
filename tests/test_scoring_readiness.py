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

    def test_complementary_wet_food_is_excluded_entirely(self):
        """Complementary wet food (snacks, soups, toppers) is excluded entirely from the complete-food catalog."""
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
        self.assertIsNone(full)
        self.assertIsNone(mini)

    def test_dry_product_with_declared_macros_is_ranked_without_optional_moisture(self):
        """Under EU Reg 767/2009, dry food with protein, fat, fibre, ash is ranked with standard moisture allowance."""
        p = {
            'pid': 'test-4',
            'name': 'Ração Seca Gato Adulto',
            'brand': 'TestBrand',
            'price': 15.0,
            'unit_price_kg': 5.0,
            'ingredients': 'Frango desidratado 40%, arroz 20%',
            'nutrition_raw': 'Proteína: 32.0% Gordura: 14.0% Fibra: 2.5% Cinza: 7.0%' # missing moisture (optional <=14%)
        }
        full, mini = score_dry_product(p)
        self.assertTrue(full['is_ranked'])
        self.assertIsNotNone(full['score'])
        self.assertIsNone(full['nutrition_parsed']['carbs_nfe'])
        self.assertEqual(mini['ir'], True)

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

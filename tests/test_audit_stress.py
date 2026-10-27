import unittest
import math
from src.scoring.dry_scorer import score_dry_product
from src.scoring.wet_scorer import score_wet_product
from src.scoring.evidence import (
    normalize_nutrients,
    extract_nutrient_value,
    extract_total_meat_percentage,
    extract_first_ingredient,
    NUTRIENT_PATTERNS
)


class TestEdgeCaseExtraction(unittest.TestCase):
    """Deep extraction robustness tests across regex, punctuation, and Unicode."""

    def test_decimal_commas_and_plural_synonyms(self):
        """Analytical constituents with decimal commas and plural Portuguese terms."""
        raw = "Constituintes: Proteínas brutas 33,5%, Matérias gordas brutas 15,2%, Fibras brutas 2,8%, Cinzas brutas 7,1%, Teor de humidade 8,4%"
        parsed = normalize_nutrients(raw, category='dry')
        self.assertEqual(parsed['protein']['value'], 33.5)
        self.assertEqual(parsed['fat']['value'], 15.2)
        self.assertEqual(parsed['fiber']['value'], 2.8)
        self.assertEqual(parsed['ash']['value'], 7.1)
        self.assertEqual(parsed['moisture']['value'], 8.4)
        # 100 - (33.5 + 15.2 + 2.8 + 7.1 + 8.4) = 100 - 67 = 33.0
        self.assertEqual(parsed['carbs_nfe'], 33.0)

    def test_unicode_non_breaking_spaces(self):
        """Labels with non-breaking spaces (\u00a0 or \u202f) are handled cleanly."""
        raw = "Proteína:\u00a034,0%\u00a0Gordura:\u00a016,0%\u00a0Fibra:\u00a02,0%\u00a0Cinza:\u00a06,5%\u00a0Humidade:\u00a07,5%"
        parsed = normalize_nutrients(raw, category='dry')
        self.assertEqual(parsed['protein']['value'], 34.0)
        self.assertEqual(parsed['fat']['value'], 16.0)

    def test_trailing_unit_guard_prevents_iu_and_mg_backtracking(self):
        """Values followed by non-percent units (UI, mg, kcal) do not trigger false % matches."""
        raw = "Cálcio: 1.2%, Magnésio: 85 mg/kg, Vitamina A: 25000 UI/kg, Vitamina D3: 1500 UI/kg"
        ca = extract_nutrient_value(raw, NUTRIENT_PATTERNS['calcium'])
        self.assertEqual(ca, 1.2)
        mg = extract_nutrient_value(raw, NUTRIENT_PATTERNS['magnesium'])
        # 85 mg/kg must NOT be parsed as 85%
        self.assertIsNone(mg)

    def test_multiple_distinct_meats_summation(self):
        """Sums multiple distinct animal sources accurately."""
        ingr = "Frango desidratado (32%), peru fresco (18%), salmão desidratado (12%), ervilhas, batata"
        meat = extract_total_meat_percentage(ingr)
        self.assertEqual(meat, 62)

    def test_nested_sub_ingredients_double_counting_safeguard(self):
        """Nested percentages 'aves 70% (frango 40%, peru 30%)' must return 70%, not 140%."""
        ingr = "70% aves (frango 40%, peru 30%), 28.5% caldo, 1% minerais"
        meat = extract_total_meat_percentage(ingr)
        self.assertEqual(meat, 70)

    def test_zero_grain_marketing_claim_does_not_flag_has_grains(self):
        """Marketing phrases like '0% cereais' or 'isento de cereais' must not trigger has_grains."""
        p = {
            'pid': 'zero_grain',
            'name': 'Ração Top Meat 0% Cereais',
            'brand': 'PureMeat',
            'price': 20.0,
            'unit_price_kg': 10.0,
            'ingredients': 'Frango fresco 50%, batata desidratada 20%, gordura de frango (0% cereais, sem milho nem trigo)',
            'nutrition_raw': 'Proteína: 38.0% Gordura: 16.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0%'
        }
        full, mini = score_dry_product(p)
        self.assertTrue(full['is_grain_free'])
        self.assertTrue(mini['gf'])


class TestScoringContractsAndClamping(unittest.TestCase):
    """Guarantees score range integrity [10, 95] and demographic specific scoring."""

    def test_score_caps_and_floors(self):
        """Scores cannot exceed 95 or fall below 10."""
        # Product with all negative penalties possible
        horrible = {
            'pid': 'horrible_1',
            'name': 'Ração Baixa Qualidade',
            'brand': 'BadBrand',
            'price': 2.0,
            'unit_price_kg': 1.0,
            'ingredients': 'Milho, trigo, carnes e subprodutos animais, glúten de milho, corantes (óxido de ferro), açúcar, bha, bht',
            'nutrition_raw': 'Proteína: 22.0% Gordura: 8.0% Humidade: 10.0% Fibra: 6.0% Cinza: 10.0%'
        }
        full_h, mini_h = score_dry_product(horrible)
        self.assertEqual(full_h['score'], 10)
        self.assertEqual(mini_h['s'], 10)
        self.assertIn('Tier D', mini_h['t'])

        # Product with all top features
        super_food = {
            'pid': 'super_1',
            'name': 'Super Carnivore Elite',
            'brand': 'ApexPredator',
            'price': 40.0,
            'unit_price_kg': 20.0,
            'ingredients': 'Frango fresco (65%), fígado de frango (5%), coração de frango (5%), óleo de salmão (3%), arando, dl-metionina',
            'nutrition_raw': 'Proteína: 45.0% Gordura: 19.0% Humidade: 8.0% Fibra: 1.5% Cinza: 6.5% Cálcio: 1.2% Fósforo: 1.0% Magnésio: 0.08% Taurina: 2500 mg/kg EPA: 0.3% DHA: 0.3%'
        }
        full_s, mini_s = score_dry_product(super_food)
        self.assertEqual(full_s['score'], 95)
        self.assertEqual(mini_s['s'], 95)
        self.assertIn('Tier S', mini_s['t'])

    def test_fractionation_penalty_triggers(self):
        """Fractionated legume starches trigger -8 penalty."""
        p_frac = {
            'pid': 'fractionated_food',
            'name': 'Ração Grain Free Split',
            'brand': 'StarchSplitter',
            'price': 20.0,
            'unit_price_kg': 10.0,
            'ingredients': 'Frango fresco (35%), amido de ervilha, proteína de ervilha, farinha de batata, lentilhas, gordura de aves',
            'nutrition_raw': 'Proteína: 32.0% Gordura: 14.0% Humidade: 8.0% Fibra: 3.0% Cinza: 7.0%'
        }
        full, mini = score_dry_product(p_frac)
        self.assertTrue(full['is_fractionated'])
        self.assertTrue(mini['fr'])

    def test_non_food_items_excluded(self):
        """Accessories and non-food items returning None, None."""
        accessories = [
            {'pid': 'acc1', 'name': 'Arranhador para Gatos Torre'},
            {'pid': 'acc2', 'name': 'Comedouro Inox para Gato'},
            {'pid': 'acc3', 'name': 'Tapete para Areia de Gato'},
            {'pid': 'acc4', 'name': 'Bebedouro Fonte Automática'},
            {'pid': 'acc5', 'name': 'Brinquedo Rato Peluche Gato'}
        ]
        for acc in accessories:
            f_dry, m_dry = score_dry_product(acc)
            self.assertIsNone(f_dry)
            self.assertIsNone(m_dry)

            f_wet, m_wet = score_wet_product(acc)
            self.assertIsNone(f_wet)
            self.assertIsNone(m_wet)


class TestMinifiedSchemaCompleteness(unittest.TestCase):
    """Ensures minified schemas match the expectations of frontend template.html."""

    def test_dry_minified_schema_keys(self):
        p = {
            'pid': 'schema_dry',
            'name': 'Dry Schema Check',
            'brand': 'CheckBrand',
            'price': 15.0,
            'unit_price_kg': 5.0,
            'ingredients': 'Frango fresco 40%, ervilhas, batata',
            'nutrition_raw': 'Proteína: 34.0% Gordura: 16.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0%'
        }
        _, mini = score_dry_product(p)
        expected_keys = [
            'id', 'n', 'b', 'p', 'pkg', 'fi', 'fresh', 'meat_pct', 'k', 'st',
            't', 's', 'vr', 'ir', 'ur', 'gf', 'grn', 'sug', 'fr', 'cg', 'col', 'tau',
            'omg', 'org', 'prot', 'fat', 'carb', 'cb', 'u', 'r', 'fid', 'rec', 'conf'
        ]
        for key in expected_keys:
            self.assertIn(key, mini, f"Missing key '{key}' in dry minified output")

        # Verify no NaN or Inf values
        for k, v in mini.items():
            if isinstance(v, float):
                self.assertFalse(math.isnan(v), f"Value for '{k}' is NaN")
                self.assertFalse(math.isinf(v), f"Value for '{k}' is Inf")

    def test_wet_minified_schema_keys(self):
        p = {
            'pid': 'schema_wet',
            'name': 'Wet Schema Check',
            'brand': 'CheckBrand',
            'description': 'Alimento completo para gatos',
            'price': 1.5,
            'unit_price_kg': 7.5,
            'ingredients': 'Frango 60%, caldo 38%, minerais 2%',
            'nutrition_raw': 'Proteína: 10.0% Gordura: 5.0% Humidade: 80.0% Fibra: 0.3% Cinza: 2.0%'
        }
        _, mini = score_wet_product(p)
        expected_keys = [
            'id', 'n', 'b', 'p', 'pkg', 'c', 'fi', 'k', 't', 's',
            'vr', 'ir', 'ur', 'sug', 'grn', 'veg', 'org', 'carr', 'tau', 'omg',
            'meat_pct', 'prot', 'fat', 'carb', 'cb', 'u', 'r', 'fid', 'rec', 'conf'
        ]
        for key in expected_keys:
            self.assertIn(key, mini, f"Missing key '{key}' in wet minified output")

        # Verify no NaN or Inf values
        for k, v in mini.items():
            if isinstance(v, float):
                self.assertFalse(math.isnan(v), f"Value for '{k}' is NaN")
                self.assertFalse(math.isinf(v), f"Value for '{k}' is Inf")


class TestPostAuditRefinements(unittest.TestCase):
    """Tests directly verifying fixes from cross-subagent biological code audit."""

    def test_thyme_tomilho_not_confused_with_corn_milho(self):
        """Botanical thyme (tomilho) must not trigger grain penalty or grain-inclusive cap."""
        p = {
            'pid': 'thyme_kibble',
            'name': 'Grain Free Carnivore com Tomilho',
            'brand': 'BotanicalPet',
            'price': 30.0,
            'unit_price_kg': 15.0,
            'ingredients': 'Frango fresco (55%), ervilhas, gordura de aves, tomilho (0.1%), alecrim (0.1%)',
            'nutrition_raw': 'Proteína: 38.0% Gordura: 18.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0%'
        }
        full, mini = score_dry_product(p)
        self.assertTrue(full['is_grain_free'])
        self.assertFalse(full['has_grains'])
        self.assertTrue(mini['gf'])
        self.assertFalse(mini['grn'])
        self.assertGreaterEqual(full['score'], 80)
        self.assertIn('Tier S', mini['t'])

    def test_byproduct_meal_first_ingredient_penalized(self):
        """'Farinha de subprodutos de aves' must be classified as vague (-5), not dehydrated (+14)."""
        p = {
            'pid': 'byproduct_first',
            'name': 'Ração Económica Subprodutos',
            'brand': 'BudgetPet',
            'price': 10.0,
            'unit_price_kg': 5.0,
            'ingredients': 'Farinha de subprodutos de aves (40%), arroz, milho',
            'nutrition_raw': 'Proteína: 30.0% Gordura: 12.0% Humidade: 8.0% Fibra: 3.0% Cinza: 8.0%'
        }
        full, mini = score_dry_product(p)
        self.assertEqual(full['first_ingredient'], 'Farinha de subprodutos de aves (40%)')
        self.assertFalse(mini['fresh'])
        # Must not get the +14 dehydrated bonus
        self.assertLess(full['score'], 55)

    def test_wet_ensopado_not_excluded_as_soup(self):
        """'Ensopado' (stew) in wet food title must not be matched as 'sopa' (soup/complementary)."""
        p = {
            'pid': 'stew_wet',
            'name': 'Hill\'s Prescription Diet Gastrointestinal Biome Ensopado para Gatos',
            'brand': 'Hill\'s Prescription Diet',
            'price': 2.5,
            'unit_price_kg': 20.0,
            'description': 'Alimento composto completo para gatos adultos',
            'ingredients': 'Frango (12%), fígado de porco, amido de arroz, glúten de trigo, minerais',
            'nutrition_raw': 'Proteína: 7.5% Gordura: 4.0% Humidade: 80.0% Fibra: 0.8% Cinza: 1.5%'
        }
        full, mini = score_wet_product(p)
        self.assertIsNotNone(full)
        self.assertIsNotNone(mini)
        self.assertTrue(full['is_ranked'])
        self.assertEqual(full['classification'], 'Completo')

    def test_magnesium_sanity_cap_enforced(self):
        """Lethal magnesium (>0.3%) is rejected by the physical sanity cap."""
        from src.scoring.evidence import extract_nutrient_value, NUTRIENT_PATTERNS
        raw_toxic = "Constituintes: Proteína 30% Gordura 15% Magnésio: 0.8%"
        mg_toxic = extract_nutrient_value(raw_toxic, NUTRIENT_PATTERNS['magnesium'])
        self.assertIsNone(mg_toxic)

        raw_safe = "Constituintes: Proteína 30% Gordura 15% Magnésio: 0.08%"
        mg_safe = extract_nutrient_value(raw_safe, NUTRIENT_PATTERNS['magnesium'])
        self.assertEqual(mg_safe, 0.08)

    def test_decimal_mg_backtracking_prevention(self):
        """'Magnésio: 85.0 mg/kg' must not backtrack to 85.0%."""
        from src.scoring.evidence import extract_nutrient_value, NUTRIENT_PATTERNS
        raw = "Magnésio: 85.0 mg/kg, Cálcio: 1.2%"
        mg = extract_nutrient_value(raw, NUTRIENT_PATTERNS['magnesium'])
        self.assertIsNone(mg)

    def test_meat_summation_distinct_species(self):
        """'40% frango, 30% vaca' sums to 70% rather than short-circuiting at 40%."""
        from src.scoring.evidence import extract_total_meat_percentage
        ingr = "40% frango, 30% vaca, 28.5% caldo, 1.5% minerais"
        meat = extract_total_meat_percentage(ingr)
        self.assertEqual(meat, 70)

    def test_single_protein_validation(self):
        """Pure fish and game single-protein compositions (arenque, sardinha, truta, veado) are valid."""
        from src.scoring.evidence import validate_composition, FieldStatus
        for fish in ['Arenque 95%, abóbora 4%', 'Sardinha 90%, batata-doce 8%', 'Truta 85%, ervilhas 14%', 'Veado 70%, mirtilos 28%']:
            res = validate_composition(fish)
            self.assertEqual(res['status'], FieldStatus.VALID, f"Failed on: {fish}")

    def test_minified_conflict_not_erased(self):
        """A material conflict on a minified product must not be erased during assessment attachment."""
        from src.scoring.reconciliation import attach_shared_assessment
        mock_matches = {
            'form_conflict_test': {
                'description': 'Test Form',
                'brand': 'BrandX',
                'category': 'wet',
                'verified': {'classification': 'complete', 'ingredients': 'Frango 70%', 'nutrition_raw': 'Proteína 10% Gordura 5% Cinza 2% Humidade 80%'},
                'retailer_matches': {}
            }
        }
        # Product with material conflict already flagged
        p_mini = {
            'id': 'test_conflict_pid',
            'n': 'Conflict Product',
            'b': 'BrandX',
            's': None,
            't': 'Não classificado (Conflito)',
            'ir': False,
            'conf': True,
            'fid': 'form_conflict_test'
        }
        attached = attach_shared_assessment([p_mini], category='wet', matches_config=mock_matches)[0]
        self.assertTrue(attached['conf'])
        self.assertFalse(attached['ir'])
        self.assertIsNone(attached['s'])


if __name__ == '__main__':
    unittest.main()

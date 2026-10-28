import unittest
from src.scoring.dry_scorer import score_dry_product, get_dry_carb_band
from src.scoring.wet_scorer import score_wet_product, get_wet_carb_band
from src.scoring.evidence import (
    normalize_nutrients,
    extract_nutrient_value,
    extract_taurine,
    extract_total_meat_percentage,
    extract_first_ingredient,
    validate_composition,
    NUTRIENT_PATTERNS
)
from src.scoring.reconciliation import (
    detect_material_conflict,
    calculate_shared_score_for_formulation,
    attach_shared_assessment
)


class TestFactualGrainFreeScoring(unittest.TestCase):
    """Obligate feline carnivore tests: composition must strictly dictate grain status."""

    def test_marketing_grain_free_with_grains_is_rejected(self):
        """A product titled 'Grain Free' that contains oats or rice cannot score as grain-free."""
        p = {
            'pid': 'fake_gf_1',
            'name': 'Ração para Gato Esterilizado Grain Free Frango Purenatural',
            'brand': 'Purenatural',
            'price': 25.0,
            'unit_price_kg': 10.0,
            'description': 'Fórmula Grain Free com frango fresco e arroz branco para digestão',
            'ingredients': 'Frango (47%), arroz branco, aveia, gordura de frango, polpa de beterraba',
            'nutrition_raw': 'Proteína: 32.0% Gordura: 15.0% Humidade: 8.0% Fibra: 2.5% Cinza: 7.0%'
        }
        full, mini = score_dry_product(p)
        self.assertFalse(full['is_grain_free'])
        self.assertFalse(mini['gf'])
        self.assertTrue(full['has_grains'])
        # Must not be Tier S (strictly restricted from Tier S)
        self.assertLessEqual(full['score'], 79)
        self.assertNotEqual(mini['t'], 'Tier S (Ultra-Premium)')

    def test_truly_grain_free_dry_food_can_reach_tier_s(self):
        """A genuine grain-free food with high fresh meat and low carbs can achieve Tier S."""
        p = {
            'pid': 'true_gf_1',
            'name': 'Ração Ultra Premium Sem Cereais Gato',
            'brand': 'TopCarnivore',
            'price': 30.0,
            'unit_price_kg': 12.0,
            'ingredients': 'Frango fresco (50%), peru desidratado (25%), fígado de frango (5%), ervilhas (8%), gordura de aves, óleo de salmão',
            'nutrition_raw': 'Proteína: 42.0% Gordura: 18.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0% Taurina: 2000 mg/kg'
        }
        full, mini = score_dry_product(p)
        self.assertTrue(full['is_grain_free'])
        self.assertTrue(mini['gf'])
        self.assertGreaterEqual(full['score'], 80)
        self.assertIn('Tier S', mini['t'])

    def test_acana_first_feast_composition_capped_at_tier_a(self):
        """Acana First Feast contains whole oats (aveia integral) and must cap at 79 Tier A."""
        p = {
            'pid': 'acana_first_feast',
            'name': 'Ração para Gato Júnior First Feast Acana',
            'brand': 'Acana',
            'price': 22.0,
            'unit_price_kg': 12.2,
            'description': 'Alimento completo para gatinhos',
            'ingredients': 'Frango fresco (19%), frango desidratado (13%), arenque desidratado (13%), aveia integral, ervilhas inteiras, gordura de frango (7%), peru desidratado (5%)',
            'nutrition_raw': 'Proteína: 37.0% Gordura: 18.0% Humidade: 10.0% Fibra: 4.0% Cinza: 10.0% Cálcio: 1.7% Fósforo: 1.1% Taurina: 0.1% EPA: 0.2% DHA: 0.2%'
        }
        full, mini = score_dry_product(p)
        self.assertFalse(full['is_grain_free'])
        self.assertFalse(mini['gf'])
        self.assertEqual(full['score'], 79)
        self.assertEqual(mini['t'], 'Tier A (Excelente / Alto Teor Carne)')
        self.assertEqual(mini['meat_pct'], 57)
        self.assertTrue(mini['fresh'])


class TestRenalCeilingAndMineralBalance(unittest.TestCase):
    """Tests for phosphorus and magnesium checks protecting feline renal & urinary health."""

    def test_excessive_phosphorus_receives_penalty(self):
        """Phosphorus > 1.3% in dry kibble triggers an 8-point penalty for renal damage risk."""
        p_normal = {
            'pid': 'phos_norm',
            'name': 'Dry Normal Phosphorus',
            'brand': 'SafePhos',
            'price': 15.0,
            'unit_price_kg': 7.5,
            'ingredients': 'Frango desidratado (40%), batata, gordura de aves',
            'nutrition_raw': 'Proteína: 34.0% Gordura: 16.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0% Fósforo: 1.1% Cálcio: 1.3%'
        }
        full_normal, _ = score_dry_product(p_normal)

        p_high = {
            'pid': 'phos_high',
            'name': 'Dry High Phosphorus',
            'brand': 'HighPhos',
            'price': 15.0,
            'unit_price_kg': 7.5,
            'ingredients': 'Frango desidratado (40%), batata, gordura de aves',
            'nutrition_raw': 'Proteína: 34.0% Gordura: 16.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0% Fósforo: 1.5% Cálcio: 1.6%'
        }
        full_high, _ = score_dry_product(p_high)
        # Difference between normal and high phosphorus should be 8 points
        self.assertEqual(full_normal['score'] - full_high['score'], 8)

    def test_sterilised_magnesium_scoring(self):
        """Sterilised foods with low magnesium (<=0.08%) get bonus; >0.10% get penalty."""
        p_ideal_mg = {
            'pid': 'ster_ideal_mg',
            'name': 'Gato Esterilizado Frango',
            'brand': 'SterBrand',
            'price': 20.0,
            'unit_price_kg': 10.0,
            'ingredients': 'Frango fresco (35%), ervilhas, gordura de aves',
            'nutrition_raw': 'Proteína: 36.0% Gordura: 12.0% Humidade: 8.0% Fibra: 3.0% Cinza: 6.5% Magnésio: 0.07%'
        }
        full_ideal, _ = score_dry_product(p_ideal_mg)

        p_high_mg = {
            'pid': 'ster_high_mg',
            'name': 'Gato Esterilizado Frango High Mg',
            'brand': 'SterBrand',
            'price': 20.0,
            'unit_price_kg': 10.0,
            'ingredients': 'Frango fresco (35%), ervilhas, gordura de aves',
            'nutrition_raw': 'Proteína: 36.0% Gordura: 12.0% Humidade: 8.0% Fibra: 3.0% Cinza: 6.5% Magnésio: 0.12%'
        }
        full_high, _ = score_dry_product(p_high_mg)
        # Difference should be +5 (ideal) vs -8 (penalty) = 13 points
        self.assertEqual(full_ideal['score'] - full_high['score'], 13)


class TestAdditivesAndMarineOmegaWordBoundaries(unittest.TestCase):
    """Tests that negative additives are penalized and false positive substrings are eliminated."""

    def test_marine_omega_false_positive_elimination(self):
        """The substring 'epa' in 'preparado' or 'separado' must NOT trigger omega-3 bonus."""
        p_preparado = {
            'pid': 'test_preparado',
            'name': 'Ração Preparado de Carne',
            'brand': 'GenericBrand',
            'price': 10.0,
            'unit_price_kg': 5.0,
            'ingredients': 'Carne desidratada de aves preparada mecanicamente, arroz, milho',
            'nutrition_raw': 'Proteína: 30.0% Gordura: 12.0% Humidade: 8.0% Fibra: 3.0% Cinza: 8.0%'
        }
        full, mini = score_dry_product(p_preparado)
        self.assertFalse(full['has_marine_omega'])
        self.assertFalse(mini['omg'])

    def test_marine_omega_positive_detection(self):
        """Genuine marine omega-3 sources trigger +3 bonus."""
        p_salmon_oil = {
            'pid': 'test_salmon_oil',
            'name': 'Ração Peixe com Óleo de Salmão',
            'brand': 'GoodBrand',
            'price': 15.0,
            'unit_price_kg': 7.5,
            'ingredients': 'Salmão fresco (30%), batata, óleo de salmão (3%)',
            'nutrition_raw': 'Proteína: 32.0% Gordura: 15.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0%'
        }
        full, mini = score_dry_product(p_salmon_oil)
        self.assertTrue(full['has_marine_omega'])
        self.assertTrue(mini['omg'])

    def test_dry_sugar_penalty_and_negation_guard(self):
        """Dry kibble with added sugars loses 15 points; 'sem açúcar' does not trigger penalty."""
        p_with_sugar = {
            'pid': 'sugar_dry',
            'name': 'Ração Seca com Açúcar',
            'brand': 'SweetPet',
            'price': 15.0,
            'unit_price_kg': 7.5,
            'ingredients': 'Frango fresco 30%, arroz, açúcares, gordura de aves',
            'nutrition_raw': 'Proteína: 34.0% Gordura: 16.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0%'
        }
        full_sugar, mini_sugar = score_dry_product(p_with_sugar)
        self.assertTrue(full_sugar['has_sugar'])
        self.assertFalse(mini_sugar['conf'])

        p_no_sugar = {
            'pid': 'no_sugar_dry',
            'name': 'Ração Seca Sem Açúcar',
            'brand': 'HealthyPet',
            'price': 15.0,
            'unit_price_kg': 7.5,
            'ingredients': 'Frango fresco 30%, arroz, gordura de aves (sem açúcares adicionados)',
            'nutrition_raw': 'Proteína: 34.0% Gordura: 16.0% Humidade: 8.0% Fibra: 2.0% Cinza: 7.0%'
        }
        full_no_sugar, _ = score_dry_product(p_no_sugar)
        self.assertFalse(full_no_sugar['has_sugar'])
        self.assertEqual(full_no_sugar['score'] - full_sugar['score'], 15)


class TestWetFoodBiologicalRules(unittest.TestCase):
    """Wet food scoring rules: complete cooking broths, byproduct penalties, and carbs."""

    def test_cooking_broth_complete_wet_food_not_excluded(self):
        """A complete wet food cooked in natural broth (caldo) must NOT be filtered out."""
        p = {
            'pid': 'feringa_wet_complete',
            'name': 'Feringa Menu Duo Frango e Peru',
            'brand': 'Feringa',
            'price': 2.5,
            'unit_price_kg': 12.5,
            'description': 'Alimento completo para gatos adultos',
            'ingredients': '70% aves (40% frango, 30% peru), 28.5% caldo de carne, 1% minerais, 0.5% óleo de salmão',
            'nutrition_raw': 'Proteína: 10.5% Gordura: 5.5% Humidade: 80.0% Fibra: 0.3% Cinza: 2.2%'
        }
        full, mini = score_wet_product(p)
        self.assertIsNotNone(full)
        self.assertIsNotNone(mini)
        self.assertTrue(full['is_ranked'])
        self.assertEqual(full['classification'], 'Completo')
        self.assertEqual(mini['meat_pct'], 70)
        self.assertGreaterEqual(full['score'], 80)

    def test_soup_title_without_complete_declaration_is_excluded(self):
        """A product titled 'Sopa para Gato' or 'Caldo' without complete declaration is complementary."""
        p = {
            'pid': 'soup_treat',
            'name': 'Sopa para Gato Gourmet Frango',
            'brand': 'Gourmet',
            'price': 1.0,
            'unit_price_kg': 20.0,
            'description': 'Deliciosa sopa para momentos de mimo',
            'ingredients': 'Carnes e subprodutos animais (frango 4%), subprodutos vegetais',
            'nutrition_raw': 'Proteína: 2.0% Gordura: 0.5% Humidade: 95.0% Fibra: 0.1% Cinza: 1.0%'
        }
        full, mini = score_wet_product(p)
        self.assertIsNone(full)
        self.assertIsNone(mini)

    def test_vague_byproducts_penalty_not_suppressed_by_low_meat(self):
        """Low meat percentage (e.g. 8%) must NOT suppress the -12 vague byproducts penalty."""
        p_8pct = {
            'pid': 'vague_8pct',
            'name': 'Saqueta Terrine Vaca 8%',
            'brand': 'CheapBrand',
            'price': 0.8,
            'unit_price_kg': 8.0,
            'description': 'Alimento completo para gatos',
            'ingredients': 'Carnes e subprodutos animais (dos quais 8% vaca), substâncias minerais',
            'nutrition_raw': 'Proteína: 8.5% Gordura: 4.5% Humidade: 82.0% Fibra: 0.4% Cinza: 2.0%'
        }
        full, mini = score_wet_product(p_8pct)
        self.assertTrue(full['is_ranked'])
        # Since meat is only 8%, has_vague_byproducts must remain True and Tier should be C or D
        self.assertIn(mini['t'], ['Tier C (Básico / Ingredientes Genéricos)', 'Tier D (Evitar / Açúcares e Cereais)'])

    def test_vegetable_protein_penalty_and_badge_export(self):
        """Plant protein extracts trigger -15 penalty and export veg=True to minified payload."""
        p = {
            'pid': 'wet_veg_prot',
            'name': 'Pedaços em Molho com Peixe',
            'brand': 'VegBrand',
            'price': 0.6,
            'unit_price_kg': 6.0,
            'description': 'Alimento completo para gatos adultos',
            'ingredients': 'Carnes e subprodutos animais, extractos de proteínas vegetais, peixes e subprodutos de peixes, açúcares',
            'nutrition_raw': 'Proteína: 9.0% Gordura: 4.0% Humidade: 81.0% Fibra: 0.5% Cinza: 2.0%'
        }
        full, mini = score_wet_product(p)
        self.assertTrue(full['has_veg_protein'])
        self.assertTrue(mini['veg'])
        self.assertTrue(full['has_sugar'])
        self.assertTrue(mini['sug'])
        self.assertEqual(mini['t'], 'Tier D (Evitar / Açúcares e Cereais)')


class TestReconciliationAndConflictPrevention(unittest.TestCase):
    """Reconciliation tests: benign differences do not disqualify; material conflicts do."""

    def test_dry_shared_score_preserves_carbohydrates(self):
        """Shared score calculation for dry food must not lose carbohydrate metrics."""
        mock_matches = {
            'dry_form_1': {
                'description': 'PureDry Chicken Formula',
                'brand': 'PureDry',
                'category': 'dry',
                'verified': {
                    'classification': 'complete',
                    'ingredients': 'Frango fresco 40%, frango desidratado 20%, ervilhas, batata',
                    'nutrition_raw': 'Proteína: 38.0% Gordura: 16.0% Humidade: 8.0% Fibra: 2.5% Cinza: 7.5%'
                },
                'retailer_matches': {'continente': ['12345']}
            }
        }
        shared = calculate_shared_score_for_formulation('dry_form_1', mock_matches, category='dry')
        self.assertIsNotNone(shared)
        self.assertTrue(shared['is_ranked'])
        self.assertEqual(shared['carbs'], 28.0)
        self.assertIn('Elevado', shared['carb_band'])

    def test_benign_ingredient_formatting_does_not_escalate_to_conflict(self):
        """Formatting differences resolved in favor of verified record must remain ranked."""
        mock_matches = {
            'wet_form_1': {
                'description': 'GranataPet DeliCatessen Salmon',
                'brand': 'GranataPet',
                'category': 'wet',
                'verified': {
                    'classification': 'complete',
                    'ingredients': 'Salmão 72%, caldo de salmão 24.9%, sementes de romã 1%, óleo de salmão 1%, minerais 1%',
                    'nutrition_raw': 'Proteína: 10.2%, Gordura: 5.5%, Cinza: 2.3%, Fibra: 0.4%, Humidade: 80.0%'
                },
                'retailer_matches': {'zu': ['999001']}
            }
        }
        # Retailer product with slight textual variation
        p_retailer = {
            'id': '999001',
            'n': 'GranataPet DeliCatessen Salmão 200g',
            'b': 'GranataPet',
            'r': 'zu',
            'p': 2.0,
            'pkg': 10.0,
            's': 85,
            't': 'Tier S (Ultra-Premium)',
            'ir': True,
            'conf': False
        }
        reconciled_list = attach_shared_assessment([p_retailer], category='wet', matches_config=mock_matches)
        attached = reconciled_list[0]
        self.assertTrue(attached['ir'])
        self.assertFalse(attached['conf'])
        self.assertEqual(attached['t'], 'Tier S (Ultra-Premium)')
        self.assertEqual(attached['prot'], 10.2)
        self.assertEqual(attached['fat'], 5.5)

    def test_material_conflict_detection(self):
        """Opposing complete vs complementary classifications must be detected as material conflict."""
        retailer_obs = {'classification': 'Complementar', 'ingredients': 'Atum 70%', 'nutrition_raw': 'Proteína 14%'}
        verified = {'classification': 'complete', 'ingredients': 'Atum 70%, vitaminas', 'nutrition_raw': 'Proteína 14%'}
        is_mat, reasons = detect_material_conflict(retailer_obs, verified)
        self.assertTrue(is_mat)
        self.assertIn("Contradictory classification", reasons[0])


class TestEvidenceParsingRobustness(unittest.TestCase):
    """Stress tests for label regex parsing, space separators, and physical caps."""

    def test_taurine_space_separator_and_additive_code(self):
        """Taurine formatted with space separator '2 130 mg/kg' or '(3a370)' is parsed."""
        raw1 = "Aditivos: Taurina: 2 130 mg/kg, Vitamina A: 20 000 UI/kg"
        t1 = extract_taurine(raw1)
        self.assertEqual(t1['value'], 2130.0)
        self.assertEqual(t1['unit'], 'mg/kg')

        raw2 = "Taurina (3a370) 2500 mg/kg"
        t2 = extract_taurine(raw2)
        self.assertEqual(t2['value'], 2500.0)
        self.assertEqual(t2['unit'], 'mg/kg')

        raw3 = "Taurina: 0.25 g/kg"
        t3 = extract_taurine(raw3)
        self.assertEqual(t3['value'], 250.0)
        self.assertEqual(t3['unit'], 'mg/kg')

    def test_magnesium_physical_sanity_cap(self):
        """Feline magnesium in % never exceeds 0.3%; higher values are mg/kg or invalid."""
        raw = "Componentes analíticos: Magnésio: 80 mg/kg, Proteína: 30%, Gordura: 15%"
        mg_val = extract_nutrient_value(raw, NUTRIENT_PATTERNS['magnesium'])
        # Must return None for % because 80 mg/kg is not a percentage
        self.assertIsNone(mg_val)

        raw_valid = "Proteína: 32% Gordura: 14% Magnésio: 0.08%"
        mg_valid = extract_nutrient_value(raw_valid, NUTRIENT_PATTERNS['magnesium'])
        self.assertEqual(mg_valid, 0.08)

    def test_multipack_meat_does_not_sum_across_pouches(self):
        """A multipack stating '8 x 85g com frango (14% frango)' must extract 14%, not 112%."""
        multipack = "Multipack 8 saquetas x 85 g: carne e subprodutos animais (dos quais 14% frango), substâncias minerais"
        meat = extract_total_meat_percentage(multipack)
        self.assertEqual(meat, 14)

    def test_sugar_cane_fiber_does_not_trigger_sugar_penalty(self):
        """Sugar cane fiber ('fibra de cana-de-açúcar') is insoluble fiber, not added sugar."""
        p = {
            'pid': 'uppy_nutri_test',
            'name': 'Ração para Gato Adulto Esterilizado Sem Cereais Uppy Nutri',
            'brand': 'Uppy Nutri',
            'price': 25.0,
            'unit_price_kg': 12.5,
            'ingredients': 'Frango (54%) (frango fresco 26%, proteína de frango desidratada 26%), batata (14%), fibras vegetais (fibra de cana-de-açúcar 2%, polpa de beterraba 1,5%), ovo em pó (4%), gordura de aves, taurina',
            'nutrition_raw': 'Proteína bruta: 38.0%, Matéria gorda bruta: 13.0%, Cinza bruta: 7.5%, Fibra bruta: 3.5%, Magnésio: 0.08%',
            'category': 'dry'
        }
        full_p, min_p = score_dry_product(p)
        self.assertFalse(full_p['has_sugar'])
        self.assertNotIn('Açúcares Adicionados (-15)', full_p.get('cons') or [])
        self.assertGreaterEqual(full_p['score'], 85)

    def test_sub_ingredient_parenthetical_percentage_not_double_counted(self):
        """Outer declaration 'Frango (54%) (frango fresco 26%, proteína desidratada 26%)' must return 54%, not 106%."""
        text = "Frango (54%) (frango fresco 26%, proteína de frango desidratada 26%, proteína de frango hidrolisada 2%), batata (14%)"
        meat = extract_total_meat_percentage(text)
        self.assertEqual(meat, 54)

    def test_sub_percentage_das_quais_not_double_counted(self):
        """'proteínas secas de aves (16% das quais 50% de frango)' must return 16%, not 66%."""
        text = "proteínas secas de aves (16% das quais 50% de frango), farinha de proteínas de milho"
        meat = extract_total_meat_percentage(text)
        self.assertEqual(meat, 16)

    def test_four_percent_token_trick_capped_at_tier_c(self):
        """Gourmet Gold with 'Carnes e subprodutos animais (57%, dos quais 4% Vitela)' must be capped at Tier C (<=59)."""
        p = {
            'pid': 'gourmet_token_test',
            'name': 'Comida Húmida para Gato Júnior Mousse Gatinhos Vitela Purina Gourmet Gold',
            'brand': 'Purina Gourmet Gold',
            'price': 1.2,
            'unit_price_kg': 14.1,
            'ingredients': 'Carnes e subprodutos animais (57%, dos quais 4% Vitela), Peixes e Subprodutos de Peixes, Minerais',
            'nutrition_raw': 'Proteína bruta 13%, Matéria gorda bruta 7%, Cinza bruta 3%, Humidade 74.5%, Fibra bruta 0.5%',
            'category': 'wet'
        }
        from src.scoring.wet_scorer import score_wet_product
        full_p, min_p = score_wet_product(p)
        self.assertLessEqual(full_p['score'], 59)
        self.assertEqual(full_p['tier'], 'Tier C (Básico / Ingredientes Genéricos)')

    def test_complete_fillets_in_gravy_not_excluded_as_complementary(self):
        """Complete wet foods mentioning 'filetes' but declared as complete meals must be scored."""
        p = {
            'pid': '8375238',
            'name': 'Comida Húmida para Gato Adulto Sem Cereais Frango e Pato Saquetas Smaak',
            'brand': 'Smaak',
            'price': 0.85,
            'unit_price_kg': 8.5,
            'description': 'O alimento húmido completo, preparado com suculentos filetes de frango e pato em molho (50% filetes / 50% molho), garante uma refeição saborosa e equilibrada.',
            'ingredients': 'Composição: Carne e derivados de origem animal nos filetes (85%) (dos quais 70% de frango, 5% de pato), 4% de topinambo, 2,7% de farinha de ervilha, 0,9% de lignocelulose.',
            'nutrition_raw': 'Constituintes Analíticos: Proteína bruta 6%, Matéria Gorda Bruta 4,5%, Cinzas brutas 0,7%, Fibras brutas 0,5%, Humidade 84%, Cálcio 0,2%, Fósforo 0,2%',
            'category': 'wet'
        }
        from src.scoring.wet_scorer import score_wet_product
        full_p, min_p = score_wet_product(p)
        self.assertIsNotNone(full_p)
        self.assertTrue(full_p['is_ranked'])


if __name__ == '__main__':
    unittest.main()

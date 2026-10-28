import unittest
import math
from src.scoring.litter_evidence import (
    extract_litter_measurements, classify_litter_material,
    detect_litter_clumping, detect_litter_scent, detect_litter_dust,
    detect_litter_features, evaluate_litter_evidence,
    LitterMaterial
)
from src.scoring.litter_scorer import score_litter_product

class TestLitterScoringAndEvidence(unittest.TestCase):

    def test_volume_and_weight_extraction(self):
        # Single volume
        v1, w1 = extract_litter_measurements("Areia Aglomerante Sanicat 10 L")
        self.assertEqual(v1, 10.0)
        self.assertIsNone(w1)

        # Multi-pack volume
        v2, w2 = extract_litter_measurements("Cat's Best Original 2 x 10 litros")
        self.assertEqual(v2, 20.0)

        # Single weight
        v3, w3 = extract_litter_measurements("Areia Sepiolite 5 kg")
        self.assertIsNone(v3)
        self.assertEqual(w3, 5.0)

        # Dual measurement (vol + weight in parens)
        v4, w4 = extract_litter_measurements("Biokat's Diamond Care Classic areia aglomerante sem perfume 10 l (8,5 kg)")
        self.assertEqual(v4, 10.0)
        self.assertEqual(w4, 8.5)

        # Multi-pack weight
        v5, w5 = extract_litter_measurements("Areia bentonite 2 x 6 kg")
        self.assertEqual(w5, 12.0)

    def test_measurement_edge_cases_and_false_positives(self):
        # 1. Portuguese Retail Abbreviations for Liters
        self.assertEqual(extract_litter_measurements("Areia 10 lt")[0], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 10 lts")[0], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 10 ltr")[0], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 10 ltrs")[0], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 2 x 10 lt")[0], 20.0)

        # 2. Portuguese Plurals & Spelled-out Weights
        self.assertEqual(extract_litter_measurements("Areia 10 kgs")[1], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 10kgs")[1], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 10 quilos")[1], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 10 kilos")[1], 10.0)
        self.assertEqual(extract_litter_measurements("Areia 2 x 6 kgs")[1], 12.0)
        self.assertEqual(extract_litter_measurements("Areia 400 gr")[1], 0.4)
        self.assertEqual(extract_litter_measurements("Areia 500 gramas")[1], 0.5)

        # 3. False Positives Prevention
        v_4g, w_4g = extract_litter_measurements("Tigerino 4G Clumping 10 L")
        self.assertEqual(v_4g, 10.0)
        self.assertIsNone(w_4g)

        v_bare4g, w_bare4g = extract_litter_measurements("Areia 4G")
        self.assertIsNone(v_bare4g)
        self.assertIsNone(w_bare4g)

        self.assertEqual(extract_litter_measurements("Sanicat 7 dias"), (None, None))
        self.assertEqual(extract_litter_measurements("Areia 3x Action"), (None, None))
        self.assertEqual(extract_litter_measurements("Areia 3 em 1"), (None, None))

        # 4. Discontinuous Multipacks
        self.assertEqual(extract_litter_measurements("Pack 2x Sanicat 10L")[0], 20.0)
        self.assertEqual(extract_litter_measurements("Pack 2 x Areia 10 L")[0], 20.0)

        # 5. Compound Dual Strings
        self.assertEqual(extract_litter_measurements("KittyBay 10 l / 6 kg"), (10.0, 6.0))
        self.assertEqual(extract_litter_measurements("Biokat's 3 x 5 L (15 L)"), (15.0, None))

    def test_unit_price_fallback_and_pack_size_completeness(self):
        # Fallback to scraped unit_price_l when volume not in title
        p1 = {
            'name': 'Areia Aglomerante Especial',
            'price': 13.00,
            'unit_price_l': 1.30,
            'category': 'litter'
        }
        ev1 = evaluate_litter_evidence(p1)
        self.assertEqual(ev1['unit_price_l'], 1.30)
        self.assertEqual(ev1['volume_l'], 10.0)

        # Pack size weight extracted even when title already had volume
        p2 = {
            'name': "Cat's Best Original 10 l",
            'pack_size': '10 l (aprox. 4,3 kg)',
            'price': 12.29
        }
        ev2 = evaluate_litter_evidence(p2)
        self.assertEqual(ev2['volume_l'], 10.0)
        self.assertEqual(ev2['weight_kg'], 4.3)

    def test_material_classification(self):
        self.assertEqual(classify_litter_material("Areia Tofu Natural Catfield"), LitterMaterial.TOFU_PLANT)
        self.assertEqual(classify_litter_material("Mandioca branca areia ecológica KittyBay"), LitterMaterial.TOFU_PLANT)
        self.assertEqual(classify_litter_material("Cat's Best Original pellets de madeira"), LitterMaterial.WOOD)
        self.assertEqual(classify_litter_material("Ever Clean Extra Strong Clumping"), LitterMaterial.BENTONITE)
        self.assertEqual(classify_litter_material("Areia Sílica Cristais Sanicat"), LitterMaterial.SILICA)
        self.assertEqual(classify_litter_material("Areia Sepiolite Absorvente"), LitterMaterial.SEPIOLITE)

    def test_cats_best_classified_as_wood_despite_vegetal_keyword(self):
        # Precedence check: Cat's Best contains 'vegetal' but is wood/plant fibers
        mat = classify_litter_material("Cat's Best Original Areia Vegetal Aglomerante para Gatos")
        self.assertEqual(mat, LitterMaterial.WOOD)

    def test_pea_straw_and_pellets_substrates(self):
        self.assertEqual(classify_litter_material("Catit Go Natural Pea Husk Clumping Litter"), LitterMaterial.TOFU_PLANT)
        self.assertEqual(classify_litter_material("Areia de palha vegetal natural"), LitterMaterial.TOFU_PLANT)
        self.assertEqual(classify_litter_material("Pellets de madeira de pinho 15 kg"), LitterMaterial.WOOD)

    def test_tigerino_nuggies_and_sandy_bentonite(self):
        self.assertEqual(classify_litter_material("Tigerino Nuggies areia bentonite"), LitterMaterial.BENTONITE)
        self.assertEqual(classify_litter_material("Sandy areia de gato 10 kg"), LitterMaterial.BENTONITE)

    def test_standalone_crystals_classified_as_silica(self):
        self.assertEqual(classify_litter_material("Sanicat Cristais Areia Absorvente 5 L"), LitterMaterial.SILICA)

    def test_common_absorbent_mineral_classified_as_sepiolite(self):
        self.assertEqual(classify_litter_material("Areia Mineral Absorvente Continente 5 kg"), LitterMaterial.SEPIOLITE)

    def test_substrate_safety_and_negations(self):
        # 1. Silica Negation guard
        self.assertEqual(classify_litter_material("Areia vegetal Tofu sem sílica 6 L"), LitterMaterial.TOFU_PLANT)
        self.assertEqual(classify_litter_material("Areia aglomerante livre de sílica 10 L"), LitterMaterial.BENTONITE)

        # 2. Composite bentonite with silica crystals -> Bentonite
        self.assertEqual(classify_litter_material("Areia bentonite branca com cristais de sílica 10 L"), LitterMaterial.BENTONITE)

        # 3. Kitten Compaction Risk Penalty on clumping bentonite
        p_kitten = {
            'pid': 'kitten_clay',
            'name': 'Areia Aglomerante para Gatinhos Kitten Bentonite 5 L',
            'price': 6.99,
            'description': 'Areia aglomerante de bentonite suave para gatinhos kitten.'
        }
        res_k, _ = score_litter_product(p_kitten)
        self.assertIn('Perigo de Compactação Digestiva em Gatinhos (-15)', res_k['cons'])

    def test_clumping_edge_cases_and_hygiene(self):
        # 1. Recycled paper pellets must NOT clump
        self.assertFalse(detect_litter_clumping("Areia de Papel Reciclado 10 L"))
        self.assertFalse(detect_litter_clumping("Sanicat Clean & Green Recycled Paper Pellets 10 L"))

        # 2. Wood pellets default to non-clumping (disintegrate into sawdust)
        self.assertFalse(detect_litter_clumping("Pellets de madeira de pinho 15 kg"))

        # 3. Known clumping wood brands detected without explicit 'aglomerante'
        self.assertTrue(detect_litter_clumping("Cat's Best Original 10 L"))
        self.assertTrue(detect_litter_clumping("Cat's Best Smart Pellets 10 L"))

        # 4. Portuguese singular 'torrão' negation
        self.assertFalse(detect_litter_clumping("Areia bentonite não forma torrão"))
        self.assertFalse(detect_litter_clumping("Areia bentonite sem formação de torrões"))

        # 5. Multilingual negations on imported feeds (Spanish, French, German)
        self.assertFalse(detect_litter_clumping("Arena bentonita no aglomerante 10 L"))
        self.assertFalse(detect_litter_clumping("Litière bentonite non agglomérante 10 L"))
        self.assertFalse(detect_litter_clumping("Bentonit Katzenstreu nicht klumpend 10 L"))

        # 6. Absorbent bentonite without clumping claims
        self.assertFalse(detect_litter_clumping("Sanicat Bentonite Areia Absorvente 10 L"))

        # 7. Clumping positive marker with singular torrão
        self.assertTrue(detect_litter_clumping("Areia mineral com rápida formação de torrão"))

        # 8. True Tofu / Cassava correctly clumping
        self.assertTrue(detect_litter_clumping("Areia Tofu Natural 6 L"))
        self.assertTrue(detect_litter_clumping("Areia de Mandioca KittyBay 6 L"))

    def test_expanded_european_fragrances_detected(self):
        """Verify all common European/Portuguese market perfumes are penalized."""
        test_cases = [
            ("Sanicat Clumping White Marseille 10 L", "Sabão de Marselha"),
            ("Biokat's Classic Babypowder 10 L", "Talco / Baby Powder"),
            ("Sanicat Alfazema 10 L", "Lavanda / Alfazema"),
            ("Tigerino Nuggies Lemon 14 L", "Citrinos"),
            ("Sanicat Clumping White Floral 10 L", "Floral"),
            ("Tigerino Nuggies Flowers 14 L", "Floral"),
            ("Ever Clean Spring Garden 10 L", "Floral"),
            ("Sanicat Rose 10 L", "Rosas"),
            ("Sanicat Cotton Blossom 10 L", "Flor de Algodão"),
            ("Biokat's Camomila 10 L", "Camomila"),
            ("Catfield Tofu Chá Verde 6 L", "Chá Verde"),
            ("Kit Cat Soya Clump Peach 7 L", "Pêssego"),
            ("Ever Clean Extra Strong Scented 10 L", "Perfumado"),
            ("Areia Aromatizada Bentonite 10 L", "Perfumado"),
            ("Biokat's Bianco Fresh Extra 10 L", "Brisa Marinha / Fresco"),
            ("Areia com cheiro agradável 10 L", "Perfumado"),
            ("Areia aglomerante com aroma a pinho 10 L", "Pinho")
        ]
        for title, expected_label in test_cases:
            has_perfume, is_unscented, scent_name = detect_litter_scent(title)
            self.assertTrue(has_perfume, f"Failed to detect perfume in: {title}")
            self.assertFalse(is_unscented, f"Perfumed litter incorrectly marked unscented: {title}")

    def test_fragrance_negation_in_hypoallergenic_litters(self):
        """Unscented litters claiming 'sem perfume de lavanda' must NOT be penalized."""
        p1 = detect_litter_scent(
            "Areia Vegetal Tofu 6 L", 
            "Areia 100% natural sem aditivos ou perfume de lavanda. Muito absorvente."
        )
        self.assertFalse(p1[0], "Hypoallergenic litter falsely flagged as lavanda")
        self.assertTrue(p1[1], "Hypoallergenic litter should receive unscented status")

        p2 = detect_litter_scent(
            "Cat's Best Pure Nature 10 L", 
            "Fibras vegetais puras. Sem perfume artificial nem talco."
        )
        self.assertFalse(p2[0], "Hypoallergenic litter falsely flagged as talco")
        self.assertTrue(p2[1], "Hypoallergenic litter should receive unscented status")

    def test_odor_control_copy_does_not_leak_unscented_bonus(self):
        """Claims about eliminating urine smell must not award unscented bonus to perfumed or unverified litters."""
        res1 = detect_litter_scent(
            "Sanicat Cotton Blossom 10 L", 
            "Areia aglomerante que mantém a sua casa sem cheiro a urina."
        )
        self.assertTrue(res1[0])
        self.assertFalse(res1[1], "Scented litter leaked unscented bonus due to 'sem cheiro a urina'")

        res2 = detect_litter_scent(
            "Areia Mineral Absorvente 5 kg", 
            "Fórmula avançada para uma casa inodora."
        )
        self.assertFalse(res2[1], "General claim 'casa inodora' leaked unscented bonus")

    def test_supermarket_neutro_variants_receive_bonus_without_ph_neutro_leak(self):
        """'Sanicat Neutro' gets unscented bonus, while 'com pH neutro' does not."""
        res_neutro = detect_litter_scent("Sanicat Clumping White Neutro 10 L")
        self.assertFalse(res_neutro[0])
        self.assertTrue(res_neutro[1], "Sanicat Neutro variant must be recognized as unscented")

        res_ph = detect_litter_scent(
            "Areia Mineral 10 L", 
            "Areia bentonite com pH neutro e alta absorção."
        )
        self.assertFalse(res_ph[0])
        self.assertFalse(res_ph[1], "'pH neutro' must not award unscented bonus")

    def test_veterinary_cap_strictly_enforced_across_all_fragrances(self):
        """Any scented litter must have score <= 69 and Tier B maximum."""
        scented_products = [
            {'name': 'Ever Clean Spring Garden 10 L', 'price': 16.99, 'description': 'Bentonite 99% sem pó com carvão ativado.'},
            {'name': 'Catfield Tofu Chá Verde 6 L', 'price': 7.49, 'description': 'Tofu vegetal aglomerante, deitável na sanita.'},
            {'name': 'Sanicat Cotton Blossom 10 L', 'price': 9.99, 'description': 'Argila branca aglomerante sem pó.'}
        ]
        for p in scented_products:
            full_p, _ = score_litter_product(p)
            self.assertTrue(full_p['has_perfume'], f"Perfume missed for {p['name']}")
            self.assertLessEqual(full_p['score'], 69, f"Score {full_p['score']} exceeded Tier B cap for {p['name']}")
            self.assertIn(full_p['tier'], ['Tier B (Médio / Boa Relação)', 'Tier C (Básico / Convencional)', 'Tier D (Evitar / Baixa Qualidade)'])

    def test_respiratory_dust_scoring_and_penalties(self):
        """Verify +8 bonus for low dust and -8 penalty strictly on mineral clays and silica."""
        # 1. Bentonite without dust guarantee receives -8 penalty
        p_bentonite_dusty = {
            'pid': 'b_dusty',
            'name': 'Areia Aglomerante Bentonite Branca 10 L',
            'price': 9.99,
            'description': 'Areia aglomerante tradicional de argila.'
        }
        res_b, _ = score_litter_product(p_bentonite_dusty)
        self.assertIn('Sem Garantia Baixo Pó (-8)', res_b['cons'])
        self.assertEqual(res_b['score'], 67) # 50 + 10(bentonite) + 15(clumping) - 8(dust)

        # 2. Bentonite with dust guarantee receives +8 bonus (16-point delta)
        p_bentonite_clean = {
            'pid': 'b_clean',
            'name': 'Areia Aglomerante Bentonite 10 L 99.9% sem pó',
            'price': 9.99,
            'description': 'Argila bentonite de alta qualidade.'
        }
        res_bc, _ = score_litter_product(p_bentonite_clean)
        self.assertIn('Baixo Pó / Dust-Free (+8)', res_bc['pros'])
        self.assertEqual(res_bc['score'], 83) # 50 + 10 + 15 + 8

        # 3. Tofu/Wood without dust guarantee does NOT receive -8 penalty
        p_tofu = {
            'pid': 'tofu_02',
            'name': 'Areia Tofu 6 L',
            'price': 7.99,
            'description': 'Areia de tofu vegetal aglomerante.'
        }
        res_t, _ = score_litter_product(p_tofu)
        self.assertNotIn('Sem Garantia Baixo Pó (-8)', res_t['cons'])

    def test_dust_evidence_extraction_robustness(self):
        """Verify false positive defenses and Portuguese label claim coverage."""
        # Negation guards
        self.assertFalse(detect_litter_dust("Atenção: este produto não é sem pó"))
        self.assertFalse(detect_litter_dust("Não é livre de pó"))
        self.assertFalse(detect_litter_dust("Areia natural sem perfume e sem pó de talco"))

        # Decimal comma & Portuguese label variants
        self.assertTrue(detect_litter_dust("Areia 99,5% sem pó"))
        self.assertTrue(detect_litter_dust("Areia bentonite 99% livre de poeira"))
        self.assertTrue(detect_litter_dust("Areia bentonite sem poeiras"))
        self.assertTrue(detect_litter_dust("Areia higiénica isenta de pó"))
        self.assertTrue(detect_litter_dust("Areia com baixo teor em pó"))
        self.assertTrue(detect_litter_dust("Areia com baixo teor de poeiras"))
        self.assertTrue(detect_litter_dust("Areia que não larga pó"))
        self.assertTrue(detect_litter_dust("Areia que não faz pó"))
        self.assertTrue(detect_litter_dust("Fórmula anti-poeira"))
        self.assertTrue(detect_litter_dust("Arena aglomerante sin polvo"))
        self.assertTrue(detect_litter_dust("Tigerino Nuggies 99% staubfrei"))

    def test_activated_charcoal_and_carbon_synonyms_and_footprint(self):
        """Full international coverage of active carbon and zero false positives on footprint."""
        # 1. Portuguese variants
        self.assertTrue(detect_litter_features("Areia com carvão activado 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Areia bentonite carvão activo 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Areia bentonite carvão ativado 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Areia com carbono activo 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Areia aglomerante carbono ativado 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Catfield Tofu Carvão Vegetal Ativado 6L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Areia aglomerante de carvão vegetal 10L")['has_active_carbon'])

        # 2. English variants
        self.assertTrue(detect_litter_features("Cat litter with active charcoal 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Ever Clean with activated charcoal 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Biokat's Diamond Care active carbon 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Tigerino Canada activated carbon 10L")['has_active_carbon'])
        self.assertTrue(detect_litter_features("Catfield Tofu Charcoal 6L")['has_active_carbon'])

        # 3. Downstream 'pegada' in description must NOT cancel active carbon
        t_dual = "Areia bentonite com carvão neutralizador 10L. Embalagem 100% reciclável com pegada neutra."
        self.assertTrue(detect_litter_features(t_dual)['has_active_carbon'])

        # 4. Pure carbon footprint must NOT trigger active carbon
        self.assertFalse(detect_litter_features("Areia ecológica com reduzida pegada de carbono 10L")['has_active_carbon'])
        self.assertFalse(detect_litter_features("Areia com pegada de carbono neutra")['has_active_carbon'])

        # 5. Negation check
        self.assertFalse(detect_litter_features("Areia bentonite branca sem carvão activo 10L")['has_active_carbon'])

    def test_baking_soda_and_sodium_bicarbonate_detection(self):
        """Sodium bicarbonate detection and negation handling."""
        self.assertTrue(detect_litter_features("Areia com bicarbonato de sódio 10L")['has_baking_soda'])
        self.assertTrue(detect_litter_features("Sanicat Clumping White com bicarbonato")['has_baking_soda'])
        self.assertTrue(detect_litter_features("Cat litter with baking soda 10L")['has_baking_soda'])
        self.assertTrue(detect_litter_features("Cat litter with sodium bicarbonate 10L")['has_baking_soda'])
        self.assertTrue(detect_litter_features("Clumping litter with natural bicarbonate 10L")['has_baking_soda'])
        self.assertTrue(detect_litter_features("Litière avec bicarbonate de soude 10L")['has_baking_soda'])

        # Negation check
        self.assertFalse(detect_litter_features("Areia natural sem bicarbonato nem químicos")['has_baking_soda'])

    def test_eco_bonuses_bounded_to_organic_substrates(self):
        """Inorganics (bentonite, silica) never receive biodegradable or flushable points."""
        # Bentonite with biodegradable bag claim -> must be False
        p_bent_bio = detect_litter_features("Areia bentonite aglomerante 10L. Embalagem 100% biodegradável.")
        self.assertFalse(p_bent_bio['is_biodegradable'])

        # Bentonite with flushable claim -> must be False (plumbing safety)
        p_bent_flush = detect_litter_features("Areia bentonite aglomerante flushable deitável na sanita")
        self.assertFalse(p_bent_flush['is_flushable'])

        # Silica with flush warning ("não é deitável na sanita") -> must be False
        p_silica = detect_litter_features("Areia de sílica cristais. Atenção: Não é deitável na sanita.")
        self.assertFalse(p_silica['is_flushable'])

        # Organic Tofu valid eco claims -> must be True
        p_tofu = detect_litter_features("Areia Tofu 100% vegetal biodegradável e deitável na sanita")
        self.assertTrue(p_tofu['is_biodegradable'])
        self.assertTrue(p_tofu['is_flushable'])

    def test_extreme_worst_case_clamps_to_10_tier_d(self):
        """Extreme worst inputs (perfumed, high dust, sepiolite non-clumping) clamp to 10 Tier D."""
        p = {
            'pid': 'worst_sepiolite',
            'name': 'Areia Sepiolite Absorvente Lavanda 5 kg',
            'brand': 'BudgetClay',
            'price': 1.99,
            'description': 'Areia sepiolite não aglomerante perfumada com lavanda.',
            'category': 'litter'
        }
        full, mini = score_litter_product(p)
        self.assertIsNotNone(full)
        self.assertTrue(full['is_ranked'])
        # 50 - 12 (sepiolite) - 12 (non-clump) - 15 (perfume) - 8 (dust) = 3 -> clamped to 10
        self.assertEqual(full['score'], 10)
        self.assertEqual(mini['s'], 10)
        self.assertEqual(full['tier'], 'Tier D (Evitar / Baixa Qualidade)')
        self.assertEqual(mini['t'], 'Tier D (Evitar / Baixa Qualidade)')

    def test_extreme_ultra_premium_tofu_clamps_to_95_tier_s(self):
        """Ultra-premium tofu formula (tofu, clumping, unscented, dust-free, bio, flushable) clamps to 95 Tier S."""
        p = {
            'pid': 'ultra_tofu',
            'name': 'Areia Tofu 100% Vegetal Sem Perfume 6 L',
            'brand': 'PurePlant',
            'price': 8.99,
            'description': 'Substrato vegetal de tofu ultra aglomerante, inodoro sem perfume, 99.9% sem pó, biodegradável e deitável na sanita com carvão activado.',
            'category': 'litter'
        }
        full, mini = score_litter_product(p)
        self.assertIsNotNone(full)
        self.assertTrue(full['is_ranked'])
        # 50 + 14 + 15 + 6 + 8 + 4 + 2 + 5 = 104 -> clamped to 95
        self.assertEqual(full['score'], 95)
        self.assertEqual(mini['s'], 95)
        self.assertEqual(full['tier'], 'Tier S (Ultra-Premium)')
        self.assertEqual(mini['t'], 'Tier S (Ultra-Premium)')

    def test_perfumed_ceiling_cap_strictly_enforces_tier_b(self):
        """High-performing perfumed formulas (bentonite + clumping + low dust + carbon) cap at 69 (Tier B)."""
        p = {
            'pid': 'scented_premium',
            'name': 'Areia Aglomerante Sabão de Marselha 10 L',
            'brand': 'PerfumedClay',
            'price': 11.99,
            'description': 'Argila bentonite aglomerante com carvão activado, dust-free e perfume sabão de marselha.',
            'category': 'litter'
        }
        full, mini = score_litter_product(p)
        self.assertTrue(full['has_perfume'])
        # Raw: 50 + 10 (bentonite) + 15 (clump) - 15 (perfume) + 8 (dust) + 5 (carb) = 73 -> capped at 69
        self.assertEqual(full['score'], 69)
        self.assertEqual(mini['s'], 69)
        self.assertEqual(full['tier'], 'Tier B (Médio / Boa Relação)')

    def test_string_and_nan_prices_handled_safely(self):
        """String, NaN, and Inf prices do not crash the scorer and cannot be ranked."""
        # 1. String price
        p_str = {'name': 'Areia Tofu 6 L', 'price': '8.99'}
        full_str, _ = score_litter_product(p_str)
        self.assertIsNotNone(full_str)
        self.assertTrue(full_str['is_ranked'])
        self.assertIsInstance(full_str['score'], int)

        # 2. NaN price
        p_nan = {'name': 'Areia Tofu 6 L', 'price': float('nan')}
        full_nan, mini_nan = score_litter_product(p_nan)
        self.assertFalse(full_nan['is_ranked'])
        self.assertIsNone(full_nan['score'])
        self.assertIn('missing_price', full_nan['unranked_reasons'])
        self.assertIsNone(mini_nan['s'])
        self.assertIsNone(mini_nan['pl'])

        # 3. Inf price
        p_inf = {'name': 'Areia Tofu 6 L', 'price': float('inf')}
        full_inf, mini_inf = score_litter_product(p_inf)
        self.assertFalse(full_inf['is_ranked'])
        self.assertIsNone(full_inf['score'])

    def test_value_ratio_fallback_when_unit_price_l_is_invalid(self):
        """Value ratio falls back cleanly to unit_price_kg if unit_price_l is missing or invalid."""
        p = {
            'name': 'Areia Sepiolite 10 kg',
            'price': 5.00,
            'category': 'litter'
        }
        full, mini = score_litter_product(p)
        self.assertTrue(full['is_ranked'])
        self.assertIsNone(full['unit_price_l'])
        self.assertEqual(full['unit_price_kg'], 0.50)
        # score / 0.50
        expected_vr = round(full['score'] / 0.50, 1)
        self.assertEqual(full['value_ratio'], expected_vr)
        self.assertEqual(mini['vr'], expected_vr)

    def test_accessory_scoop_and_litter_locker_filtered(self):
        """Accessories like 'Pá de areia' and 'Recarga LitterLocker' return None, None."""
        accessories = [
            {'name': 'Pá de areia Sanicat ergonómica', 'price': 2.99},
            {'name': 'LitterLocker II Balde de Descarte', 'price': 19.99},
            {'name': 'Recarga para Litter Locker Fashion', 'price': 7.50},
            {'name': 'Filtro de carvão activo para wc gato', 'price': 3.20}
        ]
        for acc in accessories:
            f, m = score_litter_product(acc)
            self.assertIsNone(f, f"Failed to filter accessory: {acc['name']}")
            self.assertIsNone(m, f"Failed to filter accessory: {acc['name']}")

    def test_natural_plant_tofu_scores_tier_s(self):
        p = {
            'pid': 'tofu_01',
            'name': 'Areia Absorvente Aglomerante Tofu Natural Catfield 6 l',
            'brand': 'Catfield',
            'price': 6.99,
            'description': 'Areia ecológica 100% vegetal à base de tofu. Aglomerante, sem pó e deitável na sanita.',
            'category': 'litter'
        }
        full_p, min_p = score_litter_product(p)
        self.assertIsNotNone(full_p)
        self.assertTrue(full_p['is_ranked'])
        self.assertGreaterEqual(full_p['score'], 85)
        self.assertEqual(full_p['tier'], 'Tier S (Ultra-Premium)')
        self.assertTrue(full_p['is_clumping'])
        self.assertTrue(full_p['is_biodegradable'])

    def test_silica_crystals_penalties(self):
        """Synthetic silica crystals are non-clumping and abrasive on paws."""
        p = {
            'pid': 'silica_01',
            'name': 'Areia de Sílica Cristais 5 L',
            'brand': 'Sanicat',
            'price': 5.49,
            'description': 'Cristais de gel de sílica absorventes não aglomerantes.',
            'category': 'litter'
        }
        full_p, min_p = score_litter_product(p)
        self.assertEqual(full_p['material'], LitterMaterial.SILICA)
        self.assertFalse(full_p['is_clumping'])
        self.assertLessEqual(full_p['score'], 45)

    def test_active_carbon_and_dust_free_bonus(self):
        p = {
            'pid': 'carbon_01',
            'name': 'Areia Aglomerante Carvão Ativado 10 L 99% sem pó',
            'brand': 'Ever Clean',
            'price': 14.99,
            'description': 'Areia bentonite premium com carvão activo eliminador de odores e fórmula dust-free.',
            'category': 'litter'
        }
        full_p, min_p = score_litter_product(p)
        self.assertTrue(full_p['has_active_carbon'])
        self.assertTrue(full_p['is_low_dust'])
        self.assertGreaterEqual(full_p['score'], 85)

    def test_sepiolite_absorbent_non_clumping_supermarket_reality_check(self):
        """Verify supermarket non-clumping mineral sands are classified as Sepiolite Tier D (<= 25)."""
        supermarket_absorbents = [
            ("Areia para Gato Absorvente Continente Pet 5 kg", "Areia absorvente mineral para higiene do gato. Não aglomerante."),
            ("Areia Absorvente para Gato Kitty Pingo Doce 5 kg", "Areia absorvente mineral para higiene do gato. Não aglomerante."),
            ("Areia Higiénica Absorvente Auchan 5 kg", "Areia mineral absorvente não aglomerante."),
            ("Areia Absorvente Clássica Moggy 5 kg", "Areia mineral absorvente tradicional para gatos, não aglomerante.")
        ]
        for name, desc in supermarket_absorbents:
            p = {'name': name, 'description': desc, 'price': 1.49}
            full, _ = score_litter_product(p)
            self.assertEqual(full['material'], LitterMaterial.SEPIOLITE, f"Failed material for {name}")
            self.assertFalse(full['is_clumping'], f"Incorrect clumping for {name}")
            self.assertLessEqual(full['score'], 25, f"Score {full['score']} exceeded 25 for {name}")
            self.assertEqual(full['tier'], 'Tier D (Evitar / Baixa Qualidade)')

    def test_activated_vegetable_charcoal_in_bentonite(self):
        """Bentonite with vegetable charcoal must remain Bentonite and achieve Tier S."""
        p = {
            'name': "Biokat's Diamond Care Classic 10 L",
            'price': 13.99,
            'description': 'Bentonite fina aglomerante com carvão vegetal ativado e aloé vera, sem pó, sem perfume.'
        }
        full, _ = score_litter_product(p)
        self.assertEqual(full['material'], LitterMaterial.BENTONITE)
        self.assertTrue(full['has_active_carbon'])
        self.assertFalse(full['has_perfume'])
        self.assertTrue(full['is_unscented'])
        self.assertEqual(full['score'], 94)
        self.assertEqual(full['tier'], 'Tier S (Ultra-Premium)')

    def test_frescura_marketing_phrase_on_unscented_plant_litter(self):
        """Hygiene marketing copy ('sensação de frescura') must not flag perfume on unscented litters."""
        p = {
            'name': 'Catfield Tofu Natural 6 L',
            'price': 7.99,
            'description': 'Areia vegetal 100% natural, aglomerante, sem pó e sem perfume. Garante sensação de frescura no WC.'
        }
        full, _ = score_litter_product(p)
        self.assertFalse(full['has_perfume'])
        self.assertTrue(full['is_unscented'])
        self.assertEqual(full['score'], 95)
        self.assertEqual(full['tier'], 'Tier S (Ultra-Premium)')

    def test_coordinate_negations_sem_quimicos_nem_perfume(self):
        """Coordinate negative claims ('sem químicos nem perfume') must trigger unscented bonus."""
        p = {
            'name': 'KittyBay Areia Ecológica de Mandioca Branca 6 L',
            'price': 8.99,
            'description': 'Areia 100% mandioca e milho, ultra aglomerante, sem pó, sem químicos nem perfume.'
        }
        full, _ = score_litter_product(p)
        self.assertTrue(full['is_unscented'])
        self.assertEqual(full['score'], 95)
        self.assertEqual(full['tier'], 'Tier S (Ultra-Premium)')

    def test_kitten_warning_does_not_trigger_kitten_penalty(self):
        """Veterinary warning against kittens ('Não utilizar em gatinhos') must NOT dock 15 points."""
        p = {
            'name': 'Ever Clean Extra Strong Clumping Unscented 10 L',
            'price': 17.99,
            'description': 'Areia bentonite 99.9% sem pó. Aviso: Não utilizar em gatinhos com menos de 3 meses.'
        }
        full, _ = score_litter_product(p)
        self.assertNotIn('Perigo de Compactação Digestiva em Gatinhos (-15)', full['cons'])
        self.assertGreaterEqual(full['score'], 85)
        self.assertEqual(full['tier'], 'Tier S (Ultra-Premium)')

    def test_pink_colored_indicator_silica_crystals(self):
        """Moisture-indicating pink crystals in silica must not trigger synthetic rose fragrance."""
        p = {
            'name': 'Areia de Sílica 5 L',
            'price': 5.99,
            'description': 'Cristais de sílica absorventes com grânulos cor de rosa indicadores de humidade.'
        }
        full, _ = score_litter_product(p)
        self.assertFalse(full['has_perfume'])
        self.assertNotIn('Perfume / Fragrância Artificial (Rosas) (-15)', full['cons'])

    def test_negative_price_unranked_reason(self):
        """Negative price must add 'negative_value' unranked reason and unrank."""
        p = {
            'name': 'Areia Bentonite 10 L',
            'price': -4.99,
            'description': 'Areia aglomerante'
        }
        full, mini = score_litter_product(p)
        self.assertFalse(full['is_ranked'])
        self.assertIn('negative_value', full['unranked_reasons'])

if __name__ == '__main__':
    unittest.main()

"""
Test suite for the reconciliation module (Milestone B).

Tests cover:
- Identity mapping from product_matches.json
- Reconciliation of formulation facts
- Shared assessment for matched products
- Conflict detection and handling
- Unmatched products remain independent
"""

import unittest
import json
import os
import tempfile
import shutil
from datetime import datetime, timezone

# Save original path and create test environment
class TestReconciliation(unittest.TestCase):
    """Test reconciliation functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.original_matches_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'data', 'product_matches.json'
        )
        self.backup_path = None
        
        # Create a minimal test matches file
        self.test_matches = {
            'test_formulation_1': {
                'description': 'Test Formulation 1',
                'brand': 'TestBrand',
                'line': 'TestLine',
                'category': 'wet',
                'life_stage': 'adult',
                'verified': {
                    'classification': 'complete',
                    'ingredients': 'Test ingredients',
                    'nutrition_raw': 'Proteína 10% Gordura 5% Humidade 80%'
                },
                'retailer_matches': {
                    'continente': ['test_pid_1'],
                    'zu': ['test_pid_1']
                }
            },
            'test_formulation_2': {
                'description': 'Test Formulation 2 - Junior',
                'brand': 'Purina',
                'line': 'Gourmet Gold',
                'category': 'wet',
                'life_stage': 'junior',
                'verified': {
                    'classification': 'complete',
                    'ingredients': 'Carnes e subprodutos animais (57%, dos quais 4% Vitela)',
                    'nutrition_raw': 'Proteína bruta 13% Matéria gorda bruta 7% Cinza bruta 3% Humidade 74.5% Fibra bruta 0.5%'
                },
                'retailer_matches': {
                    'continente': ['5304997'],
                    'zu': ['5304997']
                }
            }
        }
        
        self.test_matches_path = os.path.join(self.test_dir, 'test_product_matches.json')
        with open(self.test_matches_path, 'w') as f:
            json.dump(self.test_matches, f)

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_product_matches(self):
        """Test loading product matches configuration."""
        from src.scoring.reconciliation import load_product_matches
        
        # Test with non-existent file
        matches = load_product_matches()
        self.assertIsInstance(matches, dict)

    def test_get_product_key(self):
        """Test product key generation."""
        from src.scoring.reconciliation import get_product_key
        
        key1 = get_product_key('continente', '12345')
        self.assertEqual(key1, 'continente:12345')
        
        key2 = get_product_key('ZU', 'abc')
        self.assertEqual(key2, 'zu:abc')

    def test_find_formulation_id(self):
        """Test finding formulation ID for a product."""
        from src.scoring.reconciliation import find_formulation_id
        
        # Test with known match
        fid = find_formulation_id('continente', 'test_pid_1', matches_config=self.test_matches)
        self.assertEqual(fid, 'test_formulation_1')
        
        # Test with unknown product
        fid = find_formulation_id('zooplus', 'unknown_pid', matches_config=self.test_matches)
        self.assertIsNone(fid)
        
        # Test with ZU match
        fid = find_formulation_id('zu', 'test_pid_1', matches_config=self.test_matches)
        self.assertEqual(fid, 'test_formulation_1')

    def test_get_formulation_data(self):
        """Test retrieving formulation data."""
        from src.scoring.reconciliation import get_formulation_data
        
        data = get_formulation_data('test_formulation_1', matches_config=self.test_matches)
        self.assertIsNotNone(data)
        self.assertEqual(data['description'], 'Test Formulation 1')
        
        data = get_formulation_data('nonexistent', matches_config=self.test_matches)
        self.assertIsNone(data)

    def test_reconcile_product_evidence_matched(self):
        """Test reconciliation with a matched formulation."""
        from src.scoring.reconciliation import reconcile_product_evidence
        
        product = {
            'pid': 'test_pid_1',
            'name': 'Test Product',
            'brand': 'TestBrand',
            'ingredients': 'Original ingredients',
            'nutrition_raw': 'Original nutrition',
            'price': 10.0,
            'retailer': 'continente'
        }
        
        reconciled = reconcile_product_evidence(product, 'continente', matches_config=self.test_matches)
        
        self.assertTrue(reconciled['is_reconciled'])
        self.assertEqual(reconciled['formulation_id'], 'test_formulation_1')
        self.assertEqual(reconciled['ingredients'], 'Test ingredients')
        self.assertEqual(reconciled['nutrition_raw'], 'Proteína 10% Gordura 5% Humidade 80%')
        self.assertIn('reconciliation_timestamp', reconciled)

    def test_reconcile_product_evidence_unmatched(self):
        """Test reconciliation with an unmatched product."""
        from src.scoring.reconciliation import reconcile_product_evidence
        
        product = {
            'pid': 'unknown_pid',
            'name': 'Unknown Product',
            'retailer': 'continente'
        }
        
        reconciled = reconcile_product_evidence(product, 'continente', matches_config=self.test_matches)
        
        self.assertFalse(reconciled['is_reconciled'])
        self.assertIsNone(reconciled['formulation_id'])
        self.assertIn('No formulation match found', reconciled['reconciliation_notes'])

    def test_reconcile_product_evidence_conflict(self):
        """Test reconciliation with conflicting data."""
        from src.scoring.reconciliation import reconcile_product_evidence
        
        # Create a match with different verified data
        test_matches_with_conflict = {
            'conflict_formulation': {
                'description': 'Conflict Test',
                'verified': {
                    'classification': 'complete',
                    'ingredients': 'Verified ingredients',
                    'nutrition_raw': 'Proteína 12% Gordura 6%'
                },
                'retailer_matches': {
                    'continente': ['conflict_pid']
                }
            }
        }
        
        product = {
            'pid': 'conflict_pid',
            'name': 'Conflict Product',
            'ingredients': 'Different ingredients',
            'nutrition_raw': 'Proteína 10% Gordura 5%',
            'retailer': 'continente'
        }
        
        reconciled = reconcile_product_evidence(product, 'continente', matches_config=test_matches_with_conflict)
        
        self.assertTrue(reconciled['is_reconciled'])
        self.assertTrue(reconciled['has_conflicts'])
        self.assertEqual(reconciled['ingredients'], 'Verified ingredients')
        self.assertEqual(len(reconciled['conflicts']), 2)  # ingredients and nutrition

    def test_reconcile_batch(self):
        """Test batch reconciliation."""
        from src.scoring.reconciliation import reconcile_batch
        
        products = [
            {'pid': 'test_pid_1', 'name': 'Product 1', 'retailer': 'continente'},
            {'pid': 'test_pid_1', 'name': 'Product 2', 'retailer': 'zu'},
            {'pid': 'unknown', 'name': 'Product 3', 'retailer': 'continente'}
        ]
        
        reconciled, summary = reconcile_batch(products, 'continente', matches_config=self.test_matches)
        
        self.assertEqual(len(reconciled), 3)
        self.assertEqual(summary['total_products'], 3)
        self.assertEqual(summary['matched_count'], 2)  # test_pid_1 appears twice
        self.assertEqual(summary['unmatched_count'], 1)

    def test_group_by_formulation(self):
        """Test grouping products by formulation."""
        from src.scoring.reconciliation import group_by_formulation
        
        products = [
            {'formulation_id': 'form_1', 'name': 'P1'},
            {'formulation_id': 'form_1', 'name': 'P2'},
            {'formulation_id': 'form_2', 'name': 'P3'},
            {'formulation_id': None, 'name': 'P4'}
        ]
        
        groups = group_by_formulation(products)
        
        self.assertEqual(len(groups), 3)
        self.assertEqual(len(groups.get('form_1', [])), 2)
        self.assertEqual(len(groups.get('form_2', [])), 1)
        self.assertEqual(len(groups.get(None, [])), 1)

    def test_get_all_matched_products(self):
        """Test retrieving all matched products."""
        from src.scoring.reconciliation import get_all_matched_products
        
        all_matched = get_all_matched_products(matches_config=self.test_matches)
        
        self.assertIn('test_formulation_1', all_matched)
        self.assertIn('test_formulation_2', all_matched)
        
        # Check structure
        for fid, matches in all_matched.items():
            self.assertIsInstance(matches, list)
            for match in matches:
                self.assertIsInstance(match, tuple)
                self.assertEqual(len(match), 2)  # (retailer, pid)

    def test_get_formulation_summary(self):
        """Test getting formulation summary."""
        from src.scoring.reconciliation import get_formulation_summary
        
        summary = get_formulation_summary('test_formulation_1', matches_config=self.test_matches)
        
        self.assertIsNotNone(summary)
        self.assertEqual(summary['formulation_id'], 'test_formulation_1')
        self.assertEqual(summary['brand'], 'TestBrand')
        self.assertEqual(summary['retailer_count'], 2)

    def test_get_formulation_summary_nonexistent(self):
        """Test getting summary for non-existent formulation."""
        from src.scoring.reconciliation import get_formulation_summary
        
        summary = get_formulation_summary('nonexistent', self.test_matches)
        self.assertIsNone(summary)


class TestReconciliationWithGourmetGold(unittest.TestCase):
    """Test reconciliation with real Gourmet Gold Junior data."""

    def setUp(self):
        from src.scoring.reconciliation import load_product_matches
        self.test_matches = load_product_matches()

    def test_gourmet_gold_junior_reconciliation(self):
        """Test that Gourmet Gold Junior gets reconciled with verified data."""
        from src.scoring.reconciliation import reconcile_product_evidence, load_product_matches
        
        # Load actual product matches
        matches_config = load_product_matches()
        
        # Product with bad extraction (footer/newsletter text in nutrition)
        bad_continente_product = {
            'pid': '5304997',
            'name': 'Comida Húmida para Gato Júnior Mousse Gatinhos Vitela Purina Gourmet Gold',
            'brand': 'Purina Gourmet Gold',
            'ingredients': 'Composição: Carnes e subprodutos animais (57%, dos quais 4% Vitela), Peixes e Subprodutos de Peixes,...',
            'nutrition_raw': 'As novidades mais frescas no seu e-mail! Subscreva e descubra...',  # Bad extraction
            'price': 1.5,
            'unit_price_kg': 17.65,
            'retailer': 'Continente',
            'pdp_url': 'https://www.continente.pt/produto/comida-humida-para-gato-junior-mousse-gatinhos-vitela-purina-gourmet-gold-5304997.html'
        }
        
        reconciled = reconcile_product_evidence(bad_continente_product, 'Continente', matches_config=matches_config)
        
        # Should be matched
        self.assertTrue(reconciled['is_reconciled'])
        self.assertEqual(reconciled['formulation_id'], 'gourmet_gold_junior_veal_mousse_wet')
        
        # Should have verified nutrition, not footer text
        self.assertNotIn('As novidades mais frescas', reconciled['nutrition_raw'])
        self.assertIn('Proteína bruta 13%', reconciled['nutrition_raw'])
        self.assertIn('Humidade 74.5%', reconciled['nutrition_raw'])

    def test_gourmet_gold_junior_shared_assessment(self):
        """Test that matched Gourmet Gold Junior products share the same assessment."""
        from src.scoring.reconciliation import (
            reconcile_product_evidence, 
            load_product_matches,
            attach_shared_assessment
        )
        from src.scoring.wet_scorer import score_wet_product
        
        matches_config = load_product_matches()
        
        # Create two products from different retailers with the same PID
        cont_product = {
            'pid': '5304997',
            'name': 'Comida Húmida para Gato Júnior Mousse Gatinhos Vitela Purina Gourmet Gold',
            'brand': 'Purina Gourmet Gold',
            'ingredients': 'Composição: Carnes e subprodutos animais (57%, dos quais 4% Vitela), Peixes e Subprodutos de Peixes,...',
            'nutrition_raw': 'Proteína bruta 13% Matéria gorda bruta 7% Cinza bruta 3% Humidade 74.5% Fibra bruta 0.5%',
            'price': 1.5,
            'unit_price_kg': 17.65,
            'retailer': 'Continente',
            'pdp_url': 'https://www.continente.pt/produto/comida-humida-para-gato-junior-mousse-gatinhos-vitela-purina-gourmet-gold-5304997.html'
        }
        
        zu_product = {
            'pid': '5304997',
            'name': 'Comida Húmida para Gato Júnior Mousse Gatinhos Vitela Purina Gourmet Gold',
            'brand': 'Purina Gourmet Gold',
            'ingredients': 'Características\nDescrição:\nMousse para Gatinhos de GOURMET',
            'nutrition_raw': 'Constituintes Analíticos: Humidade 74,5%. Proteína bruta 13%. Matéria gorda bruta 7%. Cinza bruta 3%,...',
            'price': 1.4,
            'unit_price_kg': 16.47,
            'retailer': 'ZU',
            'pdp_url': 'https://www.zu.pt/products/comida-humida-para-gato-junior-mousse-gatinhos-vitela-purina-gourmet-gold-5304997'
        }
        
        # Reconcile both
        reconciled_cont = reconcile_product_evidence(cont_product, 'Continente', matches_config=matches_config)
        reconciled_zu = reconcile_product_evidence(zu_product, 'ZU', matches_config=matches_config)
        
        # Both should be reconciled
        self.assertTrue(reconciled_cont['is_reconciled'])
        self.assertTrue(reconciled_zu['is_reconciled'])
        self.assertEqual(reconciled_cont['formulation_id'], reconciled_zu['formulation_id'])
        
        # Score both (they should have the same nutritional data now)
        scored_cont, _ = score_wet_product(reconciled_cont)
        scored_zu, _ = score_wet_product(reconciled_zu)
        
        # Both should be ranked (with verified data)
        self.assertTrue(scored_cont['is_ranked'])
        self.assertTrue(scored_zu['is_ranked'])
        
        # Scores should be the same (same formulation)
        self.assertEqual(scored_cont['score'], scored_zu['score'])
        
        # But value ratios should differ (different prices)
        # Since we haven't attached shared assessment yet, they'll have their own value ratios
        # This is expected before the shared assessment step

    def test_gourmet_gold_junior_matches_verified(self):
        """Test that the Gourmet Gold Junior pair is in the matches config."""
        from src.scoring.reconciliation import load_product_matches, find_formulation_id
        
        matches_config = load_product_matches()
        
        # Check that the formulation exists
        self.assertIn('gourmet_gold_junior_veal_mousse_wet', matches_config)
        
        # Check that both retailers are mapped
        gg_junior = matches_config['gourmet_gold_junior_veal_mousse_wet']
        self.assertIn('continente', gg_junior['retailer_matches'])
        self.assertIn('zu', gg_junior['retailer_matches'])
        
        # Check that PID 5304997 is mapped for both
        self.assertIn('5304997', gg_junior['retailer_matches']['continente'])
        self.assertIn('5304997', gg_junior['retailer_matches']['zu'])
        
        # Check that find_formulation_id works
        fid = find_formulation_id('continente', '5304997', matches_config=matches_config)
        self.assertEqual(fid, 'gourmet_gold_junior_veal_mousse_wet')
        
        fid = find_formulation_id('zu', '5304997', matches_config=matches_config)
        self.assertEqual(fid, 'gourmet_gold_junior_veal_mousse_wet')


    def test_reconciliation_reversibility_preserves_raw_data(self):
        """Reconciliation must preserve raw scraped observations for full reversibility."""
        from src.scoring.reconciliation import reconcile_product_evidence
        
        product = {
            'pid': '5304997',
            'name': 'Original Product Name',
            'ingredients': 'Original Raw Ingredients List',
            'nutrition_raw': 'Original Raw Nutrition 9%',
            'classification': 'Completo',
            'retailer': 'continente'
        }
        reconciled = reconcile_product_evidence(product, 'continente', matches_config=self.test_matches)
        
        self.assertTrue(reconciled['is_reconciled'])
        # Verified data applied
        self.assertIn('57%, dos quais 4% Vitela', reconciled['ingredients'])
        # Original data preserved
        self.assertEqual(reconciled['raw_ingredients'], 'Original Raw Ingredients List')
        self.assertEqual(reconciled['raw_nutrition_raw'], 'Original Raw Nutrition 9%')
        self.assertEqual(reconciled['raw_classification'], 'Completo')

    def test_find_formulation_by_pdp_url(self):
        """Formulation matching must work with full PDP URLs as well as PIDs."""
        from src.scoring.reconciliation import find_formulation_id
        
        matches_with_url = {
            'form_url_test': {
                'retailer_matches': {
                    'zooplus': ['/shop/gato/enlatados_gato/feringa/pure_meat/12345']
                }
            }
        }
        fid = find_formulation_id(
            'zooplus', 
            pid='99999', 
            pdp_url='https://www.zooplus.pt/shop/gato/enlatados_gato/feringa/pure_meat/12345',
            matches_config=matches_with_url
        )
        self.assertEqual(fid, 'form_url_test')

    def test_material_conflict_gates_score_to_unranked(self):
        """Material conflicts across formulations must result in unranked status."""
        from src.scoring.reconciliation import (
            detect_material_conflict, 
            calculate_shared_score_for_formulation,
            attach_shared_assessment
        )
        
        # Test direct conflict detection
        retailer_obs = {
            'classification': 'complementar', # Contradicts complete
            'ingredients': 'Frango e cereais com açúcar', # Contradicts verified sugar-free
            'nutrition_raw': 'Proteína 6.0%' # Verified is 14% (>3% divergence)
        }
        verified = {
            'classification': 'complete',
            'ingredients': 'Frango 70%',
            'nutrition_raw': 'Proteína 14.0%'
        }
        is_mat, reasons = detect_material_conflict(retailer_obs, verified)
        self.assertTrue(is_mat)
        self.assertTrue(len(reasons) >= 2)
        
        # Test unresolved conflict config
        conflict_config = {
            'conflict_form': {
                'unresolved_conflict': True,
                'verified': {
                    'classification': 'complete',
                    'ingredients': 'Frango 70%',
                    'nutrition_raw': 'Proteína 12% Gordura 6% Humidade 80% Cinza 2% Fibra 0.5%'
                },
                'retailer_matches': {'continente': ['conf_1']}
            }
        }
        assessment = calculate_shared_score_for_formulation('conflict_form', matches_config=conflict_config)
        self.assertFalse(assessment['is_ranked'])
        self.assertIsNone(assessment['score'])
        self.assertIn('material_conflict_unresolved', assessment['unranked_reasons'])

    def test_attach_shared_assessment_to_minified_dicts(self):
        """Shared assessment must properly update minified data keys (s, t, vr, ir, fid, rec, conf)."""
        from src.scoring.reconciliation import attach_shared_assessment
        
        minified_products = [
            {
                'id': '5304997',
                'n': 'Minified Test Product',
                'b': 'TestBrand',
                'p': 2.0,
                'pkg': 10.0,
                'r': 'continente',
                's': None,
                't': 'Unranked',
                'vr': None,
                'ir': False,
                'ur': ['missing_data']
            }
        ]
        
        updated = attach_shared_assessment(minified_products, category='wet', matches_config=self.test_matches)
        p = updated[0]
        self.assertEqual(p['fid'], 'gourmet_gold_junior_veal_mousse_wet')
        self.assertTrue(p['rec'])
        self.assertFalse(p['conf'])

if __name__ == '__main__':
    unittest.main()

import os
import tempfile
import unittest
from src.pipeline.quality_gate import validate_candidate_dataset, extract_dataset_summary
from src.pipeline.manifest import (
    load_manifest, save_manifest, generate_manifest_csv_rows,
    get_manifest_path, get_manifest_csv_path
)

class TestLitterPipelineAndQualityGates(unittest.TestCase):

    def test_litter_measurement_threshold(self):
        """Quality gate must reject litter candidate if >50% lack volume or weight."""
        # 10 products, only 3 have measurements -> 30% coverage < 50% threshold
        candidates = [
            {'pid': f'p_{i}', 'name': f'Litter {i}', 'price': 5.0, 'volume_l': 10.0 if i < 3 else None, 'weight_kg': None}
            for i in range(10)
        ]
        is_valid, reasons = validate_candidate_dataset(
            candidate_products=candidates,
            dataset_key='continente_litter',
            last_accepted_entry=None,
            is_limited_run=False,
            allow_partial=False
        )
        self.assertFalse(is_valid)
        self.assertTrue(any('Litter measurement failure' in r for r in reasons))

    def test_litter_quality_gate_drop_rejection(self):
        """Unexpected drop exceeding 30% must be rejected."""
        last_accepted = {'product_count': 30}
        # current is only 15 (50% drop)
        candidates = [
            {'pid': f'p_{i}', 'name': f'Litter {i}', 'price': 5.0, 'volume_l': 10.0}
            for i in range(15)
        ]
        is_valid, reasons = validate_candidate_dataset(
            candidate_products=candidates,
            dataset_key='zu_litter',
            last_accepted_entry=last_accepted,
            is_limited_run=False,
            allow_partial=False
        )
        self.assertFalse(is_valid)
        self.assertTrue(any('Unexpected catalog drop' in r for r in reasons))

    def test_litter_allow_partial_passes_limited_run(self):
        """Limited run with --allow-partial passes quality gate."""
        candidates = [
            {'pid': 'p_1', 'name': 'Litter 1', 'price': 5.0, 'volume_l': 10.0}
        ]
        is_valid, reasons = validate_candidate_dataset(
            candidate_products=candidates,
            dataset_key='zooplus_litter',
            last_accepted_entry={'product_count': 50},
            is_limited_run=True,
            allow_partial=True
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(reasons), 0)

    def test_extract_dataset_summary_litter_metrics(self):
        """extract_dataset_summary must compute avg_score and substrate_breakdown for litter."""
        products = [
            {'name': 'L1', 'is_ranked': True, 'score': 90, 'material': 'Tofu / Vegetal'},
            {'name': 'L2', 'is_ranked': True, 'score': 70, 'material': 'Bentonite'},
            {'name': 'L3', 'is_ranked': False, 'score': None, 'material': 'Bentonite'}
        ]
        summary = extract_dataset_summary(products, is_partial=False, dataset_key='continente_litter')
        self.assertEqual(summary['product_count'], 3)
        self.assertEqual(summary['ranked_count'], 2)
        self.assertEqual(summary['unranked_count'], 1)
        self.assertEqual(summary['avg_score'], 80.0)
        self.assertEqual(summary['substrate_breakdown']['Tofu / Vegetal'], 1)
        self.assertEqual(summary['substrate_breakdown']['Bentonite'], 2)

    def test_manifest_csv_export(self):
        """save_manifest must create both manifest.json and manifest.csv."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest = load_manifest(tmp_dir)
            manifest['datasets']['test_litter'] = {
                'status': 'accepted',
                'generation_id': 'gen_test',
                'product_count': 25,
                'ranked_count': 20,
                'unranked_count': 5,
                'avg_score': 76.5,
                'is_partial': False
            }
            save_manifest(tmp_dir, manifest)

            json_path = get_manifest_path(tmp_dir)
            csv_path = get_manifest_csv_path(tmp_dir)

            self.assertTrue(os.path.exists(json_path))
            self.assertTrue(os.path.exists(csv_path))

            with open(csv_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn('test_litter', content)
                self.assertIn('76.5', content)
                self.assertIn('dataset_key,status,generation_id', content)

if __name__ == '__main__':
    unittest.main()

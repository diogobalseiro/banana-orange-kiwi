import os
import tempfile
import unittest
import shutil
import csv
from datetime import datetime, timezone
from src.pipeline.lock import RefreshLock, RefreshLockError
from src.pipeline.manifest import (
    load_manifest, save_manifest, update_manifest_dataset, record_rejection,
    atomic_replace, atomic_save_json, atomic_save_csv, save_snapshot,
    prune_old_snapshots, get_manifest_path, load_last_rejection
)
from src.pipeline.quality_gate import (
    validate_candidate_dataset, extract_dataset_summary
)

class TestMilestoneC(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.lock_path = os.path.join(self.test_dir, ".refresh.lock")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_refresh_lock_concurrency(self):
        """RefreshLock must reject overlapping writers."""
        with RefreshLock(self.lock_path, timeout=0.1) as lock1:
            self.assertTrue(os.path.exists(self.lock_path))
            # Second attempt should raise RefreshLockError
            lock2 = RefreshLock(self.lock_path, timeout=0.1)
            with self.assertRaises(RefreshLockError):
                lock2.acquire()

        # After exiting, lock should be released
        with RefreshLock(self.lock_path, timeout=0.1) as lock3:
            self.assertIsNotNone(lock3)

    def test_quality_gate_blocks_empty_catalog(self):
        """Zero products after nonempty baseline must be rejected."""
        last_accepted = {'product_count': 100, 'valid_ingredients_count': 90, 'valid_nutrition_count': 80}
        candidate = []
        is_valid, reasons = validate_candidate_dataset(candidate, 'continente_wet', last_accepted)
        self.assertFalse(is_valid)
        self.assertTrue(any('Zero products' in r for r in reasons))

    def test_quality_gate_blocks_max_pages_without_override(self):
        """Deliberate page-limited run must be rejected from replacing production without override."""
        last_accepted = {'product_count': 100, 'valid_ingredients_count': 90, 'valid_nutrition_count': 80}
        candidate = [{'pid': '1', 'name': 'P1', 'ingredients': 'Frango', 'nutrition_raw': 'Proteina 10%'}]
        is_valid, reasons = validate_candidate_dataset(
            candidate, 'continente_wet', last_accepted, is_limited_run=True, allow_partial=False
        )
        self.assertFalse(is_valid)
        self.assertTrue(any('--allow-partial' in r for r in reasons))

        # With override, it passes
        is_valid_allowed, _ = validate_candidate_dataset(
            candidate, 'continente_wet', last_accepted, is_limited_run=True, allow_partial=True
        )
        self.assertTrue(is_valid_allowed)

    def test_quality_gate_blocks_catastrophic_drop(self):
        """A >30% sudden product drop must be rejected."""
        last_accepted = {'product_count': 100, 'valid_ingredients_count': 90, 'valid_nutrition_count': 80}
        # 50 products = 50% drop
        candidate = [{'pid': str(i), 'name': f'P{i}', 'ingredients': 'Frango', 'nutrition_raw': 'Proteina 10%'} for i in range(50)]
        is_valid, reasons = validate_candidate_dataset(candidate, 'continente_wet', last_accepted)
        self.assertFalse(is_valid)
        self.assertTrue(any('Unexpected catalog drop' in r for r in reasons))

    def test_quality_gate_blocks_widespread_field_loss(self):
        """Sudden loss of ingredients or nutrition declarations must be rejected."""
        last_accepted = {'product_count': 100, 'valid_ingredients_count': 90, 'valid_nutrition_count': 90}
        # 100 products, but only 10 have nutrition
        candidate = [{'pid': str(i), 'name': f'P{i}', 'ingredients': 'Frango', 'nutrition_raw': ('Proteina 10%' if i < 10 else '')} for i in range(100)]
        is_valid, reasons = validate_candidate_dataset(candidate, 'continente_wet', last_accepted)
        self.assertFalse(is_valid)
        self.assertTrue(any('Widespread nutrition field loss' in r for r in reasons))

    def test_quality_gate_blocks_invalid_structure(self):
        """Observations lacking basic identity (pid or name) must be rejected."""
        last_accepted = {'product_count': 50, 'valid_ingredients_count': 45, 'valid_nutrition_count': 45}
        # 50 products, but 20 lack pid/name
        candidate = [{'pid': (str(i) if i < 30 else None), 'name': (f'P{i}' if i < 30 else None), 'ingredients': 'Frango', 'nutrition_raw': 'Proteina 10%'} for i in range(50)]
        is_valid, reasons = validate_candidate_dataset(candidate, 'continente_wet', last_accepted)
        self.assertFalse(is_valid)
        self.assertTrue(any('Structurally invalid observations' in r for r in reasons))

    def test_quality_gate_blocks_widespread_fetch_errors(self):
        """Blocked or exhausted detail requests must be rejected."""
        last_accepted = {'product_count': 50, 'valid_ingredients_count': 45, 'valid_nutrition_count': 45}
        # 50 products, but 35 failed with fetch_error
        candidate = [{'pid': str(i), 'name': f'P{i}', 'fetch_error': ('HTTP 429' if i < 35 else None), 'ingredients': 'Frango', 'nutrition_raw': 'Proteina 10%'} for i in range(50)]
        is_valid, reasons = validate_candidate_dataset(candidate, 'continente_wet', last_accepted)
        self.assertFalse(is_valid)
        self.assertTrue(any('Widespread fetch errors' in r for r in reasons))

    def test_quality_gate_blocks_failed_scraper_status(self):
        """A failed crawl status must not pass the gate."""
        candidate = [{'pid': '1', 'name': 'P1', 'ingredients': 'Frango', 'nutrition_raw': 'Proteina 10%'}]
        is_valid, reasons = validate_candidate_dataset(
            candidate, 'continente_wet', None, scraper_status="FAILED: Connection reset"
        )
        self.assertFalse(is_valid)
        self.assertTrue(any('Catalog crawl did not complete normally' in r for r in reasons))

    def test_atomic_manifest_update(self):
        """Manifest updates and replaces files atomically."""
        manifest = load_manifest(self.test_dir)
        self.assertEqual(manifest['schema_version'], '1.0')

        summary = extract_dataset_summary([{'pid': '1', 'name': 'P1', 'ingredients': 'x', 'nutrition_raw': 'y', 'is_ranked': True}])
        update_manifest_dataset(manifest, 'continente_wet', summary, 'gen_20261027')

        self.assertIn('continente_wet', manifest['datasets'])
        self.assertEqual(manifest['datasets']['continente_wet']['product_count'], 1)

        # Atomic save
        manifest_path = get_manifest_path(self.test_dir)
        atomic_save_json(manifest_path, manifest)
        reloaded = load_manifest(self.test_dir)
        self.assertEqual(reloaded['active_generation_id'], 'gen_20261027')

    def test_rejection_recording_and_manifest_warning(self):
        """Rejected candidate logs diagnostics and updates manifest with warning."""
        summary = {'product_count': 0}
        record_rejection(self.test_dir, 'continente_wet', summary, 'Empty catalog')

        rejection = load_last_rejection(self.test_dir)
        self.assertIsNotNone(rejection)
        self.assertEqual(rejection['dataset_key'], 'continente_wet')
        self.assertEqual(rejection['rejection_reason'], 'Empty catalog')

        manifest = load_manifest(self.test_dir)
        self.assertIn('last_rejection', manifest)
        self.assertEqual(manifest['last_rejection']['dataset_key'], 'continente_wet')

    def test_atomic_save_csv(self):
        """CSV files are written cleanly and atomically."""
        csv_path = os.path.join(self.test_dir, "test.csv")
        rows = [
            {'pid': '101', 'name': 'P1', 'is_ranked': True, 'score': 85},
            {'pid': '102', 'name': 'P2', 'is_ranked': False, 'score': None}
        ]
        fields = ['pid', 'name', 'is_ranked', 'score']
        atomic_save_csv(csv_path, rows, fields)

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 2)
            self.assertEqual(reader[0]['pid'], '101')
            self.assertEqual(reader[0]['is_ranked'], 'true')
            self.assertEqual(reader[1]['score'], '')

    def test_snapshot_creation_and_pruning(self):
        """Snapshots are stored and older ones pruned safely."""
        snap_rel = save_snapshot(self.test_dir, 'continente_wet', 'gen_1', [{'pid': '1'}])
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, snap_rel)))

        save_snapshot(self.test_dir, 'continente_wet', 'gen_2', [{'pid': '2'}])
        save_snapshot(self.test_dir, 'continente_wet', 'gen_3', [{'pid': '3'}])

        snapshots_dir = os.path.join(self.test_dir, "snapshots")
        self.assertEqual(len(os.listdir(snapshots_dir)), 3)

        # Keep only gen_2 and gen_3
        prune_old_snapshots(self.test_dir, ['gen_2', 'gen_3'])
        remaining = os.listdir(snapshots_dir)
        self.assertEqual(len(remaining), 2)
        self.assertFalse(any('gen_1' in f for f in remaining))
        self.assertTrue(any('gen_2' in f for f in remaining))
        self.assertTrue(any('gen_3' in f for f in remaining))

if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""
Cat Food Dashboard - Refresh & Build Runner
Usage:
    python refresh.py --retailer continente --type all
    python refresh.py --retailer continente --type wet
    python refresh.py --retailer continente --type dry
    python refresh.py --skip-scrape  # Only re-score and re-build HTML
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

# Ensure src is in python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.scrapers.continente import ContinenteScraper
from src.scrapers.zu import ZUScraper
from src.scrapers.zooplus import ZooplusScraper
from src.scoring.wet_scorer import score_wet_product
from src.scoring.dry_scorer import score_dry_product
from src.scoring.reconciliation import (
    load_product_matches,
    reconcile_batch,
    attach_shared_assessment,
    group_by_formulation
)
from src.builder.build_site import generate_html, load_data
from src.pipeline.lock import RefreshLock, RefreshLockError
from src.pipeline.manifest import (
    load_manifest,
    save_manifest,
    update_manifest_dataset,
    record_rejection,
    atomic_save_json,
    atomic_save_csv,
    save_snapshot,
    prune_old_snapshots
)
from src.pipeline.quality_gate import (
    validate_candidate_dataset,
    extract_dataset_summary
)

SCRAPERS = {
    'continente': ContinenteScraper,
    'zu': ZUScraper,
    'zooplus': ZooplusScraper
}

WET_CSV_FIELDS = [
    'pid', 'name', 'brand', 'retailer', 'price', 'unit_price_kg', 'classification',
    'is_kitten', 'is_ranked', 'score', 'tier', 'value_ratio', 'has_sugar', 'has_grains',
    'has_veg_protein', 'has_organs', 'has_carrageenan', 'has_taurine', 'unranked_reasons',
    'pdp_url', 'formulation_id', 'is_reconciled'
]

DRY_CSV_FIELDS = [
    'pid', 'name', 'brand', 'retailer', 'price', 'unit_price_kg', 'is_kitten', 'is_sterilised',
    'is_ranked', 'score', 'tier', 'value_ratio', 'is_grain_free', 'is_fractionated',
    'has_corn_gluten', 'has_colorants', 'unranked_reasons', 'pdp_url',
    'formulation_id', 'is_reconciled'
]

def run_wet_pipeline(retailer_name, scraper, data_dir, max_pages=None, allow_partial=False, manifest=None, generation_id=None):
    if manifest is None:
        manifest = load_manifest(data_dir)
    if generation_id is None:
        generation_id = f"gen_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    dataset_key = f"{retailer_name}_wet"
    print(f"\n==========================================")
    print(f"  Starting WET Food Pipeline ({retailer_name})")
    print(f"==========================================")

    scraper_status = "COMPLETED"
    raw_products = []
    try:
        raw_products = scraper.scrape_wet(max_pages=max_pages)
    except Exception as e:
        scraper_status = f"FAILED: {e}"
        print(f"❌ [Scraper Error] {retailer_name} wet food scrape failed: {e}")

    # Load product matches configuration
    matches_config = load_product_matches()
    
    # Step 1: Reconcile products with verified formulations
    print(f"[Reconciliation] Matching {len(raw_products)} products against {len(matches_config)} formulations...")
    reconciled_products, reconciliation_summary = reconcile_batch(
        raw_products, retailer_name, matches_config
    )
    
    matched_count = reconciliation_summary.get('matched_count', 0)
    print(f"[Reconciliation] {matched_count} products matched to verified formulations, {reconciliation_summary.get('unmatched_count', 0)} unmatched.")
    
    # Step 2: Score products (with reconciled data)
    scored_full = []
    minified = []
    for p in reconciled_products:
        p_full, p_mini = score_wet_product(p)
        if p_full is None or p_mini is None:
            continue
        scored_full.append(p_full)
        minified.append(p_mini)

    # Step 3: Group by formulation and attach shared assessments
    print(f"[Reconciliation] Attaching shared assessments to matched formulations...")
    scored_full = attach_shared_assessment(scored_full, category='wet')
    minified = attach_shared_assessment(minified, category='wet')

    # Sort by ranked status desc, score desc, then value ratio desc
    scored_full.sort(key=lambda x: (1 if x.get('is_ranked') else 0, x.get('score') or 0, x.get('value_ratio') or 0.0), reverse=True)
    minified.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)

    # Quality Gate Verification
    is_limited = (max_pages is not None)
    last_accepted = manifest.get("datasets", {}).get(dataset_key)
    is_valid, reasons = validate_candidate_dataset(
        candidate_products=scored_full,
        dataset_key=dataset_key,
        last_accepted_entry=last_accepted,
        is_limited_run=is_limited,
        allow_partial=allow_partial,
        scraper_status=scraper_status
    )

    if not is_valid:
        reason_str = "; ".join(reasons)
        summary = extract_dataset_summary(scored_full, is_partial=is_limited)
        record_rejection(data_dir, dataset_key, summary, reason_str, manifest=manifest)
        print(f"❌ [Quality Gate] Candidate REJECTED for {dataset_key}: {reason_str}")
        print(f"⚠️ [Quality Gate] Retaining previous accepted snapshot for {dataset_key}.")
        return None

    # Quality Gate Passed: Atomic publication
    full_path = os.path.join(data_dir, f"{retailer_name}_wet_full.json")
    mini_path = os.path.join(data_dir, f"{retailer_name}_wet.json")
    csv_path = os.path.join(data_dir, f"{retailer_name}_wet.csv")

    atomic_save_json(full_path, scored_full)
    atomic_save_json(mini_path, minified)
    atomic_save_csv(csv_path, scored_full, WET_CSV_FIELDS)

    snapshot_rel = save_snapshot(data_dir, dataset_key, generation_id, minified)
    summary = extract_dataset_summary(scored_full, is_partial=is_limited)
    summary["snapshot_file"] = snapshot_rel
    summary["file_mini"] = f"{retailer_name}_wet.json"
    summary["file_full"] = f"{retailer_name}_wet_full.json"
    summary["file_csv"] = f"{retailer_name}_wet.csv"

    update_manifest_dataset(manifest, dataset_key, summary, generation_id)
    save_manifest(data_dir, manifest)
    prune_old_snapshots(data_dir, [manifest.get("active_generation_id"), manifest.get("previous_generation_id")])

    ranked_count = sum(1 for x in minified if x.get('ir'))
    unranked_count = len(minified) - ranked_count
    print(f"[Pipeline] Wet food complete: {len(minified)} products processed ({ranked_count} ranked, {unranked_count} unranked).")
    return minified

def run_dry_pipeline(retailer_name, scraper, data_dir, max_pages=None, allow_partial=False, manifest=None, generation_id=None):
    if manifest is None:
        manifest = load_manifest(data_dir)
    if generation_id is None:
        generation_id = f"gen_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    dataset_key = f"{retailer_name}_dry"
    print(f"\n==========================================")
    print(f"  Starting DRY Food Pipeline ({retailer_name})")
    print(f"==========================================")

    scraper_status = "COMPLETED"
    raw_products = []
    try:
        raw_products = scraper.scrape_dry(max_pages=max_pages)
    except Exception as e:
        scraper_status = f"FAILED: {e}"
        print(f"❌ [Scraper Error] {retailer_name} dry food scrape failed: {e}")

    # Load product matches configuration
    matches_config = load_product_matches()
    
    # Step 1: Reconcile products with verified formulations
    print(f"[Reconciliation] Matching {len(raw_products)} products against {len(matches_config)} formulations...")
    reconciled_products, reconciliation_summary = reconcile_batch(
        raw_products, retailer_name, matches_config
    )
    
    matched_count = reconciliation_summary.get('matched_count', 0)
    print(f"[Reconciliation] {matched_count} products matched to verified formulations, {reconciliation_summary.get('unmatched_count', 0)} unmatched.")
    
    # Step 2: Score products (with reconciled data)
    scored_full = []
    minified = []
    for p in reconciled_products:
        p_full, p_mini = score_dry_product(p)
        if p_full is None or p_mini is None:
            continue
        scored_full.append(p_full)
        minified.append(p_mini)

    # Step 3: Group by formulation and attach shared assessments
    print(f"[Reconciliation] Attaching shared assessments to matched formulations...")
    scored_full = attach_shared_assessment(scored_full, category='dry')
    minified = attach_shared_assessment(minified, category='dry')

    scored_full.sort(key=lambda x: (1 if x.get('is_ranked') else 0, x.get('score') or 0, x.get('value_ratio') or 0.0), reverse=True)
    minified.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)

    # Quality Gate Verification
    is_limited = (max_pages is not None)
    last_accepted = manifest.get("datasets", {}).get(dataset_key)
    is_valid, reasons = validate_candidate_dataset(
        candidate_products=scored_full,
        dataset_key=dataset_key,
        last_accepted_entry=last_accepted,
        is_limited_run=is_limited,
        allow_partial=allow_partial,
        scraper_status=scraper_status
    )

    if not is_valid:
        reason_str = "; ".join(reasons)
        summary = extract_dataset_summary(scored_full, is_partial=is_limited)
        record_rejection(data_dir, dataset_key, summary, reason_str, manifest=manifest)
        print(f"❌ [Quality Gate] Candidate REJECTED for {dataset_key}: {reason_str}")
        print(f"⚠️ [Quality Gate] Retaining previous accepted snapshot for {dataset_key}.")
        return None

    # Quality Gate Passed: Atomic publication
    full_path = os.path.join(data_dir, f"{retailer_name}_dry_full.json")
    mini_path = os.path.join(data_dir, f"{retailer_name}_dry.json")
    csv_path = os.path.join(data_dir, f"{retailer_name}_dry.csv")

    atomic_save_json(full_path, scored_full)
    atomic_save_json(mini_path, minified)
    atomic_save_csv(csv_path, scored_full, DRY_CSV_FIELDS)

    snapshot_rel = save_snapshot(data_dir, dataset_key, generation_id, minified)
    summary = extract_dataset_summary(scored_full, is_partial=is_limited)
    summary["snapshot_file"] = snapshot_rel
    summary["file_mini"] = f"{retailer_name}_dry.json"
    summary["file_full"] = f"{retailer_name}_dry_full.json"
    summary["file_csv"] = f"{retailer_name}_dry.csv"

    update_manifest_dataset(manifest, dataset_key, summary, generation_id)
    save_manifest(data_dir, manifest)
    prune_old_snapshots(data_dir, [manifest.get("active_generation_id"), manifest.get("previous_generation_id")])

    ranked_count = sum(1 for x in minified if x.get('ir'))
    unranked_count = len(minified) - ranked_count
    print(f"[Pipeline] Dry food complete: {len(minified)} products processed ({ranked_count} ranked, {unranked_count} unranked).")
    return minified

def rescore_cached_data(data_dir, manifest=None, generation_id=None):
    print("[Scorer] Re-scoring existing cached datasets with updated rules and reconciliation...")
    if manifest is None:
        manifest = load_manifest(data_dir)
    if generation_id is None:
        generation_id = f"gen_rescore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    matches_config = load_product_matches()

    for ret in ['continente', 'zu', 'zooplus']:
        # Wet food
        dataset_key_wet = f"{ret}_wet"
        full_wet_path = os.path.join(data_dir, f"{ret}_wet_full.json")
        if os.path.exists(full_wet_path):
            with open(full_wet_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            # Reconcile
            reconciled, summary = reconcile_batch(raw, ret, matches_config)
            print(f"  [Reconciliation] {ret} wet: {summary.get('matched_count', 0)} matched, {summary.get('unmatched_count', 0)} unmatched.")
            
            scored_full = []
            minified = []
            for p in reconciled:
                p_full, p_mini = score_wet_product(p)
                if p_full is None or p_mini is None:
                    continue
                scored_full.append(p_full)
                minified.append(p_mini)
            
            # Attach shared assessments
            scored_full = attach_shared_assessment(scored_full, category='wet')
            minified = attach_shared_assessment(minified, category='wet')
            
            scored_full.sort(key=lambda x: (1 if x.get('is_ranked') else 0, x.get('score') or 0, x.get('value_ratio') or 0.0), reverse=True)
            minified.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)

            atomic_save_json(full_wet_path, scored_full)
            atomic_save_json(os.path.join(data_dir, f"{ret}_wet.json"), minified)
            atomic_save_csv(os.path.join(data_dir, f"{ret}_wet.csv"), scored_full, WET_CSV_FIELDS)

            prev_entry = manifest.get("datasets", {}).get(dataset_key_wet, {})
            retrieved_at = prev_entry.get("retrieved_at", "2026-10-27T00:00:00Z")
            snapshot_rel = save_snapshot(data_dir, dataset_key_wet, generation_id, minified)

            ds_summary = extract_dataset_summary(scored_full, is_partial=prev_entry.get("is_partial", False))
            ds_summary["retrieved_at"] = retrieved_at
            ds_summary["rescored_at"] = datetime.now(timezone.utc).isoformat()
            ds_summary["snapshot_file"] = snapshot_rel
            ds_summary["file_mini"] = f"{ret}_wet.json"
            ds_summary["file_full"] = f"{ret}_wet_full.json"
            ds_summary["file_csv"] = f"{ret}_wet.csv"

            update_manifest_dataset(manifest, dataset_key_wet, ds_summary, generation_id)
            r_cnt = sum(1 for x in minified if x.get('ir'))
            u_cnt = len(minified) - r_cnt
            print(f"  [Scorer] {ret} wet food: {len(minified)} products ({r_cnt} ranked, {u_cnt} unranked).")

        # Dry food
        dataset_key_dry = f"{ret}_dry"
        full_dry_path = os.path.join(data_dir, f"{ret}_dry_full.json")
        if os.path.exists(full_dry_path):
            with open(full_dry_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            # Reconcile
            reconciled, summary = reconcile_batch(raw, ret, matches_config)
            print(f"  [Reconciliation] {ret} dry: {summary.get('matched_count', 0)} matched, {summary.get('unmatched_count', 0)} unmatched.")
            
            scored_full = []
            minified = []
            for p in reconciled:
                p_full, p_mini = score_dry_product(p)
                if p_full is None or p_mini is None:
                    continue
                scored_full.append(p_full)
                minified.append(p_mini)
            
            # Attach shared assessments
            scored_full = attach_shared_assessment(scored_full, category='dry')
            minified = attach_shared_assessment(minified, category='dry')
            
            scored_full.sort(key=lambda x: (1 if x.get('is_ranked') else 0, x.get('score') or 0, x.get('value_ratio') or 0.0), reverse=True)
            minified.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)

            atomic_save_json(full_dry_path, scored_full)
            atomic_save_json(os.path.join(data_dir, f"{ret}_dry.json"), minified)
            atomic_save_csv(os.path.join(data_dir, f"{ret}_dry.csv"), scored_full, DRY_CSV_FIELDS)

            prev_entry = manifest.get("datasets", {}).get(dataset_key_dry, {})
            retrieved_at = prev_entry.get("retrieved_at", "2026-10-27T00:00:00Z")
            snapshot_rel = save_snapshot(data_dir, dataset_key_dry, generation_id, minified)

            ds_summary = extract_dataset_summary(scored_full, is_partial=prev_entry.get("is_partial", False))
            ds_summary["retrieved_at"] = retrieved_at
            ds_summary["rescored_at"] = datetime.now(timezone.utc).isoformat()
            ds_summary["snapshot_file"] = snapshot_rel
            ds_summary["file_mini"] = f"{ret}_dry.json"
            ds_summary["file_full"] = f"{ret}_dry_full.json"
            ds_summary["file_csv"] = f"{ret}_dry.csv"

            update_manifest_dataset(manifest, dataset_key_dry, ds_summary, generation_id)
            r_cnt = sum(1 for x in minified if x.get('ir'))
            u_cnt = len(minified) - r_cnt
            print(f"  [Scorer] {ret} dry food: {len(minified)} products ({r_cnt} ranked, {u_cnt} unranked).")

    save_manifest(data_dir, manifest)
    prune_old_snapshots(data_dir, [manifest.get("active_generation_id"), manifest.get("previous_generation_id")])
    return manifest

def main():
    parser = argparse.ArgumentParser(description="Refresh and build Cat Food Rankings")
    parser.add_argument('--retailer', choices=['continente', 'zu', 'zooplus', 'all'], default='continente', help="Retailer to scrape")
    parser.add_argument('--type', choices=['wet', 'dry', 'all'], default='all', help="Food category to refresh")
    parser.add_argument('--max-pages', type=int, default=None, help="Limit catalog pagination (for quick test runs)")
    parser.add_argument('--allow-partial', action='store_true', help="Allow publication of partial/limited catalog scrape")
    parser.add_argument('--skip-scrape', action='store_true', help="Skip scraping and rebuild index.html from existing data")
    args = parser.parse_args()

    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)
    lock_path = os.path.join(data_dir, '.refresh.lock')

    try:
        with RefreshLock(lock_path):
            manifest = load_manifest(data_dir)
            generation_id = f"gen_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            failed_datasets = []

            if not args.skip_scrape:
                target_retailers = ['continente', 'zu', 'zooplus'] if args.retailer == 'all' else [args.retailer]

                for ret in target_retailers:
                    scraper_cls = SCRAPERS.get(ret)
                    if not scraper_cls:
                        raise NotImplementedError(f"Scraper for {ret} is not available.")
                    scraper = scraper_cls()

                    if args.type in ['wet', 'all']:
                        res = run_wet_pipeline(
                            ret, scraper, data_dir, 
                            max_pages=args.max_pages, 
                            allow_partial=args.allow_partial,
                            manifest=manifest, 
                            generation_id=generation_id
                        )
                        if res is None:
                            failed_datasets.append(f"{ret}_wet")

                    if args.type in ['dry', 'all']:
                        res = run_dry_pipeline(
                            ret, scraper, data_dir, 
                            max_pages=args.max_pages, 
                            allow_partial=args.allow_partial,
                            manifest=manifest, 
                            generation_id=generation_id
                        )
                        if res is None:
                            failed_datasets.append(f"{ret}_dry")
            else:
                manifest = rescore_cached_data(data_dir, manifest=manifest, generation_id=generation_id)

            # Rebuild unified HTML site
            print("\n[Builder] Recompiling unified GitHub Pages dashboard...")
            wet_products, dry_products = load_data(data_dir, manifest=manifest)
            index_html = os.path.join(BASE_DIR, 'index.html')
            generate_html(wet_products, dry_products, index_html, manifest_data=manifest)

            if failed_datasets:
                print(f"\n❌ Refresh ended with candidate rejections: {failed_datasets}")
                print(f"⚠️ Previously accepted snapshots were preserved in the published catalog.")
                sys.exit(1)
            else:
                print(f"✨ Refresh pipeline finished successfully! Open: {index_html}\n")
    except RefreshLockError as e:
        print(f"❌ Concurrency Lock Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

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

SCRAPERS = {
    'continente': ContinenteScraper,
    'zu': ZUScraper,
    'zooplus': ZooplusScraper
}

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_csv(filepath, rows, fieldnames):
    if not rows:
        return
    cleaned_rows = []
    for r in rows:
        cleaned = {}
        for f in fieldnames:
            v = r.get(f)
            if v is None:
                cleaned[f] = ""
            elif isinstance(v, bool):
                cleaned[f] = "true" if v else "false"
            elif isinstance(v, list):
                cleaned[f] = "; ".join(str(item) for item in v)
            else:
                cleaned[f] = v
        cleaned_rows.append(cleaned)

    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(cleaned_rows)

def run_wet_pipeline(retailer_name, scraper, data_dir, max_pages=None):
    print(f"\n==========================================")
    print(f"  Starting WET Food Pipeline ({retailer_name})")
    print(f"==========================================")
    raw_products = scraper.scrape_wet(max_pages=max_pages)
    
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

    full_path = os.path.join(data_dir, f"{retailer_name}_wet_full.json")
    mini_path = os.path.join(data_dir, f"{retailer_name}_wet.json")
    csv_path = os.path.join(data_dir, f"{retailer_name}_wet.csv")

    save_json(full_path, scored_full)
    save_json(mini_path, minified)

    csv_fields = [
        'pid', 'name', 'brand', 'retailer', 'price', 'unit_price_kg', 'classification',
        'is_kitten', 'is_ranked', 'score', 'tier', 'value_ratio', 'has_sugar', 'has_grains',
        'has_veg_protein', 'has_organs', 'has_carrageenan', 'has_taurine', 'unranked_reasons',
        'pdp_url', 'formulation_id', 'is_reconciled'
    ]
    save_csv(csv_path, scored_full, csv_fields)

    ranked_count = sum(1 for x in minified if x.get('ir'))
    unranked_count = len(minified) - ranked_count
    print(f"[Pipeline] Wet food complete: {len(minified)} products processed ({ranked_count} ranked, {unranked_count} unranked).")
    return minified

def run_dry_pipeline(retailer_name, scraper, data_dir, max_pages=None):
    print(f"\n==========================================")
    print(f"  Starting DRY Food Pipeline ({retailer_name})")
    print(f"==========================================")
    raw_products = scraper.scrape_dry(max_pages=max_pages)
    
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
        scored_full.append(p_full)
        minified.append(p_mini)

    # Step 3: Group by formulation and attach shared assessments
    print(f"[Reconciliation] Attaching shared assessments to matched formulations...")
    scored_full = attach_shared_assessment(scored_full, category='dry')
    minified = attach_shared_assessment(minified, category='dry')

    scored_full.sort(key=lambda x: (1 if x.get('is_ranked') else 0, x.get('score') or 0, x.get('value_ratio') or 0.0), reverse=True)
    minified.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)

    full_path = os.path.join(data_dir, f"{retailer_name}_dry_full.json")
    mini_path = os.path.join(data_dir, f"{retailer_name}_dry.json")
    csv_path = os.path.join(data_dir, f"{retailer_name}_dry.csv")

    save_json(full_path, scored_full)
    save_json(mini_path, minified)

    csv_fields = [
        'pid', 'name', 'brand', 'retailer', 'price', 'unit_price_kg', 'is_kitten', 'is_sterilised',
        'is_ranked', 'score', 'tier', 'value_ratio', 'is_grain_free', 'is_fractionated',
        'has_corn_gluten', 'has_colorants', 'unranked_reasons', 'pdp_url',
        'formulation_id', 'is_reconciled'
    ]
    save_csv(csv_path, scored_full, csv_fields)

    ranked_count = sum(1 for x in minified if x.get('ir'))
    unranked_count = len(minified) - ranked_count
    print(f"[Pipeline] Dry food complete: {len(minified)} products processed ({ranked_count} ranked, {unranked_count} unranked).")
    return minified

def rescore_cached_data(data_dir):
    print("[Scorer] Re-scoring existing cached datasets with updated rules and reconciliation...")
    matches_config = load_product_matches()
    
    wet_csv_fields = [
        'pid', 'name', 'brand', 'retailer', 'price', 'unit_price_kg', 'classification',
        'is_kitten', 'is_ranked', 'score', 'tier', 'value_ratio', 'has_sugar', 'has_grains',
        'has_veg_protein', 'has_organs', 'has_carrageenan', 'has_taurine', 'unranked_reasons',
        'pdp_url', 'formulation_id', 'is_reconciled'
    ]
    dry_csv_fields = [
        'pid', 'name', 'brand', 'retailer', 'price', 'unit_price_kg', 'is_kitten', 'is_sterilised',
        'is_ranked', 'score', 'tier', 'value_ratio', 'is_grain_free', 'is_fractionated',
        'has_corn_gluten', 'has_colorants', 'unranked_reasons', 'pdp_url',
        'formulation_id', 'is_reconciled'
    ]

    for ret in ['continente', 'zu', 'zooplus']:
        # Wet food
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
            save_json(full_wet_path, scored_full)
            save_json(os.path.join(data_dir, f"{ret}_wet.json"), minified)
            save_csv(os.path.join(data_dir, f"{ret}_wet.csv"), scored_full, wet_csv_fields)
            r_cnt = sum(1 for x in minified if x.get('ir'))
            u_cnt = len(minified) - r_cnt
            print(f"  [Scorer] {ret} wet food: {len(minified)} products ({r_cnt} ranked, {u_cnt} unranked).")

        # Dry food
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
                scored_full.append(p_full)
                minified.append(p_mini)
            
            # Attach shared assessments
            scored_full = attach_shared_assessment(scored_full, category='dry')
            minified = attach_shared_assessment(minified, category='dry')
            
            scored_full.sort(key=lambda x: (1 if x.get('is_ranked') else 0, x.get('score') or 0, x.get('value_ratio') or 0.0), reverse=True)
            minified.sort(key=lambda x: (1 if x.get('ir') else 0, x.get('s') or 0, x.get('vr') or 0.0), reverse=True)
            save_json(full_dry_path, scored_full)
            save_json(os.path.join(data_dir, f"{ret}_dry.json"), minified)
            save_csv(os.path.join(data_dir, f"{ret}_dry.csv"), scored_full, dry_csv_fields)
            r_cnt = sum(1 for x in minified if x.get('ir'))
            u_cnt = len(minified) - r_cnt
            print(f"  [Scorer] {ret} dry food: {len(minified)} products ({r_cnt} ranked, {u_cnt} unranked).")

def main():
    parser = argparse.ArgumentParser(description="Refresh and build Cat Food Rankings")
    parser.add_argument('--retailer', choices=['continente', 'zu', 'zooplus', 'all'], default='continente', help="Retailer to scrape")
    parser.add_argument('--type', choices=['wet', 'dry', 'all'], default='all', help="Food category to refresh")
    parser.add_argument('--max-pages', type=int, default=None, help="Limit catalog pagination (for quick test runs)")
    parser.add_argument('--skip-scrape', action='store_true', help="Skip scraping and rebuild index.html from existing data")
    args = parser.parse_args()

    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)

    if not args.skip_scrape:
        target_retailers = ['continente', 'zu', 'zooplus'] if args.retailer == 'all' else [args.retailer]

        for ret in target_retailers:
            scraper_cls = SCRAPERS.get(ret)
            if not scraper_cls:
                raise NotImplementedError(f"Scraper for {ret} is not available.")
            scraper = scraper_cls()

            if args.type in ['wet', 'all']:
                run_wet_pipeline(ret, scraper, data_dir, max_pages=args.max_pages)

            if args.type in ['dry', 'all']:
                run_dry_pipeline(ret, scraper, data_dir, max_pages=args.max_pages)
    else:
        rescore_cached_data(data_dir)

    # Rebuild unified HTML site
    print("\n[Builder] Recompiling unified GitHub Pages dashboard...")
    wet_products, dry_products = load_data(data_dir)
    index_html = os.path.join(BASE_DIR, 'index.html')
    generate_html(wet_products, dry_products, index_html)
    print(f"✨ Refresh pipeline finished successfully! Open: {index_html}\n")

if __name__ == '__main__':
    main()

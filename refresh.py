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
from src.scoring.wet_scorer import score_wet_product
from src.scoring.dry_scorer import score_dry_product
from src.builder.build_site import generate_html, load_data

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_csv(filepath, rows, fieldnames):
    if not rows:
        return
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def run_wet_pipeline(retailer_name, scraper, data_dir, max_pages=None):
    print(f"\n==========================================")
    print(f"  Starting WET Food Pipeline ({retailer_name})")
    print(f"==========================================")
    raw_products = scraper.scrape_wet(max_pages=max_pages)
    
    scored_full = []
    minified = []
    for p in raw_products:
        p_full, p_mini = score_wet_product(p)
        scored_full.append(p_full)
        minified.append(p_mini)

    # Sort by score desc, then value ratio desc
    scored_full.sort(key=lambda x: (x.get('score', 0), x.get('value_ratio', 0)), reverse=True)
    minified.sort(key=lambda x: (x.get('s', 0), x.get('vr', 0)), reverse=True)

    full_path = os.path.join(data_dir, f"{retailer_name}_wet_full.json")
    mini_path = os.path.join(data_dir, f"{retailer_name}_wet.json")
    csv_path = os.path.join(data_dir, f"{retailer_name}_wet.csv")

    save_json(full_path, scored_full)
    save_json(mini_path, minified)

    csv_fields = ['pid', 'name', 'brand', 'price', 'unit_price_kg', 'classification', 'is_kitten', 'score', 'tier', 'value_ratio', 'has_sugar', 'has_grains', 'has_veg_protein', 'pdp_url']
    save_csv(csv_path, scored_full, csv_fields)

    print(f"[Pipeline] Wet food complete: {len(minified)} products processed.")
    return minified

def run_dry_pipeline(retailer_name, scraper, data_dir, max_pages=None):
    print(f"\n==========================================")
    print(f"  Starting DRY Food Pipeline ({retailer_name})")
    print(f"==========================================")
    raw_products = scraper.scrape_dry(max_pages=max_pages)

    scored_full = []
    minified = []
    for p in raw_products:
        p_full, p_mini = score_dry_product(p)
        scored_full.append(p_full)
        minified.append(p_mini)

    scored_full.sort(key=lambda x: (x.get('score', 0), x.get('value_ratio', 0)), reverse=True)
    minified.sort(key=lambda x: (x.get('s', 0), x.get('vr', 0)), reverse=True)

    full_path = os.path.join(data_dir, f"{retailer_name}_dry_full.json")
    mini_path = os.path.join(data_dir, f"{retailer_name}_dry.json")
    csv_path = os.path.join(data_dir, f"{retailer_name}_dry.csv")

    save_json(full_path, scored_full)
    save_json(mini_path, minified)

    csv_fields = ['pid', 'name', 'brand', 'price', 'unit_price_kg', 'is_kitten', 'is_sterilised', 'score', 'tier', 'value_ratio', 'is_grain_free', 'has_corn_gluten', 'has_colorants', 'pdp_url']
    save_csv(csv_path, scored_full, csv_fields)

    print(f"[Pipeline] Dry food complete: {len(minified)} products processed.")
    return minified

def main():
    parser = argparse.ArgumentParser(description="Refresh and build Cat Food Rankings")
    parser.add_argument('--retailer', choices=['continente', 'zu', 'zooplus'], default='continente', help="Retailer to scrape")
    parser.add_argument('--type', choices=['wet', 'dry', 'all'], default='all', help="Food category to refresh")
    parser.add_argument('--max-pages', type=int, default=None, help="Limit catalog pagination (for quick test runs)")
    parser.add_argument('--skip-scrape', action='store_true', help="Skip scraping and rebuild index.html from existing data")
    args = parser.parse_args()

    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)

    if not args.skip_scrape:
        if args.retailer == 'continente':
            scraper = ContinenteScraper()
        else:
            raise NotImplementedError(f"Scraper for {args.retailer} is not yet implemented.")

        if args.type in ['wet', 'all']:
            run_wet_pipeline(args.retailer, scraper, data_dir, max_pages=args.max_pages)

        if args.type in ['dry', 'all']:
            run_dry_pipeline(args.retailer, scraper, data_dir, max_pages=args.max_pages)

    # Rebuild unified HTML site
    print("\n[Builder] Recompiling unified GitHub Pages dashboard...")
    wet_products, dry_products = load_data(data_dir)
    index_html = os.path.join(BASE_DIR, 'index.html')
    generate_html(wet_products, dry_products, index_html)
    print(f"✨ Refresh pipeline finished successfully! Open: {index_html}\n")

if __name__ == '__main__':
    main()

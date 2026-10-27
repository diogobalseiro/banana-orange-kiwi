#!/usr/bin/env python3
"""
Baseline completeness audit script.
Evaluates dataset quality distinguishing nonempty strings from semantic validity.
"""
import glob
import json
import os
import re

def audit_dataset(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    nonempty_ingr = 0
    valid_ingr = 0
    nonempty_nutri = 0
    valid_nutri_protein = 0
    valid_unit_price = 0
    rejected_footer_nutri = 0

    footer_marker = "As novidades mais frescas"

    for p in data:
        ingr = p.get('ingredients') or ''
        nutri = p.get('nutrition_raw') or ''
        up = p.get('unit_price_kg')
        parsed = p.get('nutrition_parsed') or {}

        if ingr.strip():
            nonempty_ingr += 1
            # Check if it's marketing copy vs actual composition
            if not ingr.strip().startswith("Caraterísticas") and not ingr.strip().startswith("Descrição:"):
                valid_ingr += 1

        if nutri.strip():
            nonempty_nutri += 1
            if footer_marker in nutri:
                rejected_footer_nutri += 1
            elif parsed.get('protein') is not None:
                valid_nutri_protein += 1

        if up is not None and isinstance(up, (int, float)) and up > 0:
            valid_unit_price += 1

    return {
        'total': total,
        'nonempty_ingr': nonempty_ingr,
        'valid_ingr': valid_ingr,
        'nonempty_nutri': nonempty_nutri,
        'rejected_footer_nutri': rejected_footer_nutri,
        'valid_nutri_protein': valid_nutri_protein,
        'valid_unit_price': valid_unit_price
    }

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    baseline_dir = os.path.join(base_dir, 'data', 'baseline')
    files = sorted(glob.glob(os.path.join(baseline_dir, '*_full.json')))

    print(f"{'Dataset':<28} | {'Total':<6} | {'Valid Ingr':<11} | {'Valid Nutri':<12} | {'Footer Trap':<12} | {'Unit Price':<11}")
    print("-" * 92)
    for fpath in files:
        fname = os.path.basename(fpath).replace('_full.json', '')
        res = audit_dataset(fpath)
        print(f"{fname:<28} | {res['total']:<6} | {res['valid_ingr']:<11} | {res['valid_nutri_protein']:<12} | {res['rejected_footer_nutri']:<12} | {res['valid_unit_price']:<11}")

if __name__ == '__main__':
    main()

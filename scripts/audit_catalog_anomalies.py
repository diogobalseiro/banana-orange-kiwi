#!/usr/bin/env python3
"""
scripts/audit_catalog_anomalies.py

Systematic biological anomaly scanner across all catalog datasets.
Evaluates every product against feline obligate carnivore biological invariants.
Outputs findings to stdout and writes data/audit/anomaly_register.json and .csv.
"""

import csv
import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
AUDIT_DIR = DATA_DIR / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

CATALOG_FILES = [
    ("continente_dry_full.json", "dry", "Continente"),
    ("continente_wet_full.json", "wet", "Continente"),
    ("zu_dry_full.json", "dry", "ZU"),
    ("zu_wet_full.json", "wet", "ZU"),
    ("zooplus_dry_full.json", "dry", "Zooplus"),
    ("zooplus_wet_full.json", "wet", "Zooplus"),
]

PRIVATE_LABELS = {
    "continente", "continente pet", "continente pet care", "continente pet premium", "continente pet basic",
    "pingo doce", "auchan", "mercadona", "compy"
}

ORGAN_TERMS = ['coração', 'corações', 'fígado', 'figado', 'moela', 'moelas', 'pulmão', 'pulmões', 'estômago', 'estômagos', 'rins', 'rim', 'miudezas']


def has_fake_organ_bonus(ingr: str, has_organs_flag: bool) -> bool:
    """Returns True if has_organs is flagged but the only organ reference is a hydrolysate / digest."""
    if not has_organs_flag or not ingr:
        return False
    lower = ingr.lower()
    # Strip hydrolysate/digest occurrences
    cleaned = re.sub(r'(?:hidrolisad[oa]\s+de\s+|fígado\s+hidrolisado|figado\s+hidrolisado|digest\s+de\s+)[a-zá-ú\s]+', '', lower)
    # Check if any organ term remains in cleaned text
    has_real_organ = any(o in cleaned for o in ORGAN_TERMS)
    return not has_real_organ


def check_product_invariants(p: dict, cat_type: str, dataset_name: str) -> list:
    """Evaluates a single product against biological invariants. Returns a list of violation dicts."""
    violations = []
    pid = p.get('pid') or p.get('id') or 'unknown'
    name = p.get('name') or ''
    brand = (p.get('brand') or '').strip()
    score = p.get('score')
    tier = p.get('tier') or ''
    is_ranked = p.get('is_ranked', False)

    if not is_ranked or score is None:
        return violations

    ingr = p.get('ingredients') or ''
    nutri = p.get('nutrition_parsed') or {}
    prot = p.get('protein')
    carbs = p.get('carbs')
    is_fractionated = p.get('is_fractionated', False)
    has_organs = p.get('has_organs', False)
    brand_lower = brand.lower()

    # Invariant: Fake Organ Superfood from palatant digest
    if has_fake_organ_bonus(ingr, has_organs):
        violations.append({
            'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
            'score': score, 'tier': tier, 'rule': 'ORGAN_DIGEST_FALSE_POSITIVE',
            'severity': 'HIGH',
            'details': "Organ bonus awarded exclusively from flavor hydrolysate/digest palatant"
        })

    # Dry Kibble Invariants
    if cat_type == "dry":
        is_sterilised = p.get('is_sterilised', False) or any(s in f"{name.lower()} {p.get('description', '').lower()}" for s in ['esterilizado', 'esterilizada', 'esterilizados', 'esterilizadas', 'sterilised', 'sterilized', 'neutered', 'castrado', 'castrada', 'castrados'])
        min_tier_s_prot = 36.0 if is_sterilised else 38.0
        max_tier_s_carbs = 35.0 if is_sterilised else 30.0

        # 1. Tier S Protein invariant
        if score >= 80 and prot is not None and prot < min_tier_s_prot:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'DRY_TIER_S_LOW_PROTEIN',
                'severity': 'CRITICAL',
                'details': f"Tier S requires protein >= {min_tier_s_prot}%, found {prot}%"
            })

        # 2. Tier S Carbs invariant
        if score >= 80 and carbs is not None and carbs > max_tier_s_carbs:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'DRY_TIER_S_HIGH_CARBS',
                'severity': 'CRITICAL',
                'details': f"Tier S requires carbs <= {max_tier_s_carbs}%, found {carbs}%"
            })

        # 3. Tier S Starch Fractionation: must not be fractionated
        if score >= 80 and is_fractionated:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'DRY_TIER_S_FRACTIONATED_STARCH',
                'severity': 'CRITICAL',
                'details': "Tier S prohibits starch fractionation (split peas/potatoes)"
            })

        # 4. Supermarket / Private Label in Tier S
        if score >= 80 and any(pl in brand_lower for pl in PRIVATE_LABELS):
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'PRIVATE_LABEL_IN_TIER_S',
                'severity': 'CRITICAL',
                'details': f"Private label brand '{brand}' scoring in Tier S ({score} pts)"
            })

        # 5. Tier A Protein invariant: must be >= 33.0%
        if score >= 65 and score < 80 and prot is not None and prot < 33.0:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'DRY_TIER_A_LOW_PROTEIN',
                'severity': 'MEDIUM',
                'details': f"Tier A requires protein >= 33.0%, found {prot}%"
            })

        # 6. Tier A Carbs invariant: must be <= 36.0%
        if score >= 65 and score < 80 and carbs is not None and carbs > 36.0:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'DRY_TIER_A_HIGH_CARBS',
                'severity': 'MEDIUM',
                'details': f"Tier A requires carbs <= 36.0%, found {carbs}%"
            })

    # Wet Food Invariants
    elif cat_type == "wet":
        prot_dmb = nutri.get('protein_dmb')
        carbs_dmb = nutri.get('carbs_dmb')
        has_grains = p.get('has_grains', False)

        if score >= 80 and has_grains:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'WET_TIER_S_GRAIN_INCLUSIVE',
                'severity': 'CRITICAL',
                'details': "Wet Tier S strictly prohibits grains"
            })

        if score >= 80 and prot_dmb is not None and prot_dmb < 50.0:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'WET_TIER_S_LOW_PROTEIN_DMB',
                'severity': 'CRITICAL',
                'details': f"Wet Tier S requires protein DMB >= 50.0%, found {prot_dmb}%"
            })

        if score >= 80 and carbs_dmb is not None and carbs_dmb > 15.0:
            violations.append({
                'file': dataset_name, 'pid': pid, 'brand': brand, 'name': name,
                'score': score, 'tier': tier, 'rule': 'WET_TIER_S_HIGH_CARBS_DMB',
                'severity': 'CRITICAL',
                'details': f"Wet Tier S requires carbs DMB <= 15.0%, found {carbs_dmb}%"
            })

    return violations


def main():
    all_violations = []
    total_products = 0
    total_ranked = 0
    file_stats = {}

    print("=" * 80)
    print("PHASE 1: AUTOMATED BIOLOGICAL ANOMALY AUDIT ACROSS ALL CATALOGS")
    print("=" * 80)

    for filename, cat_type, retailer in CATALOG_FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"[!] Warning: File {filepath} does not exist, skipping.")
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        file_violations = []
        ranked_count = 0
        for p in data:
            total_products += 1
            if p.get('is_ranked'):
                ranked_count += 1
            v_list = check_product_invariants(p, cat_type, filename)
            file_violations.extend(v_list)

        total_ranked += ranked_count
        all_violations.extend(file_violations)
        file_stats[filename] = {
            'total': len(data),
            'ranked': ranked_count,
            'violations': len(file_violations)
        }
        print(f"[*] {filename:28} | Total: {len(data):4} | Ranked: {ranked_count:4} | Violations: {len(file_violations):4}")

    print("-" * 80)
    print(f"TOTAL CATALOG ENTRIES: {total_products} | RANKED: {total_ranked} | ANOMALY VIOLATIONS: {len(all_violations)}")
    print("-" * 80)

    # Group violations by rule
    rule_counts = {}
    for v in all_violations:
        r = v['rule']
        rule_counts[r] = rule_counts.get(r, 0) + 1

    print("\nVIOLATION SUMMARY BY BIOLOGICAL RULE:")
    for rule, count in sorted(rule_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {rule:35} : {count:3} occurrences")

    # Save to JSON
    json_path = AUDIT_DIR / "anomaly_register.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_products': total_products,
            'total_ranked': total_ranked,
            'total_violations': len(all_violations),
            'rule_summary': rule_counts,
            'file_stats': file_stats,
            'violations': all_violations
        }, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Anomaly register saved to: {json_path}")

    # Save to CSV
    csv_path = AUDIT_DIR / "anomaly_register.csv"
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['file', 'pid', 'brand', 'name', 'score', 'tier', 'rule', 'severity', 'details'])
        writer.writeheader()
        for v in all_violations:
            writer.writerow(v)
    print(f"[+] CSV export saved to: {csv_path}")


if __name__ == '__main__':
    main()

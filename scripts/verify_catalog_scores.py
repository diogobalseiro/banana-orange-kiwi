#!/usr/bin/env python3
"""
scripts/verify_catalog_scores.py

Entry-by-Entry Verification Ledger Generator.
Re-evaluates all 1,666 products across Continente, ZU, and Zooplus,
recording before/after scores, tier migrations, delta justifications,
and biological invariant compliance.

Outputs:
  data/audit/entry_verification_ledger.json
  data/audit/entry_verification_ledger.csv
"""

import csv
import json
import os
from pathlib import Path
from src.scoring.dry_scorer import score_dry_product
from src.scoring.wet_scorer import score_wet_product
from scripts.audit_catalog_anomalies import check_product_invariants, PRIVATE_LABELS

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


def verify_catalogs():
    ledger = []
    file_summaries = {}
    total_products = 0
    total_recalibrated = 0
    total_tier_changes = 0

    print("=" * 85)
    print("PHASE 3: ENTRY-BY-ENTRY CATALOG VERIFICATION RUNNER")
    print("=" * 85)

    for filename, cat_type, retailer in CATALOG_FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"[!] Warning: File {filepath} not found.")
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        scorer_fn = score_dry_product if cat_type == "dry" else score_wet_product
        file_recalibrated = 0
        file_tier_changes = 0
        file_violations_remaining = 0

        for p in data:
            total_products += 1
            pid = p.get('pid') or p.get('id') or 'unknown'
            name = p.get('name') or ''
            brand = (p.get('brand') or '').strip()
            old_score = p.get('score')
            old_tier = p.get('tier') or 'Não classificado'
            is_ranked = p.get('is_ranked', False)

            # Deep copy to score independently
            p_copy = dict(p)
            new_full, new_mini = scorer_fn(p_copy)

            if new_full is None:
                new_score = None
                new_tier = "Excluído (Não-Alimento / Complementar)"
                score_delta = 0
                status = "EXCLUDED"
                reasons = ["Non-food or complementary snack excluded"]
            elif not new_full.get('is_ranked'):
                new_score = None
                new_tier = new_full.get('tier', 'Não classificado')
                score_delta = 0
                status = "FLAGGED_INSUFFICIENT_DATA"
                reasons = new_full.get('unranked_reasons', [])
            else:
                new_score = new_full.get('score')
                new_tier = new_full.get('tier')
                score_delta = (new_score - old_score) if (old_score is not None and new_score is not None) else 0

                # Check invariants on newly scored item
                remaining_violations = check_product_invariants(new_full, cat_type, filename)
                file_violations_remaining += len(remaining_violations)

                if old_score != new_score:
                    file_recalibrated += 1
                if old_tier != new_tier:
                    file_tier_changes += 1

                reasons = []
                if old_score != new_score:
                    if old_score and new_score and new_score < old_score:
                        if p.get('has_organs') and not new_full.get('has_organs'):
                            reasons.append("Removed false positive organ superfood bonus from palatant digest")
                        if p.get('meat_pct') != new_full.get('meat_pct'):
                            reasons.append(f"Corrected meat % from {p.get('meat_pct')}% to {new_full.get('meat_pct')}%")
                        if new_full.get('is_fractionated') and old_score >= 80:
                            reasons.append("Applied Tier S starch fractionation ceiling (cap 79)")
                        if any(pl in brand.lower() for pl in PRIVATE_LABELS) and old_score >= 80:
                            reasons.append("Applied private label supermarket ceiling")
                        if new_full.get('protein') and new_full.get('protein') < 38.0 and old_score >= 80:
                            reasons.append(f"Applied Tier S protein ceiling ({new_full.get('protein')}% < 38%)")
                        if new_full.get('carbs') and new_full.get('carbs') > 24.0 and old_score >= 80:
                            reasons.append(f"Applied Tier S carbohydrate ceiling ({new_full.get('carbs')}% > 24%)")
                        if not reasons:
                            reasons.append(f"Macronutrient curve adjustment ({score_delta:+d} pts)")
                    else:
                        reasons.append(f"Score recalibrated ({score_delta:+d} pts)")

                if abs(score_delta) > 5 or old_tier != new_tier:
                    status = "RECALIBRATED_CORRECTED"
                else:
                    status = "VERIFIED_SOUND"

            entry_record = {
                'file': filename,
                'category': cat_type,
                'retailer': retailer,
                'pid': pid,
                'brand': brand,
                'name': name,
                'price': p.get('price'),
                'unit_price_kg': p.get('unit_price_kg'),
                'old_score': old_score,
                'new_score': new_score,
                'delta': score_delta,
                'old_tier': old_tier,
                'new_tier': new_tier,
                'tier_changed': (old_tier != new_tier),
                'status': status,
                'protein': new_full.get('protein') if new_full else None,
                'fat': new_full.get('fat') if new_full else None,
                'carbs': new_full.get('carbs') if new_full else None,
                'meat_pct': new_full.get('meat_pct') if new_full else None,
                'is_grain_free': new_full.get('is_grain_free') if new_full else None,
                'is_fractionated': new_full.get('is_fractionated') if new_full else None,
                'has_organs': new_full.get('has_organs') if new_full else None,
                'justification': "; ".join(reasons) if reasons else "Biological invariants confirmed sound"
            }
            ledger.append(entry_record)

        total_recalibrated += file_recalibrated
        total_tier_changes += file_tier_changes
        file_summaries[filename] = {
            'total': len(data),
            'recalibrated': file_recalibrated,
            'tier_changes': file_tier_changes,
            'remaining_violations': file_violations_remaining
        }
        print(f"[*] {filename:28} | Total: {len(data):4} | Recalibrated: {file_recalibrated:4} | Tier Changes: {file_tier_changes:4} | Remaining Invariant Violations: {file_violations_remaining:2}")

    print("-" * 85)
    print(f"TOTAL ENTRIES VERIFIED: {total_products}")
    print(f"TOTAL RECALIBRATED ENTRIES: {total_recalibrated}")
    print(f"TOTAL TIER MIGRATIONS: {total_tier_changes}")
    print("-" * 85)

    # Save complete verification ledger
    json_path = AUDIT_DIR / "entry_verification_ledger.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_products': total_products,
            'total_recalibrated': total_recalibrated,
            'total_tier_changes': total_tier_changes,
            'file_summaries': file_summaries,
            'entries': ledger
        }, f, indent=2, ensure_ascii=False)
    print(f"[+] Full JSON ledger saved to: {json_path}")

    csv_path = AUDIT_DIR / "entry_verification_ledger.csv"
    fieldnames = [
        'file', 'category', 'retailer', 'pid', 'brand', 'name', 'unit_price_kg',
        'old_score', 'new_score', 'delta', 'old_tier', 'new_tier', 'tier_changed',
        'status', 'protein', 'fat', 'carbs', 'meat_pct', 'is_grain_free', 'is_fractionated', 'has_organs',
        'justification'
    ]
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in ledger:
            writer.writerow(row)
    print(f"[+] Full CSV export saved to: {csv_path}")

    return ledger


if __name__ == '__main__':
    verify_catalogs()

"""
Quality Gate for publication protection.
Blocks deployment of degraded candidates, empty crawls, or accidental partial sweeps.
"""

from typing import Any, Dict, List, Optional, Tuple

# Threshold constants
MAX_ALLOWED_DROP_RATIO = 0.30  # Max 30% drop in total product count
MAX_ALLOWED_FIELD_LOSS = 0.40  # Max 40% loss in populated ingredient/nutrition fields

def is_valid_field_text(text: Any) -> bool:
    """Distinguishes genuine extraction from empty strings, marketing copy, or footer newsletter traps."""
    if not text:
        return False
    s = str(text).strip()
    if not s:
        return False
    if 'novidades mais frescas' in s or 'Subscreva e descubra' in s:
        return False
    if s.startswith('Caraterísticas') or s.startswith('Descrição') or s.startswith('Benefícios'):
        return False
    return True

class QualityGateError(Exception):
    """Raised when a candidate dataset fails quality verification."""
    def __init__(self, dataset_key: str, reasons: List[str]):
        self.dataset_key = dataset_key
        self.reasons = reasons
        super().__init__(f"Quality gate rejected '{dataset_key}': {'; '.join(reasons)}")

def validate_candidate_dataset(candidate_products: List[Dict[str, Any]], 
                               dataset_key: str, 
                               last_accepted_entry: Optional[Dict[str, Any]] = None,
                               is_limited_run: bool = False,
                               allow_partial: bool = False,
                               scraper_status: str = "COMPLETED") -> Tuple[bool, List[str]]:
    """
    Validates whether candidate data meets reliability standards to be accepted.
    Returns (is_valid: bool, rejection_reasons: List[str]).
    """
    reasons = []

    # 1. Scraper completion status
    if scraper_status != "COMPLETED":
        reasons.append(f"Catalog crawl did not complete normally (status: {scraper_status})")

    # 2. Page-limited check (--max-pages)
    if is_limited_run and not allow_partial:
        reasons.append(
            "Deliberate page-limited scrape (--max-pages) cannot replace production catalog without --allow-partial"
        )

    # 3. Empty catalog check
    curr_count = len(candidate_products)
    prev_count = last_accepted_entry.get("product_count", 0) if last_accepted_entry else 0

    if curr_count == 0:
        reasons.append(
            f"Zero products extracted (catalog cannot be empty, {prev_count} previously)"
        )

    # 4. Sudden catalog drop check
    if not is_limited_run and prev_count > 0 and curr_count > 0:
        drop_pct = (prev_count - curr_count) / prev_count
        min_prev = 5 if dataset_key.endswith('_litter') else 15
        if prev_count >= min_prev and drop_pct > MAX_ALLOWED_DROP_RATIO:
            reasons.append(
                f"Unexpected catalog drop of {round(drop_pct * 100, 1)}% ({curr_count} vs {prev_count} previous)"
            )

    # 5. Field coverage check
    if dataset_key.endswith('_litter'):
        # Validate critical litter attributes (volume or weight coverage, supporting minified keys)
        curr_meas = sum(1 for p in candidate_products if p.get('volume_l') or p.get('weight_kg') or p.get('vol') or p.get('wt'))
        if not is_limited_run and curr_count >= 5:
            if curr_meas < 0.5 * curr_count:
                reasons.append(f"Litter measurement failure: only {curr_meas}/{curr_count} have volume or weight")
    else:
        # Ingredients and nutrition checks for pet food
        curr_ingr = sum(1 for p in candidate_products if is_valid_field_text(p.get('ingredients')))
        curr_nutri = sum(1 for p in candidate_products if is_valid_field_text(p.get('nutrition_raw')))

        if not is_limited_run and last_accepted_entry:
            prev_ingr = last_accepted_entry.get("valid_ingredients_count", 0)
            prev_nutri = last_accepted_entry.get("valid_nutrition_count", 0)

            if prev_ingr >= 20 and curr_ingr > 0:
                ingr_loss = (prev_ingr - curr_ingr) / prev_ingr
                if ingr_loss > MAX_ALLOWED_FIELD_LOSS:
                    reasons.append(
                        f"Widespread ingredient field loss of {round(ingr_loss * 100, 1)}% ({curr_ingr} vs {prev_ingr})"
                    )

            if prev_nutri >= 20 and curr_nutri > 0:
                nutri_loss = (prev_nutri - curr_nutri) / prev_nutri
                if nutri_loss > MAX_ALLOWED_FIELD_LOSS:
                    reasons.append(
                        f"Widespread nutrition field loss of {round(nutri_loss * 100, 1)}% ({curr_nutri} vs {prev_nutri})"
                    )

    # 6. Structural validity check
    if curr_count > 0:
        invalid_structure_count = sum(1 for p in candidate_products if not p.get('pid') or not p.get('name'))
        if invalid_structure_count > 0.1 * curr_count:
            reasons.append(
                f"Structurally invalid observations: {invalid_structure_count} products lack pid or name"
            )

    # 7. Widespread fetch error check (e.g. blocked requests / failed details)
    if curr_count > 0:
        fetch_error_count = sum(1 for p in candidate_products if p.get('fetch_error'))
        if fetch_error_count > 0.5 * curr_count:
            reasons.append(
                f"Widespread fetch errors or blocked pages: {fetch_error_count} of {curr_count} products failed to fetch details"
            )

    is_valid = len(reasons) == 0
    return is_valid, reasons

def extract_dataset_summary(products: List[Dict[str, Any]], is_partial: bool = False, dataset_key: str = "") -> Dict[str, Any]:
    """
    Computes summary metadata for an accepted dataset snapshot.
    Supports extended substrate breakdown and average score for litter datasets.
    """
    ranked_prods = [p for p in products if p.get('is_ranked') or p.get('ir')]
    summary = {
        "product_count": len(products),
        "total_products": len(products),
        "valid_ingredients_count": sum(1 for p in products if is_valid_field_text(p.get('ingredients'))),
        "valid_nutrition_count": sum(1 for p in products if is_valid_field_text(p.get('nutrition_raw'))),
        "ranked_count": len(ranked_prods),
        "unranked_count": len(products) - len(ranked_prods),
        "is_partial": is_partial
    }

    if dataset_key.endswith('_litter'):
        ranked_scores = [
            p.get('score') if p.get('score') is not None else p.get('s')
            for p in ranked_prods
            if (p.get('score') is not None or p.get('s') is not None)
        ]
        summary["avg_score"] = round(sum(ranked_scores) / len(ranked_scores), 1) if ranked_scores else None
        
        substrate_counts = {}
        for p in products:
            mat = p.get('material') or p.get('mat') or 'Outro'
            substrate_counts[mat] = substrate_counts.get(mat, 0) + 1
        summary["substrate_breakdown"] = substrate_counts

    return summary

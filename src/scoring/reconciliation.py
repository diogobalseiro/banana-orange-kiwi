"""
Reconciliation module for matching retailer products to verified formulations.

This module provides:
- Identity mapping from data/product_matches.json
- Reconciliation of formulation facts before scoring
- Shared assessment calculation for matched products
- Unmatched products remain independent

Key principles:
- Verified manufacturer/packaging evidence takes precedence
- Contradictory declarations remain visible
- Material conflicts mark formulation as unresolved/unranked
- Each offer retains its own price, URL, pack size
- Shared nutritional assessment is calculated once per formulation
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Path to the product matches configuration
MATCHES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                           'data', 'product_matches.json')


class ReconciliationError(Exception):
    """Raised when reconciliation fails due to configuration errors."""
    pass


def load_product_matches() -> Dict[str, Any]:
    """
    Load the curated product matches configuration.
    
    Returns:
        Dictionary with formulation_id -> {formulation_data, retailer_matches}
    """
    if not os.path.exists(MATCHES_PATH):
        return {}
    
    try:
        with open(MATCHES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ReconciliationError(f"Failed to load product matches: {e}") from e


def get_product_key(retailer: str, pid: str) -> str:
    """
    Create a stable key for identifying a retailer product observation.
    
    Args:
        retailer: Retailer name (e.g., 'continente', 'zu', 'zooplus')
        pid: Product ID from the retailer
        
    Returns:
        String key: f"{retailer}:{pid}"
    """
    return f"{retailer.lower()}:{pid}"


def find_formulation_id(retailer: str, pid: str, matches_config: Optional[Dict] = None) -> Optional[str]:
    """
    Find the formulation ID for a given retailer product.
    
    Args:
        retailer: Retailer name
        pid: Product ID
        matches_config: Optional pre-loaded matches config
        
    Returns:
        Formulation ID if matched, None otherwise
    """
    if matches_config is None:
        matches_config = load_product_matches()
    
    retailer_lower = retailer.lower()
    
    for formulation_id, match_data in matches_config.items():
        retailer_matches = match_data.get('retailer_matches', {})
        # Check if this retailer has matches
        if retailer_lower in retailer_matches:
            # retailer_matches[retailer] is a list of PIDs
            pids = retailer_matches[retailer_lower]
            if pid in pids:
                return formulation_id
    
    return None


def get_formulation_data(formulation_id: str, matches_config: Optional[Dict] = None) -> Optional[Dict]:
    """
    Get the formulation data for a given ID.
    
    Args:
        formulation_id: The stable formulation identifier
        matches_config: Optional pre-loaded matches config
        
    Returns:
        Formulation data dict or None if not found
    """
    if matches_config is None:
        matches_config = load_product_matches()
    
    return matches_config.get(formulation_id)


def get_all_matched_products(matches_config: Optional[Dict] = None) -> Dict[str, List[Tuple[str, str]]]:
    """
    Get all products that are part of a formulation match.
    
    Returns:
        Dict mapping formulation_id -> [(retailer, pid), ...]
    """
    if matches_config is None:
        matches_config = load_product_matches()
    
    result = {}
    for formulation_id, match_data in matches_config.items():
        retailer_matches = match_data.get('retailer_matches', {})
        result[formulation_id] = [
            (r, p) for r, p_list in retailer_matches.items()
            for p in p_list
        ]
    return result


def reconcile_product_evidence(product: Dict[str, Any], 
                               retailer: str, 
                               matches_config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Reconcile a single product's evidence with verified formulation data.
    
    This function:
    1. Checks if the product matches a known formulation
    2. If matched, merges verified formulation data with retailer-specific data
    3. Marks the product with its formulation_id
    4. Preserves all retailer-specific fields (price, URL, pack size, retrieval time)
    5. Handles conflicts explicitly
    
    Args:
        product: The raw product dict from extraction
        retailer: Retailer name
        matches_config: Optional pre-loaded matches config
        
    Returns:
        Reconciled product dict with:
        - formulation_id (if matched)
        - formulation_data (merged verified data)
        - reconciliation_notes (conflicts, sources)
        - is_reconciled: bool
    """
    pid = product.get('pid') or product.get('id')
    if not pid:
        return {
            **product,
            'is_reconciled': False,
            'formulation_id': None,
            'reconciliation_notes': ['No product ID available']
        }
    
    if matches_config is None:
        matches_config = load_product_matches()
    
    formulation_id = find_formulation_id(retailer, pid, matches_config)
    
    if not formulation_id:
        # No match found - return product as-is
        return {
            **product,
            'is_reconciled': False,
            'formulation_id': None,
            'reconciliation_notes': ['No formulation match found']
        }
    
    formulation_data = matches_config.get(formulation_id)
    if not formulation_data:
        return {
            **product,
            'is_reconciled': False,
            'formulation_id': formulation_id,
            'reconciliation_notes': ['Formulation ID not found in config']
        }
    
    # Start with a copy of the product
    reconciled = dict(product)
    
    # Add formulation metadata
    reconciled['formulation_id'] = formulation_id
    reconciled['is_reconciled'] = True
    reconciled['reconciliation_timestamp'] = datetime.now(timezone.utc).isoformat()
    
    # Track sources and conflicts
    notes = []
    conflicts = []
    sources = {'retailer': retailer, 'pid': pid}
    
    # Merge verified formulation data
    verified = formulation_data.get('verified', {})
    
    # Reconcile composition/ingredients
    verified_ingredients = verified.get('ingredients')
    retailer_ingredients = product.get('ingredients', '')
    
    if verified_ingredients:
        if retailer_ingredients and retailer_ingredients != verified_ingredients:
            # Conflict: keep both, mark as conflicting
            conflicts.append({
                'field': 'ingredients',
                'retailer_value': retailer_ingredients,
                'verified_value': verified_ingredients,
                'resolution': 'prefer_verified'
            })
            notes.append('Ingredients conflict resolved in favor of verified formulation')
        reconciled['ingredients'] = verified_ingredients
        sources['ingredients'] = 'verified_formulation'
    
    # Reconcile nutrition
    verified_nutrition = verified.get('nutrition_raw')
    retailer_nutrition = product.get('nutrition_raw', '')
    
    if verified_nutrition:
        if retailer_nutrition and retailer_nutrition != verified_nutrition:
            conflicts.append({
                'field': 'nutrition_raw',
                'retailer_value': retailer_nutrition,
                'verified_value': verified_nutrition,
                'resolution': 'prefer_verified'
            })
            notes.append('Nutrition conflict resolved in favor of verified formulation')
        reconciled['nutrition_raw'] = verified_nutrition
        sources['nutrition_raw'] = 'verified_formulation'
    
    # Reconcile classification
    verified_classification = verified.get('classification')
    if verified_classification:
        reconciled['classification'] = verified_classification
        sources['classification'] = 'verified_formulation'
    
    # Add formulation-level metadata
    if 'formulation_notes' in formulation_data:
        reconciled['formulation_notes'] = formulation_data['formulation_notes']
    
    # If there are conflicts, mark as unresolved
    if conflicts:
        reconciled['has_conflicts'] = True
        reconciled['conflicts'] = conflicts
        notes.append(f'{len(conflicts)} field conflicts detected')
    else:
        reconciled['has_conflicts'] = False
    
    reconciled['reconciliation_notes'] = notes
    reconciled['reconciliation_sources'] = sources
    
    return reconciled


def reconcile_batch(products: List[Dict[str, Any]], 
                   retailer: str, 
                   matches_config: Optional[Dict] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Reconcile a batch of products from a single retailer.
    
    Args:
        products: List of product dicts
        retailer: Retailer name
        matches_config: Optional pre-loaded matches config
        
    Returns:
        Tuple of (reconciled_products, reconciliation_summary)
        
        reconciliation_summary contains:
        - total_products: int
        - matched_count: int
        - unmatched_count: int
        - conflict_count: int
        - formulations_used: list of formulation_ids
    """
    if matches_config is None:
        matches_config = load_product_matches()
    
    reconciled = []
    summary = {
        'total_products': len(products),
        'matched_count': 0,
        'unmatched_count': 0,
        'conflict_count': 0,
        'formulations_used': set()
    }
    
    for product in products:
        r = reconcile_product_evidence(product, retailer, matches_config)
        reconciled.append(r)
        
        if r.get('is_reconciled'):
            summary['matched_count'] += 1
            summary['formulations_used'].add(r.get('formulation_id'))
        else:
            summary['unmatched_count'] += 1
        
        if r.get('has_conflicts'):
            summary['conflict_count'] += 1
    
    summary['formulations_used'] = list(summary['formulations_used'])
    return reconciled, summary


def group_by_formulation(products: List[Dict[str, Any]], 
                         matches_config: Optional[Dict] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group reconciled products by their formulation ID.
    
    Products without a formulation_id are grouped under None.
    
    Args:
        products: List of (potentially reconciled) product dicts
        matches_config: Optional pre-loaded matches config (for lookup)
        
    Returns:
        Dict mapping formulation_id -> [products]
    """
    groups = {}
    
    for product in products:
        fid = product.get('formulation_id')
        if fid not in groups:
            groups[fid] = []
        groups[fid].append(product)
    
    return groups


def calculate_shared_score_for_formulation(formulation_id: str, 
                                          products: List[Dict[str, Any]],
                                          category: str = 'wet') -> Optional[Dict[str, Any]]:
    """
    Calculate a shared score for all products in a formulation group.
    
    This uses the first valid (ranked) product as the reference, since
    all matched products should have the same formulation and thus
    the same nutritional assessment.
    
    Args:
        formulation_id: The formulation identifier
        products: List of products in this formulation group
        category: 'wet' or 'dry'
        
    Returns:
        Shared assessment dict with score, tier, and reasoning, or None
        if no valid scoring can be performed.
    """
    from .wet_scorer import score_wet_product
    from .dry_scorer import score_dry_product
    from .evidence import check_scoring_readiness
    
    if not products:
        return None
    
    # Use the first product with valid formulation data as reference
    # All should have the same formulation, so we score once
    reference_product = products[0]
    
    # Create a clean copy for scoring
    scoring_input = {
        'pid': f"formulation:{formulation_id}",
        'name': reference_product.get('name'),
        'brand': reference_product.get('brand'),
        'price': reference_product.get('price'),
        'unit_price_kg': reference_product.get('unit_price_kg'),
        'ingredients': reference_product.get('ingredients', ''),
        'nutrition_raw': reference_product.get('nutrition_raw', ''),
        'nutrition_normalized': reference_product.get('nutrition_normalized'),
        'classification': reference_product.get('classification'),
        'pdp_url': reference_product.get('pdp_url'),
        'retailer': reference_product.get('retailer'),
        'formulation_id': formulation_id,
        # Formulation-level notes if present
        'formulation_notes': reference_product.get('formulation_notes')
    }
    
    # Score based on category
    try:
        if category == 'dry':
            full, mini = score_dry_product(scoring_input)
        else:
            full, mini = score_wet_product(scoring_input)
    except Exception as e:
        return {
            'formulation_id': formulation_id,
            'score': None,
            'tier': 'Unranked (Scoring Error)',
            'is_ranked': False,
            'unranked_reasons': [f'Scoring failed: {str(e)}'],
            'scoring_error': str(e)
        }
    
    # Return the shared assessment
    return {
        'formulation_id': formulation_id,
        'score': full.get('score'),
        'tier': full.get('tier'),
        'is_ranked': full.get('is_ranked'),
        'unranked_reasons': full.get('unranked_reasons', []),
        'value_ratio': None,  # Will be calculated per-offer
        'shared_fields': {
            'protein_dmb': full.get('protein_dmb'),
            'fat_dmb': full.get('fat_dmb'),
            'carbs_dmb': full.get('carbs_dmb') if category == 'wet' else full.get('carbs_nfe'),
            'carb_band': full.get('carb_band'),
            'has_sugar': full.get('has_sugar'),
            'has_grains': full.get('has_grains'),
            'has_veg_protein': full.get('has_veg_protein'),
            'has_organs': full.get('has_organs'),
        }
    }


def attach_shared_assessment(products: List[Dict[str, Any]], 
                            category: str = 'wet') -> List[Dict[str, Any]]:
    """
    For each formulation group, calculate shared assessment and attach to all offers.
    
    Args:
        products: List of reconciled products
        category: 'wet' or 'dry'
        
    Returns:
        List of products with shared assessment attached
    """
    # Group by formulation
    groups = group_by_formulation(products)
    
    # Process each group
    result = []
    for formulation_id, group_products in groups.items():
        if formulation_id is None:
            # Unmatched products - keep as-is
            result.extend(group_products)
            continue
        
        # Calculate shared assessment
        shared_assessment = calculate_shared_score_for_formulation(
            formulation_id, group_products, category
        )
        
        if not shared_assessment:
            result.extend(group_products)
            continue
        
        # Attach shared assessment to each offer
        for product in group_products:
            product_copy = dict(product)
            
            # Preserve offer-specific fields
            product_copy['score'] = shared_assessment.get('score')
            product_copy['tier'] = shared_assessment.get('tier')
            product_copy['is_ranked'] = shared_assessment.get('is_ranked')
            product_copy['unranked_reasons'] = shared_assessment.get('unranked_reasons', [])
            
            # If ranked, calculate value ratio based on this offer's price
            if shared_assessment.get('is_ranked') and product.get('unit_price_kg'):
                score = shared_assessment.get('score') or 0
                pkg = product.get('unit_price_kg')
                if pkg and pkg > 0:
                    product_copy['value_ratio'] = round(score / pkg, 2)
            else:
                product_copy['value_ratio'] = None
            
            # Add shared assessment metadata
            product_copy['shared_assessment'] = {
                'formulation_id': formulation_id,
                'score_source': 'shared_formulation',
                'formulation_notes': product.get('formulation_notes')
            }
            
            result.append(product_copy)
    
    return result


def get_formulation_summary(formulation_id: str, 
                           matches_config: Optional[Dict] = None) -> Optional[Dict]:
    """
    Get metadata about a specific formulation.
    
    Args:
        formulation_id: The formulation identifier
        matches_config: Optional pre-loaded matches config
        
    Returns:
        Formulation metadata or None
    """
    if matches_config is None:
        matches_config = load_product_matches()
    
    data = matches_config.get(formulation_id)
    if not data:
        return None
    
    return {
        'formulation_id': formulation_id,
        'description': data.get('description', ''),
        'brand': data.get('brand', ''),
        'line': data.get('line', ''),
        'category': data.get('category', 'wet'),
        'life_stage': data.get('life_stage'),
        'recipe': data.get('recipe'),
        'flavour': data.get('flavour'),
        'verified_date': data.get('verified_date'),
        'source': data.get('source'),
        'retailer_count': len(data.get('retailer_matches', {})),
        'retailers': list(data.get('retailer_matches', {}).keys()),
        'notes': data.get('notes', '')
    }

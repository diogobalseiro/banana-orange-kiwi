"""
Reconciliation module for matching retailer products to verified formulations.

This module provides:
- Identity mapping from data/product_matches.json (matching by PID or PDP URL)
- Full reversibility: preservation of raw retailer observations
- Conflict tracking (reconciliation notes, field conflicts, material conflicts)
- Shared assessment calculation for matched products (full & minified)
- Unmatched products remain independent
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

MATCHES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'product_matches.json'
)


class ReconciliationError(Exception):
    """Raised when reconciliation fails due to configuration errors."""
    pass


def load_product_matches() -> Dict[str, Any]:
    """Load the curated product matches configuration."""
    if not os.path.exists(MATCHES_PATH):
        return {}
    
    try:
        with open(MATCHES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ReconciliationError(f"Failed to load product matches: {e}") from e


def get_product_key(retailer: str, pid: str) -> str:
    """Create a stable key for identifying a retailer product observation."""
    return f"{retailer.lower()}:{pid}"


def find_formulation_id(retailer: str, 
                        pid: str, 
                        pdp_url: Optional[str] = None, 
                        matches_config: Optional[Dict] = None,
                        product_name: Optional[str] = None) -> Optional[str]:
    """Find the formulation ID for a given retailer product by PID, PDP URL, or alias."""
    if matches_config is None:
        matches_config = load_product_matches()
    
    retailer_lower = retailer.lower()
    
    # 1. Exact match against PID or PDP URL in retailer_matches
    for formulation_id, match_data in matches_config.items():
        retailer_matches = match_data.get('retailer_matches', {})
        if retailer_lower in retailer_matches:
            matches_list = retailer_matches[retailer_lower]
            # Match against pid
            if pid and str(pid) in [str(m) for m in matches_list]:
                return formulation_id
            # Match against pdp_url
            if pdp_url:
                for entry in matches_list:
                    if str(entry) in pdp_url or pdp_url.rstrip('/') == str(entry).rstrip('/'):
                        return formulation_id
    
    # 2. Match by brand + aliases if product_name is provided
    if product_name:
        name_lower = product_name.lower()
        for formulation_id, match_data in matches_config.items():
            brand = (match_data.get('brand') or '').lower()
            if brand and brand in name_lower:
                aliases = match_data.get('aliases', [])
                for alias in aliases:
                    if alias.lower() in name_lower:
                        return formulation_id

    return None


def get_formulation_data(formulation_id: str, matches_config: Optional[Dict] = None) -> Optional[Dict]:
    """Get the formulation data for a given ID."""
    if matches_config is None:
        matches_config = load_product_matches()
    return matches_config.get(formulation_id)


def get_all_matched_products(matches_config: Optional[Dict] = None) -> Dict[str, List[Tuple[str, str]]]:
    """
    Get all products that are part of a formulation match.
    Returns: Dict mapping formulation_id -> [(retailer, pid), ...]
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


def get_formulation_summary(formulation_id: str, matches_config: Optional[Dict] = None) -> Optional[Dict]:
    """Get metadata about a specific formulation."""
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


def group_by_formulation(products: List[Dict[str, Any]], 
                         matches_config: Optional[Dict] = None) -> Dict[Optional[str], List[Dict[str, Any]]]:
    """Group products by their formulation ID."""
    groups: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for product in products:
        fid = product.get('formulation_id') or product.get('fid')
        if fid not in groups:
            groups[fid] = []
        groups[fid].append(product)
    return groups


def detect_material_conflict(retailer_obs: Dict[str, Any], verified: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Detects whether there is a genuine material conflict between retailer observation
    and verified formulation (e.g. contradictory grains, sugar, or macros).
    """
    reasons = []
    
    r_class = (retailer_obs.get('classification') or '').lower()
    v_class = (verified.get('classification') or '').lower()
    if ('complementar' in r_class and 'complete' in v_class) or ('completo' in r_class and 'complementary' in v_class):
        reasons.append("Contradictory classification (complete vs complementary)")

    r_ingr = (retailer_obs.get('ingredients') or '').lower()
    v_ingr = (verified.get('ingredients') or '').lower()

    if r_ingr and v_ingr:
        sugar_terms = ['açúcar', 'açúcares', 'açucar', 'açucares', 'caramelo', 'xarope']
        r_sugar = any(s in r_ingr for s in sugar_terms)
        v_sugar = any(s in v_ingr for s in sugar_terms)
        if (r_sugar and not v_sugar) or (v_sugar and 'sem açúcar' in r_ingr):
            reasons.append("Contradictory sugar declaration")

    r_nutri = retailer_obs.get('nutrition_raw') or ''
    v_nutri = verified.get('nutrition_raw') or ''
    if r_nutri and v_nutri:
        m_r_prot = re.search(r'[Pp]rote[íi]na[:\s]+(\d+(?:[.,]\d+)?)', r_nutri)
        m_v_prot = re.search(r'[Pp]rote[íi]na[:\s]+(\d+(?:[.,]\d+)?)', v_nutri)
        if m_r_prot and m_v_prot:
            p_r = float(m_r_prot.group(1).replace(',', '.'))
            p_v = float(m_v_prot.group(1).replace(',', '.'))
            if abs(p_r - p_v) > 3.0:
                reasons.append(f"Material protein divergence ({p_r}% vs {p_v}%)")

    is_material = len(reasons) > 0
    return is_material, reasons


def reconcile_product_evidence(product: Dict[str, Any], 
                               retailer: str, 
                               matches_config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Reconciles a product's evidence with verified formulation data while preserving
    original observations for full reversibility.
    """
    pid = str(product.get('pid') or product.get('id') or '')
    pdp_url = product.get('pdp_url') or product.get('u')
    
    if not pid and not pdp_url:
        return {
            **product,
            'is_reconciled': False,
            'formulation_id': None,
            'has_conflicts': False,
            'conflicts': [],
            'reconciliation_notes': ['No product ID available'],
            'raw_ingredients': product.get('ingredients', ''),
            'raw_nutrition_raw': product.get('nutrition_raw', '')
        }

    if matches_config is None:
        matches_config = load_product_matches()
    
    product_name = product.get('name')
    formulation_id = find_formulation_id(retailer, pid, pdp_url, matches_config, product_name=product_name)
    
    if not formulation_id:
        return {
            **product,
            'is_reconciled': False,
            'formulation_id': None,
            'has_conflicts': False,
            'conflicts': [],
            'reconciliation_notes': ['No formulation match found'],
            'raw_ingredients': product.get('ingredients', ''),
            'raw_nutrition_raw': product.get('nutrition_raw', '')
        }
    
    formulation_data = matches_config.get(formulation_id)
    if not formulation_data:
        return {
            **product,
            'is_reconciled': False,
            'formulation_id': formulation_id,
            'has_conflicts': False,
            'conflicts': [],
            'reconciliation_notes': ['Formulation ID not found in config'],
            'raw_ingredients': product.get('ingredients', ''),
            'raw_nutrition_raw': product.get('nutrition_raw', '')
        }
    
    reconciled = dict(product)
    
    # 1. PRESERVE ORIGINAL OBSERVATIONS (Full Reversibility)
    reconciled['raw_ingredients'] = product.get('ingredients', '')
    reconciled['raw_nutrition_raw'] = product.get('nutrition_raw', '')
    reconciled['raw_classification'] = product.get('classification')
    
    reconciled['formulation_id'] = formulation_id
    reconciled['is_reconciled'] = True
    reconciled['reconciliation_timestamp'] = datetime.now(timezone.utc).isoformat()
    
    notes = []
    conflicts = []
    sources = {'retailer': retailer, 'pid': pid}
    
    verified = formulation_data.get('verified', {})
    
    # Reconcile composition/ingredients
    verified_ingredients = verified.get('ingredients')
    retailer_ingredients = product.get('ingredients', '')
    if verified_ingredients:
        if retailer_ingredients and retailer_ingredients != verified_ingredients:
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

    # Add formulation metadata
    if 'formulation_notes' in formulation_data:
        reconciled['formulation_notes'] = formulation_data['formulation_notes']
        
    # Material conflict check
    has_material, material_reasons = detect_material_conflict(product, verified)
    if formulation_data.get('unresolved_conflict') or has_material:
        reconciled['has_material_conflict'] = True
        notes.extend(material_reasons)
    else:
        reconciled['has_material_conflict'] = False

    reconciled['has_conflicts'] = bool(conflicts or reconciled['has_material_conflict'])
    reconciled['conflicts'] = conflicts
    reconciled['reconciliation_notes'] = notes
    reconciled['reconciliation_sources'] = sources
    
    return reconciled


def reconcile_batch(products: List[Dict[str, Any]], 
                    retailer: str, 
                    matches_config: Optional[Dict] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Reconciles a batch of products from a single retailer."""
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


def calculate_shared_score_for_formulation(formulation_id: str, 
                                          matches_config: Optional[Dict] = None,
                                          category: str = 'wet') -> Optional[Dict[str, Any]]:
    """
    Calculates the canonical nutritional assessment once directly from the verified formulation record.
    """
    from .wet_scorer import score_wet_product
    from .dry_scorer import score_dry_product
    
    if matches_config is None:
        matches_config = load_product_matches()
        
    formulation_data = matches_config.get(formulation_id)
    if not formulation_data:
        return None
        
    verified = formulation_data.get('verified', {})
    
    if formulation_data.get('unresolved_conflict'):
        return {
            'formulation_id': formulation_id,
            'score': None,
            'tier': 'Não classificado (Conflito de Formulação)',
            'is_ranked': False,
            'unranked_reasons': ['material_conflict_unresolved'],
            'has_conflicts': True
        }
        
    scoring_input = {
        'pid': f"formulation:{formulation_id}",
        'name': formulation_data.get('description', formulation_id),
        'brand': formulation_data.get('brand', 'Desconhecida'),
        'ingredients': verified.get('ingredients', ''),
        'nutrition_raw': verified.get('nutrition_raw', ''),
        'classification': verified.get('classification', 'complete'),
        'formulation_id': formulation_id
    }
    
    if category == 'dry':
        full, _ = score_dry_product(scoring_input)
    else:
        full, _ = score_wet_product(scoring_input)
        
    return {
        'formulation_id': formulation_id,
        'score': full.get('score'),
        'tier': full.get('tier'),
        'is_ranked': full.get('is_ranked'),
        'unranked_reasons': full.get('unranked_reasons', []),
        'has_conflicts': False,
        'has_sugar': full.get('has_sugar'),
        'has_grains': full.get('has_grains'),
        'has_veg_protein': full.get('has_veg_protein'),
        'has_organs': full.get('has_organs'),
        'has_carrageenan': full.get('has_carrageenan'),
        'has_taurine': full.get('has_taurine'),
        'carb_band': full.get('carb_band'),
        'carbs': full.get('nutrition_parsed', {}).get('carbs_dmb' if category == 'wet' else 'carbs_nfe')
    }


def attach_shared_assessment(products: List[Dict[str, Any]], 
                             category: str = 'wet',
                             matches_config: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """
    Attaches shared assessment to all matched products, handling both full and minified formats.
    """
    if matches_config is None:
        matches_config = load_product_matches()
        
    shared_scores = {}
    for fid in matches_config:
        shared_scores[fid] = calculate_shared_score_for_formulation(fid, matches_config, category)
        
    result = []
    for item in products:
        if item is None:
            continue
        p = dict(item)
        
        is_minified = ('s' in p and 'n' in p and 'name' not in p)
        
        fid = p.get('formulation_id') or p.get('fid')
        if not fid and is_minified:
            fid = find_formulation_id(p.get('r', ''), str(p.get('id', '')), p.get('u'), matches_config)
            if fid:
                p['fid'] = fid
                
        if not fid or fid not in shared_scores or not shared_scores[fid]:
            result.append(p)
            continue
            
        assessment = shared_scores[fid]
        has_material_conflict = p.get('has_material_conflict', False) or assessment.get('has_conflicts', False)
        
        unit_price = p.get('unit_price_kg') or p.get('pkg')
        score = assessment['score'] if not has_material_conflict else None
        is_ranked = assessment['is_ranked'] and not has_material_conflict
        tier = assessment['tier'] if not has_material_conflict else 'Não classificado (Conflito)'
        unranked_reasons = assessment['unranked_reasons'] if not has_material_conflict else ['material_conflict_unresolved']
        
        val_ratio = None
        if is_ranked and unit_price and unit_price > 0 and score:
            val_ratio = round(score / unit_price, 2)
            
        if is_minified:
            p['s'] = score
            p['t'] = tier
            p['ir'] = is_ranked
            p['ur'] = unranked_reasons
            p['vr'] = val_ratio
            p['fid'] = fid
            p['rec'] = True
            p['conf'] = has_material_conflict
            if assessment.get('has_sugar') is not None:
                p['sug'] = assessment['has_sugar']
            if assessment.get('has_grains') is not None:
                p['grn'] = assessment['has_grains']
            if assessment.get('carb_band'):
                p['cb'] = assessment['carb_band']
            if assessment.get('carbs') is not None:
                p['carb'] = assessment['carbs']
        else:
            p['score'] = score
            p['tier'] = tier
            p['is_ranked'] = is_ranked
            p['unranked_reasons'] = unranked_reasons
            p['value_ratio'] = val_ratio
            p['formulation_id'] = fid
            p['is_reconciled'] = True
            p['has_material_conflict'] = has_material_conflict
            if assessment.get('has_sugar') is not None:
                p['has_sugar'] = assessment['has_sugar']
            if assessment.get('has_grains') is not None:
                p['has_grains'] = assessment['has_grains']
            if assessment.get('carb_band'):
                p['carb_band'] = assessment['carb_band']
            p['shared_assessment'] = {
                'formulation_id': fid,
                'source': 'verified_shared_formulation',
                'is_ranked': is_ranked
            }
            
        result.append(p)
        
    return result

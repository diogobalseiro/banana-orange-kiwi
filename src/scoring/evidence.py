"""
Evidence contract and nutrient normalization module.
Ensures factual integrity, handles uncertainty explicitly, and eliminates nutrient imputation.
"""

import re
from enum import Enum

class FieldStatus(str, Enum):
    VALID = 'valid'
    MISSING = 'missing'
    INVALID = 'invalid'
    CONFLICTING = 'conflicting'

# Common regex patterns for analytical constituents (supports PT label variants)
NUTRIENT_PATTERNS = {
    'protein': [
        r'[Pp]rote[íi]na\s*(?:bruta)?',
    ],
    'fat': [
        r'[Gg]ordura\s*bruta',
        r'[Mm]at[ée]ria\s*gorda(?:[,\s]*bruta)?',
        r'[Gg]ordura',
        r'[Óó]leos\s*e\s*gorduras',
        r'[Tt]eor\s*de\s*gordura',
    ],
    'moisture': [
        r'[Hh]umidade',
        r'[Tt]eor\s*de\s*humidade',
    ],
    'ash': [
        r'[Cc]inza(?:s)?\s*bruta(?:s)?',
        r'[Cc]inza(?:s)?',
        r'[Mm]at[ée]ria\s*inorg[âa]nica',
    ],
    'fiber': [
        r'[Ff]ibra\s*bruta',
        r'[Ff]ibra(?:s)?',
        r'[Mm]at[ée]ria\s*fibrosa',
        r'[Cc]elulose(?:\s*bruta)?',
    ],
    'calcium': [
        r'[Cc][áa]lcio',
    ],
    'phosphorus': [
        r'[Ff][óo]sforo',
    ],
    'magnesium': [
        r'[Mm]agn[ée]sio',
    ]
}

def extract_nutrient_value(text, pattern_list):
    """
    Search for a nutrient pattern and extract its float value in percent.
    Supports decimal commas, nonbreaking spaces, and optional % sign.
    """
    for pat in pattern_list:
        regex = rf'(?:{pat})[:\s]+(\d+(?:[.,]\d+)?)(?:\s*%)?(?:[;\s,\|\.]|$)'
        m = re.search(regex, text, re.I)
        if m:
            val_str = m.group(1).replace(',', '.')
            try:
                val = float(val_str)
                # Basic sanity range for food percentages
                if 0.0 <= val <= 100.0:
                    return val
            except ValueError:
                pass
    return None

def extract_taurine(text):
    """
    Extract taurine value and preserve declared unit (% or mg/kg).
    """
    # Check mg/kg or g/kg first
    m_mg = re.search(r'[Tt]aurina[:\s]+(\d+(?:[.,]\d+)?)\s*(?:mg/kg|mg\s*/\s*kg)', text, re.I)
    if m_mg:
        try:
            return {'value': float(m_mg.group(1).replace(',', '.')), 'unit': 'mg/kg', 'status': FieldStatus.VALID}
        except ValueError:
            pass

    # Check %
    m_pct = re.search(r'[Tt]aurina[:\s]+(\d+(?:[.,]\d+)?)\s*%', text, re.I)
    if m_pct:
        try:
            return {'value': float(m_pct.group(1).replace(',', '.')), 'unit': '%', 'status': FieldStatus.VALID}
        except ValueError:
            pass

    # Generic number
    m_gen = re.search(r'[Tt]aurina[:\s]+(\d+(?:[.,]\d+)?)', text, re.I)
    if m_gen:
        try:
            v = float(m_gen.group(1).replace(',', '.'))
            unit = 'mg/kg' if v > 10.0 else '%'
            return {'value': v, 'unit': unit, 'status': FieldStatus.VALID}
        except ValueError:
            pass

    return {'value': None, 'unit': None, 'status': FieldStatus.MISSING}

def validate_composition(composition_text):
    """
    Distinguishes valid composition from marketing copy or empty extraction.
    """
    if not composition_text or not isinstance(composition_text, str):
        return {'status': FieldStatus.MISSING, 'text': '', 'reason': 'missing'}
    
    clean = composition_text.strip()
    if not clean:
        return {'status': FieldStatus.MISSING, 'text': '', 'reason': 'empty'}

    # If it contains known marketing description prefixes, reject as composition
    if clean.startswith('Caraterísticas') or clean.startswith('Descrição:'):
        return {'status': FieldStatus.INVALID, 'text': clean, 'reason': 'marketing_description_extracted_as_composition'}

    # Minimum semantic check: composition should contain some ingredient terms
    common_markers = ['carne', 'peixe', 'subprodutos', 'frango', 'vitela', 'peru', 'salmão', 'cereais', 'água', 'caldo']
    if not any(k in clean.lower() for k in common_markers) and len(clean) < 15:
        return {'status': FieldStatus.INVALID, 'text': clean, 'reason': 'unrecognized_composition_structure'}

    return {'status': FieldStatus.VALID, 'text': clean, 'reason': None}

def normalize_nutrients(raw_text, category='wet'):
    """
    Parses analytical constituents from raw nutrition text without imputation.
    Returns normalized dictionary with per-field statuses and verified totals.
    """
    result = {
        'status': FieldStatus.VALID,
        'protein': {'value': None, 'status': FieldStatus.MISSING},
        'fat': {'value': None, 'status': FieldStatus.MISSING},
        'moisture': {'value': None, 'status': FieldStatus.MISSING},
        'ash': {'value': None, 'status': FieldStatus.MISSING},
        'fiber': {'value': None, 'status': FieldStatus.MISSING},
        'calcium': {'value': None, 'status': FieldStatus.MISSING},
        'phosphorus': {'value': None, 'status': FieldStatus.MISSING},
        'magnesium': {'value': None, 'status': FieldStatus.MISSING},
        'taurine': {'value': None, 'unit': None, 'status': FieldStatus.MISSING},
        'dm_pct': None,
        'protein_dmb': None,
        'fat_dmb': None,
        'carbs_nfe': None,
        'carbs_dmb': None,
        'ca_p_ratio': None
    }

    if not raw_text or not isinstance(raw_text, str):
        result['status'] = FieldStatus.MISSING
        return result

    # Reject known footer/newsletter extraction
    if 'As novidades mais frescas' in raw_text or 'Subscreva e descubra' in raw_text:
        result['status'] = FieldStatus.INVALID
        result['rejection_reason'] = 'newsletter_footer_detected'
        return result

    clean = raw_text.replace('\xa0', ' ')

    for key, patterns in NUTRIENT_PATTERNS.items():
        val = extract_nutrient_value(clean, patterns)
        if val is not None:
            result[key] = {'value': val, 'status': FieldStatus.VALID}

    result['taurine'] = extract_taurine(clean)

    # Ca:P ratio calculation if both minerals are present and P > 0
    ca = result['calcium']['value']
    p = result['phosphorus']['value']
    if ca is not None and p is not None and p > 0:
        result['ca_p_ratio'] = round(ca / p, 2)

    # Validate impossible totals: sum of macros cannot exceed 100% (+ 2% rounding tolerance)
    macros = [result[k]['value'] for k in ['protein', 'fat', 'moisture', 'ash', 'fiber'] if result[k]['value'] is not None]
    if macros and sum(macros) > 102.0:
        result['status'] = FieldStatus.INVALID
        result['rejection_reason'] = f'macro_sum_exceeds_100 ({round(sum(macros), 1)}%)'
        return result

    # Moisture and Dry Matter Calculation:
    # Strictly require declared moisture. NO default 80% or 8% substitution!
    moisture_val = result['moisture']['value']
    if moisture_val is not None:
        dm = max(1.0, 100.0 - moisture_val)
        result['dm_pct'] = round(dm, 1)

        if result['protein']['value'] is not None:
            result['protein_dmb'] = round((result['protein']['value'] / dm) * 100.0, 1)
        if result['fat']['value'] is not None:
            result['fat_dmb'] = round((result['fat']['value'] / dm) * 100.0, 1)

    # Carbohydrates by Difference (NFE):
    # Strictly require all 5 macros declared.
    all_5_present = all(result[k]['value'] is not None for k in ['protein', 'fat', 'moisture', 'ash', 'fiber'])
    if all_5_present:
        prot = result['protein']['value']
        fat = result['fat']['value']
        moist = result['moisture']['value']
        ash = result['ash']['value']
        fib = result['fiber']['value']
        carbs = max(0.0, 100.0 - (prot + fat + moist + ash + fib))
        result['carbs_nfe'] = round(carbs, 1)

        if result['dm_pct'] is not None:
            result['carbs_dmb'] = round((carbs / result['dm_pct']) * 100.0, 1)

    return result

def check_scoring_readiness(product, category='wet'):
    """
    Evaluates whether a product has sufficient evidence to receive an official ranked score.
    Returns (is_ready: bool, reasons: list[str]).
    """
    reasons = []

    # 1. Composition validation
    comp_val = validate_composition(product.get('ingredients'))
    if comp_val['status'] != FieldStatus.VALID:
        reasons.append('missing_composition' if comp_val['status'] == FieldStatus.MISSING else 'invalid_composition')

    # 2. Nutrition validation
    nutri = product.get('nutrition_normalized')
    if not nutri:
        nutri = normalize_nutrients(product.get('nutrition_raw', ''), category=category)

    if nutri.get('status') == FieldStatus.INVALID:
        reasons.append(f"invalid_nutrition ({nutri.get('rejection_reason', 'unknown')})")
    elif nutri.get('status') == FieldStatus.MISSING:
        reasons.append('missing_nutrition')
    else:
        # Check required analytical constituents
        if category == 'dry':
            # EU Reg 767/2009: moisture is optional on dry kibble (<= 14%). Core requirements: protein, fat, ash, fiber.
            required = ['protein', 'fat', 'ash', 'fiber']
        else:
            # Wet food: moisture is mandatory (> 14%). Fiber is negligible (<0.5%) and optional.
            required = ['protein', 'fat', 'moisture', 'ash']

        missing_constituents = [k for k in required if nutri.get(k, {}).get('value') is None]
        if missing_constituents:
            reasons.append('missing_analytical_constituents')

    # 3. Suitability & Completeness check
    classification = product.get('classification')
    if classification == 'complementary':
        reasons.append('complementary_food_excluded')
    elif classification == 'unknown' or not classification:
        # Check text clues
        text = f"{product.get('name', '')} {product.get('description', '')}".lower()
        if 'complementar' in text or 'snack' in text:
            reasons.append('complementary_food_excluded')

    is_ready = len(reasons) == 0
    return is_ready, reasons

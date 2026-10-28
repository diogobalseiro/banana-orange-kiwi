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
        r'[Pp]rote[íi]na(?:s)?\s*(?:bruta(?:s)?)?',
        r'[Cc]rude\s+[Pp]rotein',
    ],
    'fat': [
        r'[Óó]leos\s*e\s*gorduras\s*(?:brutos?|brutas?)?',
        r'[Mm]at[ée]ria(?:s)?\s*gorda(?:s)?(?:[,\s]*bruta(?:s)?)?',
        r'[Gg]ordura(?:s)?\s*(?:bruta(?:s)?)?',
        r'[Tt]eor\s*de\s*(?:matéria\s+gorda|gordura)',
        r'[Ll][íi]pidos\s*(?:totais|brutos)?',
    ],
    'moisture': [
        r'[Hh]umidade(?:\s*(?:\(m[áa]x\.?\)|m[áa]x(?:ima)?\.?))?',
        r'[Tt]eor\s*de\s*(?:humidade|[áa]gua)',
        r'[Uu]midade',
        r'[Hh][úu]midade',
        r'[Mm]oisture',
    ],
    'ash': [
        r'[Cc]inza(?:s)?\s*(?:bruta(?:s)?|totais|total|residual)?',
        r'[Mm]at[ée]ria\s*inorg[âa]nica',
        r'[Rr]es[íi]duo\s*incandescente',
    ],
    'fiber': [
        r'[Ff]ibra(?:s)?\s*(?:bruta(?:s)?|alimentar(?:es)?|diet[ée]tica)?',
        r'[Mm]at[ée]ria\s*fibrosa',
        r'[Cc]elulose(?:\s*bruta)?',
    ],
    'calcium': [r'[Cc][áa]lcio\b', r'\bCa\b'],
    'phosphorus': [r'[Ff][óo]sforo\b', r'\bP\b'],
    'magnesium': [r'[Mm]agn[ée]sio\b', r'\bMg\b']
}

def extract_nutrient_value(text, pattern_list):
    """
    Search for a nutrient pattern and extract its float value in percent.
    Supports suffix notation (Proteína 10%), prefix notation (10% proteína),
    decimal commas, nonbreaking spaces, and optional % sign while preventing
    delimiter backtracking on decimal points before non-percent units (e.g. mg).
    """
    is_magnesium = any(re.search(r'magn|\bmg\b', re.sub(r'\[.*?\]', 'm', p), re.I) for p in pattern_list)

    for pat in pattern_list:
        # 1. Suffix notation: e.g. "Proteína bruta: 10.0%" or "Proteína 10,0"
        m_suffix = re.search(rf'(?:{pat})[:\s]+(\d+(?:[.,]\d+)?)(?![.,\d])\s*(%|[a-zA-Z/]+)?', text, re.I)
        if m_suffix:
            unit = m_suffix.group(2) or ''
            # Ensure not followed by non-percent units like mg, g, kcal, etc.
            if not re.match(r'^(?:mg|g|kcal|ui|iu|kg|mcg)\b', unit, re.I):
                try:
                    val = float(m_suffix.group(1).replace(',', '.'))
                    # For magnesium, biological maximum in cat food is 0.3% (anything higher is mg/kg or invalid)
                    if not (is_magnesium and val > 0.3):
                        if 0.0 <= val <= 100.0:
                            return val
                except ValueError:
                    pass

        # 2. Prefix notation: e.g. "10% proteína bruta", "10% de proteína", ", 5% matéria gorda"
        m_prefix = re.search(rf'(?:^|[,;\n\r\t•\-\|\(]|\b(?:com|contém|contem|teor\s+de)\s+)\s*(\d+(?:[.,]\d+)?)\s*%\s*(?:de\s*)?(?:{pat})', text, re.I)
        if m_prefix:
            try:
                val = float(m_prefix.group(1).replace(',', '.'))
                if not (is_magnesium and val > 0.3):
                    if 0.0 <= val <= 100.0:
                        return val
            except ValueError:
                pass
    return None

def extract_taurine(text):
    """
    Extract taurine value and preserve declared unit (% or mg/kg).
    Handles space and dot thousands separators, additive identification codes, and g/kg conversions.
    """
    if not text or not isinstance(text, str):
        return {'value': None, 'unit': None, 'status': FieldStatus.MISSING}

    # Normalize space thousands separators e.g. "2 130 mg" -> "2130 mg" and dot thousands "2.130 mg" -> "2130 mg"
    normalized = re.sub(r'(\d+)\s+(\d{3})\b', r'\1\2', text)
    normalized = re.sub(r'(\d+)\.(\d{3})\s*(?:mg|ui|iu)', r'\1\2 mg', normalized, flags=re.I)

    # Check mg/kg or mg with optional additive code e.g. "Taurina (3a370): 2130 mg/kg" or "Taurine 3a370 2130 mg"
    m_mg = re.search(r'[Tt]aurin[ae](?:\s*(?:\([^)]*\)|3a\d+))?[:\s]+(\d+(?:[.,]\d+)?)\s*(?:mg/kg|mg\s*/\s*kg|mg\b)', normalized, re.I)
    if m_mg:
        try:
            return {'value': float(m_mg.group(1).replace(',', '.')), 'unit': 'mg/kg', 'status': FieldStatus.VALID}
        except ValueError:
            pass

    # Check g/kg e.g. "Taurina 0.25 g/kg" -> 250 mg/kg
    m_g = re.search(r'[Tt]aurin[ae](?:\s*(?:\([^)]*\)|3a\d+))?[:\s]+(\d+(?:[.,]\d+)?)\s*(?:g/kg|g\s*/\s*kg)', normalized, re.I)
    if m_g:
        try:
            return {'value': float(m_g.group(1).replace(',', '.')) * 1000.0, 'unit': 'mg/kg', 'status': FieldStatus.VALID}
        except ValueError:
            pass

    # Check % e.g. "Taurina: 0.15%"
    m_pct = re.search(r'[Tt]aurin[ae](?:\s*(?:\([^)]*\)|3a\d+))?[:\s]+(\d+(?:[.,]\d+)?)\s*%', normalized, re.I)
    if m_pct:
        try:
            v = float(m_pct.group(1).replace(',', '.'))
            if v <= 1.0: # Normal dietary taurine is 0.05% - 0.3%
                return {'value': v, 'unit': '%', 'status': FieldStatus.VALID}
            else:
                return {'value': v, 'unit': 'mg/kg', 'status': FieldStatus.VALID}
        except ValueError:
            pass

    # Generic number
    m_gen = re.search(r'[Tt]aurin[ae](?:\s*(?:\([^)]*\)|3a\d+))?[:\s]+(\d+(?:[.,]\d+)?)', normalized, re.I)
    if m_gen:
        try:
            v = float(m_gen.group(1).replace(',', '.'))
            unit = 'mg/kg' if v > 1.0 else '%'
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
    if re.match(r'^\s*(?:caracter[íi]sticas|carater[íi]sticas|descri[çc][ãa]o(?:\s+do\s+produto)?|benef[íi]cios|vantagens)\s*[:\-]', clean, re.I):
        return {'status': FieldStatus.INVALID, 'text': clean, 'reason': 'marketing_description_extracted_as_composition'}

    # Minimum semantic check: composition should contain some recognized ingredient terms
    common_markers = [
        'carne', 'peixe', 'subproduto', 'derivado', 'ave', 'aves', 'frango', 'vitela', 'vaca', 'peru', 
        'salmão', 'salmao', 'atum', 'pato', 'borrego', 'cordeiro', 'bovino', 'porco', 'suíno', 'presunto',
        'coelho', 'javali', 'cereais', 'arroz', 'trigo', 'milho', 'ervilha', 'água', 'agua', 'caldo', 
        'levedura', 'mineral', 'minerais', 'óleo', 'oleo', 'gordura', 'vegeta', 'legume', 'extrato',
        'proteína', 'proteina', 'ingrediente', 'bacalhau', 'arenque', 'sardinha', 'truta', 'veado',
        'cavala', 'galinha', 'codorniz', 'pescada', 'anchova', 'mexilhão', 'camarão', 'lebre', 'cabrito'
    ]
    if not any(k in clean.lower() for k in common_markers):
        return {'status': FieldStatus.INVALID, 'text': clean, 'reason': 'no_ingredient_terms_found'}

    if len(clean) < 10 and not any(p in clean for p in ['%', '(', ',']):
        return {'status': FieldStatus.INVALID, 'text': clean, 'reason': 'composition_too_short'}

    return {'status': FieldStatus.VALID, 'text': clean, 'reason': None}

def extract_first_ingredient(text):
    """
    Extracts the clean first ingredient from composition text, stripping
    introductory headers and respecting parenthetical nesting and decimal commas.
    """
    if not text or not isinstance(text, str):
        return None

    # Only strip leading header if at the beginning of the text (allows periods in preamble)
    m = re.match(r'^\s*(?:alimento\s+[^:\n]+)?(?:ingredientes|composição|ingredients|composition)(?:\s+de\s+[^:\n]+)?[:\-]?\s*', text, flags=re.I)
    if m:
        clean = text[m.end():].strip()
    else:
        clean = text.strip()

    # Strip optional flavor prefix like "com frango:" or "variedade frango:"
    clean = re.sub(r'^(?:(?:com|variedade(?:\s+de)?|pedaços\s+com|paté\s+de)\s+[a-zá-ú\s]+:)\s*', '', clean, flags=re.I).strip()
    
    # Split on first comma/semicolon/newline/bullet outside parentheses, preserving decimal commas
    depth = 0
    first_part = []
    for i, char in enumerate(clean):
        if char in '([':
            depth += 1
        elif char in ')]':
            depth = max(0, depth - 1)
        elif char in [',', ';', '\n', '\r', '•'] and depth == 0:
            # Preserve decimal comma (e.g. 38,7%)
            if char == ',' and i > 0 and i < len(clean) - 1 and clean[i-1].isdigit() and clean[i+1].isdigit():
                first_part.append(char)
                continue
            break
        first_part.append(char)
    res = "".join(first_part).strip()
    res = re.sub(r'[:\-]+$', '', res).strip()
    return res if res else None

def extract_total_meat_percentage(text):
    """
    Extracts genuine meat and animal tissue percentages from composition text.
    Handles adjectives, prevents sub-ingredient double counting, avoids multipack inflation,
    detects 4% EU marketing tokens, and respects overall declarations.
    """
    if not text or not isinstance(text, str):
        return None
    lower = text.lower()
    
    # 1. Check 4% EU marketing token trick first: 'carnes e subprodutos animais (dos quais 4% vitela)'
    is_token_4pct = bool(
        re.search(r'(?:carnes?|peixes?)\s+e\s+(?:subprodutos|derivados)[^)]*?\b4\s*%', lower) or
        re.search(r'(?:dos\s+quais|das\s+quais|m[íi]n(?:imo)?\.?)\s*\b4\s*%', lower)
    )
    if is_token_4pct:
        return 4

    # 2. Check explicit overall declaration (true umbrella meat/poultry/fish declarations only):
    # Prefix: '70% aves', '70% de carne', '65% ingredientes de origem animal'
    # Suffix: 'aves 70%', 'carne (70%)'
    meat_overall = r'carne(?:s)?|aves|peixe(?:s)?|ingredientes\s+(?:de\s+origem\s+)?animais|conteúdo\s+de\s+carne|total\s+de\s+carne'
    
    m_overall_pre = re.search(rf'(\d+)\s*%\s*(?:de\s*)?(?:{meat_overall})', lower)
    if m_overall_pre and int(m_overall_pre.group(1)) >= 20:
        return int(m_overall_pre.group(1))
        
    m_overall_suf = re.search(rf'(?:{meat_overall})\s*(?:\([^)]*?\)\s*)?\(?(\d+)\s*%\)?', lower)
    if m_overall_suf and int(m_overall_suf.group(1)) >= 20:
        return int(m_overall_suf.group(1))

    # 3. Check if this is a multipack with multiple recipes ('com frango:', 'com vaca:')
    # If multipack, take the percentage of the first recipe to prevent pouch summation
    recipes = re.split(r'(?:com|variedade)\s+[a-zá-ú\s]+:', lower)
    if len(recipes) > 1:
        text_to_eval = recipes[1]
    else:
        text_to_eval = lower

    # Pre-clean sub-ingredient percentage double counting:
    # A. Strip sub-percentages that follow an already-declared parent percentage (e.g. '16% das quais 50%')
    text_to_eval = re.sub(r'(\d+\s*%\s*(?:,\s*)?(?:das?|dos?)\s+qua(?:is|l)\s+[^,.)]*?)\d+(?:[.,]\d+)?\s*%', r'\1', text_to_eval, flags=re.I)

    # B. Strip parenthetical breakdown immediately following a percentage: '(54%) (frango fresco 26%, ...)'
    text_to_eval = re.sub(r'(\(\d+%\))\s*\([^)]*?\d+%\s*[^)]*?\)', r'\1', text_to_eval)

    # C. Strip cooking broth and oils/fats before evaluating declared meats
    text_to_eval = re.sub(r'\b(?:caldo|gordura|molho|óleo|oleo)\s+(?:de\s+)?[a-zá-ú\s]+?\d+(?:[.,]\d+)?\s*%', '', text_to_eval, flags=re.I)

    # D. Strip hydrolysates / digests and their sub-percentages (e.g. 'proteínas animais hidrolisadas (aves min. 20%)')
    text_to_eval = re.sub(r'\b(?:proteínas?\s+(?:animais\s+)?hidrolisadas?|hidrolisad[oa]\s+de\s+[a-zá-ú\s]+)\s*\([^)]*?\d+(?:[.,]\d+)?\s*%\)', '', text_to_eval, flags=re.I)
    text_to_eval = re.sub(r'\b(?:proteínas?\s+(?:animais\s+)?hidrolisadas?|hidrolisad[oa]\s+de\s+[a-zá-ú\s]+)\s*(?:m[íi]n\.?\s*)?\d+(?:[.,]\d+)?\s*%', '', text_to_eval, flags=re.I)

    # 4. Extract and sum individual declared named meats
    meat_names = (
        'carne|frango|peru|salmão|salmao|atum|vaca|peixe|pato|borrego|cordeiro|'
        'javali|coelho|aves|sardinha|arenque|truta|codorniz|veado|miudezas|'
        'bovino|vitela|porco|suíno|bacalhau|galinha|cavala|pescada|lula|polvo|camarão|mexilhão'
    )
    adjectives = r'(?:\s+(?:fresco|fresca|desidratado|desidratada|cru|crua|inteiro|inteira|desossado|desossada|seco|seca|limpo|limpa|hidrolisado|hidrolisada|sem\s+espinhas|de\s+capoeira)){0,2}'

    pat_before = rf'(\d+)\s*%\s*(?:de\s*)?(?:{meat_names})'
    pat_after = rf'(?:{meat_names}){adjectives}\s*(?:\([^)]*?\))?\s*(?:m[íi]n\.?\s*)?\(?(\d+)\s*%\)?'
    
    matches = re.findall(rf'(?:{pat_before}|{pat_after})', text_to_eval)
    pcts = []
    for g1, g2 in matches:
        v = g1 or g2
        if v and int(v) > 4:
            pcts.append(int(v))
            
    if pcts:
        return min(100, sum(pcts))
    return None

def check_has_organs(ingr_text):
    """
    Evaluates whether genuine feline organ superfoods (liver, heart, gizzard, lung, kidney)
    are present in the composition.
    Enzymatic palatability hydrolysates and digests (e.g. 'hidrolisado de fígado de frango',
    'digest de fígado') are strictly excluded as they are flavor additives, not whole organ meats.
    """
    if not ingr_text or not isinstance(ingr_text, str):
        return False
    lower = ingr_text.lower()
    cleaned = re.sub(r'\b(?:hidrolisad[oa]\s+de\s+|fígado\s+hidrolisado|figado\s+hidrolisado|digest\s+de\s+|fígado\s+desidratado\s+em\s+pó\s+como\s+aroma)[a-zá-ú\s]+', '', lower)
    organ_terms = [
        'coração', 'corações', 'fígado', 'figado', 'moela', 'moelas',
        'pulmão', 'pulmões', 'estômago', 'estômagos', 'rins', 'rim', 'miudezas'
    ]
    return any(o in cleaned for o in organ_terms)

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

    # Validate impossible totals: sum of macros cannot exceed 100% (+ 4% statutory tolerance under EU 767/2009)
    macros = [result[k]['value'] for k in ['protein', 'fat', 'moisture', 'ash', 'fiber'] if result[k]['value'] is not None]
    if macros and sum(macros) > 104.0:
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
    elif category == 'wet' and all(result[k]['value'] is not None for k in ['protein', 'fat', 'moisture', 'ash']):
        # Under EU Reg 767/2009, crude fiber is optional on wet food when negligible (<0.5%).
        # Use standard negligible fiber allowance (0.2%) for NFE calculation
        prot = result['protein']['value']
        fat = result['fat']['value']
        moist = result['moisture']['value']
        ash = result['ash']['value']
        fib = 0.2
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
    classification = str(product.get('classification') or '').lower()
    if classification in ['complementary', 'complementar']:
        reasons.append('complementary_food_excluded')
    elif classification in ['unknown', ''] or not classification:
        # Check text clues
        text = f"{product.get('name', '')} {product.get('description', '')}".lower()
        if 'complementar' in text or 'snack' in text:
            reasons.append('complementary_food_excluded')

    is_ready = len(reasons) == 0
    return is_ready, reasons

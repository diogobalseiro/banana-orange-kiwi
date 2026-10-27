import re
from .evidence import normalize_nutrients, validate_composition, check_scoring_readiness, extract_first_ingredient, extract_total_meat_percentage, FieldStatus

def parse_wet_nutrition(nutri_text):
    return normalize_nutrients(nutri_text, category='wet')

def get_wet_carb_band(carbs_dmb):
    if carbs_dmb is None:
        return 'N/D'
    if carbs_dmb <= 10.0:
        return '<=10% DMB (Ideal)'
    elif carbs_dmb <= 20.0:
        return '10-20% DMB (Moderado)'
    else:
        return '>20% DMB (Elevado)'

def score_wet_product(p):
    name = p.get('name') or ''
    brand = p.get('brand') or ''
    desc = p.get('description') or ''
    ingr = p.get('ingredients') or ''
    nutri_raw = p.get('nutrition_raw') or ''

    text_to_check = f"{name} {desc} {ingr} {nutri_raw}".lower()
    title_desc = f"{name} {desc}".lower()
    brand_lower = brand.lower()
    name_lower = name.lower()

    # 0. Non-food items mistakenly crawled into food categories
    non_food_markers = ['arranhador', 'tapete para', 'comedouro', 'bebedouro', 'brinquedo', 'tampa para lata', 'areia para', 'toalhete', 'escova', 'coleira']
    if any(k in name_lower for k in non_food_markers):
        return None, None

    # 1. Classification: Complete vs Complementary
    # Broth/soup/fillets indicate complementary food when in title/description, NOT when in ingredients (cooking broth)
    # Word boundaries prevent false matches like "ensopado" matching "sopa"
    is_complementary = False
    title_comp_pattern = r'\b(?:sopa|soup|caldo|broth|hydra\s+care|shinycat|suplemento|iogurte|leite\s+para\s+gato|cat\s+milk|fillets|filetes|snack|petisco|treat)\b'
    general_comp_keywords = [
        'complementar', 'alimento complementar', 'complemento alimentar'
    ]

    is_complete_declared = bool(re.search(
        r'\b(?:alimento\s+(?:\w+\s+){0,2}complet[oa]|100%\s*complete?|complete\s+(?:\w+\s+){0,2}(?:pet\s+food|cat\s+food|food|diet))\b',
        text_to_check, re.I
    ))

    if any(k in text_to_check for k in general_comp_keywords) or re.search(title_comp_pattern, title_desc, re.I):
        if not is_complete_declared:
            is_complementary = True
    elif any(b in brand_lower for b in ['schesir', 'ciao', 'churu', 'applaws', 'fish4cats', 'inaba', 'thrive', 'encore', 'cosma']):
        if not is_complete_declared:
            is_complementary = True

    if is_complementary or p.get('classification') in ['Complementar', 'complementary']:
        # Exclude complementary foods (snacks, treats, soups) entirely to focus on complete diets
        return None, None

    classification = 'Completo'

    # Target: Kitten / Junior
    is_kitten = any(k in f"{name_lower} {desc.lower()}" for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote', 'crescimento'])

    # 2. Composition Validation
    comp_eval = validate_composition(ingr)
    has_valid_composition = (comp_eval['status'] == FieldStatus.VALID)

    first_ingr = None
    first_is_fresh_animal = False
    first_is_named_meat = False
    first_is_vague_animal = False
    first_is_plant = False
    has_sugar = None
    has_grains = None
    has_veg_protein = None
    has_organs = None
    has_carrageenan = None
    has_gums = None
    high_meat_pct = None
    is_token_4pct = False
    has_vague_byproducts = False
    is_monoproteic = False

    if has_valid_composition:
        ingr_clean_text = comp_eval['text']
        ingr_lower = ingr_clean_text.lower()

        # First ingredient check
        first_ingr = extract_first_ingredient(ingr_clean_text)
        if first_ingr:
            first_lower = first_ingr.lower()

            animal_terms = [
                'frango', 'salmão', 'salmao', 'peru', 'vaca', 'carne', 'peixe', 'atum', 'borrego', 'aves', 'pato',
                'coelho', 'javali', 'sardinha', 'arenque', 'truta', 'veado', 'cordeiro', 'vitela', 'bovino', 'porco',
                'suíno', 'bacalhau', 'galinha', 'cavala', 'pescada', 'anchova', 'codorniz', 'caça', 'cervo', 'ovo', 'ovos'
            ]
            fresh_terms = ['fresco', 'fresca', 'desossado', 'desossada', 'frescos', 'frescas', 'cru', 'crua', 'crus', 'cruas', 'filete', 'filetes', 'lombo', 'peito']
            plant_terms = ['milho', 'trigo', 'cereais', 'arroz', 'ervilha', 'batata', 'farinha', 'glúten', 'proteína vegetal', 'cevada', 'subprodutos de origem vegetal', 'subprodutos vegetais', 'soja', 'aveia', 'legumes']

            if any(f in first_lower for f in fresh_terms) and any(a in first_lower for a in animal_terms):
                first_is_fresh_animal = True
            elif ('carne e subprodutos' in first_lower or 'carnes e subprodutos' in first_lower or 'subprodutos animais' in first_lower or 'subprodutos de aves' in first_lower):
                first_is_vague_animal = True
            elif any(a in first_lower for a in animal_terms):
                first_is_named_meat = True
            elif any(p in first_lower for p in plant_terms):
                first_is_plant = True

        # Genuine named meat percentage & token trick match
        raw_meat_pct = extract_total_meat_percentage(ingr_clean_text)
        if raw_meat_pct == 4:
            is_token_4pct = True
            high_meat_pct = None
        else:
            high_meat_pct = raw_meat_pct

        # Organ meats
        has_organs = any(o in ingr_lower for o in [
            'coração', 'corações', 'fígado', 'figado', 'moela', 'moelas', 'pulmão', 'pulmões', 'estômago', 'estômagos', 'rins', 'rim', 'miudezas'
        ])

        # Monoproteic
        is_monoproteic = any(m in text_to_check for m in ['monoproteico', 'mono-proteico', 'monoproteica', 'single protein', 'uma única fonte de proteína'])

        # Detrimental additives
        clean_sugar_text = re.sub(r'\b(?:fibra\s+de\s+)?cana-de-a[çc][úu]car\b', '', ingr_lower, flags=re.I)
        has_sugar = any(s in clean_sugar_text for s in ['açúcar', 'açúcares', 'açucar', 'açucares', 'caramelo', 'xarope', 'dextrose', 'melaço'])
        if has_sugar and any(neg in clean_sugar_text for neg in [
            'sem açúcar', 'sem açucares', 'sem açúcares', 'sem acucar', 'não contém açúcar', 'não contém açúcares',
            'nao contem acucar', 'sem adição de açúcar', 'sem adição de açúcares', 'sem adicao de acucar', 'sem adicao de acucares',
            'sem açúcares adicionados', 'sem acucares adicionados', '0% açúcar', '0% açúcares', 'isento de açúcar', 'isento de açúcares'
        ]):
            has_sugar = False

        neg_grain_pat = r'\b(?:0%|zero%?|sem|isento\s+de|não\s+contém|nao\s+contem|livre\s+de)\s+(?:adição\s+de\s+|adicao\s+de\s+|de\s+)?(?:cereais|grãos|graos|glúten|gluten|trigo|milho|arroz|aveia|soja)(?:\s*(?:,|nem|ou|e)\s*(?:adição\s+de\s+|adicao\s+de\s+|de\s+)?(?:trigo|milho|arroz|aveia|soja|cereais|glúten|gluten|grãos|graos))*\b'
        clean_grain_text = re.sub(neg_grain_pat, '', ingr_lower, flags=re.I)
        has_grains = bool(re.search(r'\b(?:cereais|trigo|milho|arroz|farinha\s+de\s+trigo|farinha\s+de\s+milho|aveia|cevada|centeio|sorgo)\b', clean_grain_text, re.I))

        has_veg_protein = bool(re.search(r'\b(?:subprodutos\s+de\s+origem\s+vegetal|subprodutos\s+vegetais|extra[ct]+os?\s+de\s+prote[íi]na(?:s)?\s+vegeta(?:l|is)|concentrados?\s+de\s+prote[íi]na(?:s)?\s+vegeta(?:l|is))\b', ingr_lower, re.I))

        # Check slaughterhouse byproducts & derivatives (meat and fish), suppressed only if meat >= 50%
        has_vague_derivs = bool(re.search(r'\b(?:carnes?|peixes?)\s+e\s+(?:subprodutos|derivados)|subprodutos\s+(?:animais|de\s+peixe)\b', ingr_lower, re.I))
        has_vague_byproducts = has_vague_derivs and (not high_meat_pct or high_meat_pct < 50) and not is_token_4pct

        has_carrageenan = any(c in ingr_lower for c in ['carragenina', 'carragenano', 'carrageenan', 'e407'])
        if has_carrageenan and any(neg in ingr_lower for neg in ['sem carragenina', 'sem carragenano', 'carrageenan free', 'isento de carragenina']):
            has_carrageenan = False

        has_gums = any(g in ingr_lower for g in ['goma cássia', 'goma cassia', 'cassia gum', 'e499'])

    # Beneficial micronutrients
    has_taurine = any(t in text_to_check for t in ['taurina', 'taurine'])
    has_marine_omega = bool(re.search(r'\b(?:epa|dha)\b', text_to_check, re.I)) or any(o in text_to_check for o in ['óleo de salmão', 'oleo de salmao', 'óleo de peixe', 'oleo de peixe', 'ómega-3', 'omega-3', 'salmon oil', 'fish oil'])

    # 3. Parse Analytical Components using Evidence Contract
    nutri = normalize_nutrients(nutri_raw, category='wet')
    p['nutrition_parsed'] = nutri

    # 4. Check Scoring Readiness Gate
    temp_p = dict(p)
    temp_p['classification'] = 'complementary' if is_complementary else 'complete'
    temp_p['nutrition_normalized'] = nutri
    is_ready, unranked_reasons = check_scoring_readiness(temp_p, category='wet')

    score = None
    tier = 'Unranked'
    val_ratio = None
    cb = get_wet_carb_band(nutri.get('carbs_dmb'))
    pkg = p.get('unit_price_kg')
    try:
        pkg = float(pkg) if pkg is not None else None
    except (ValueError, TypeError):
        pkg = None

    if is_ready:
        score = 50

        # 1. Meat content & quality
        if high_meat_pct and high_meat_pct >= 70:
            score += 22
        elif high_meat_pct and high_meat_pct >= 50:
            score += 15
        elif high_meat_pct and high_meat_pct >= 30:
            score += 8

        if has_organs:
            score += 5
        if is_monoproteic:
            score += 3

        # Penalties for low-grade slaughter derivatives and plant fillers
        if first_is_plant:
            score -= 20
        if first_is_vague_animal:
            score -= 8
        if is_token_4pct:
            score -= 15
        elif has_vague_byproducts:
            score -= 12

        # 2. Fillers & Additives
        if has_sugar:
            score -= 25
        if has_grains:
            if high_meat_pct and high_meat_pct >= 60:
                score -= 8
            else:
                score -= 15
        if has_veg_protein:
            score -= 15
        if has_carrageenan:
            score -= 6
        if has_gums:
            score -= 3

        # 3. Beneficial Additives
        if has_taurine:
            score += 4
        if has_marine_omega:
            score += 3

        # 4. Analytical Macronutrients
        prot_dmb = nutri.get('protein_dmb')
        if prot_dmb is not None:
            target_high_prot = 50.0 if is_kitten else 55.0
            if prot_dmb >= target_high_prot:
                score += 12
            elif prot_dmb >= 45.0:
                score += 5
            elif prot_dmb < 35.0:
                score -= 15

        carbs_dmb = nutri.get('carbs_dmb')
        if carbs_dmb is not None:
            if carbs_dmb <= 10.0:
                score += 10
            elif carbs_dmb <= 20.0:
                score += 3
            else:
                score -= 12

        # 5. Mineral balance (if declared)
        phos_dmb = nutri.get('phosphorus_dmb')
        if phos_dmb is not None and phos_dmb > 1.3 and not is_kitten:
            score -= 8

        ca_p = nutri.get('ca_p_ratio')
        if ca_p is not None:
            if 1.0 <= ca_p <= 1.5:
                score += 4
            elif ca_p > 1.8 or ca_p < 0.9:
                score -= 6

        score = max(10, min(95, score))

        # Grain-inclusive wet food cannot exceed Tier A (ceiling of 79)
        # Reserving Tier S (80+) strictly for grain-free obligate carnivore formulas
        if has_grains and score >= 80:
            score = 79

        # Formulas based on vague slaughterhouse byproducts cannot exceed Tier B (ceiling of 69)
        if first_is_vague_animal and score >= 70:
            score = 69

        # Products relying on 4% EU marketing token trick cannot exceed Tier C (ceiling of 59)
        if is_token_4pct and score >= 60:
            score = 59

        if score >= 80:
            tier = 'Tier S (Ultra-Premium)'
        elif score >= 65:
            tier = 'Tier A (Excelente / Alto Teor Carne)'
        elif score >= 50:
            tier = 'Tier B (Médio-Alto / Boa Relação)'
        elif score >= 35:
            tier = 'Tier C (Básico / Ingredientes Genéricos)'
        else:
            tier = 'Tier D (Evitar / Açúcares e Cereais)'

        if pkg and pkg > 0:
            val_ratio = round(score / pkg, 2)
    else:
        if is_complementary:
            tier = 'Complementar (Excluído)'
        else:
            tier = 'Não classificado (Dados insuficientes)'

    p['score'] = score
    p['tier'] = tier
    p['classification'] = classification
    p['first_ingredient'] = first_ingr
    p['is_kitten'] = is_kitten
    p['is_ranked'] = is_ready
    p['unranked_reasons'] = unranked_reasons
    p['has_sugar'] = has_sugar
    p['has_grains'] = has_grains
    p['has_veg_protein'] = has_veg_protein
    p['has_organs'] = has_organs
    p['has_carrageenan'] = has_carrageenan
    p['has_taurine'] = has_taurine
    p['has_marine_omega'] = has_marine_omega
    p['high_meat_pct'] = high_meat_pct
    p['value_ratio'] = val_ratio
    p['carb_band'] = cb
    p['protein'] = nutri.get('protein', {}).get('value')
    p['fat'] = nutri.get('fat', {}).get('value')

    retailer = p.get('retailer', 'Continente')
    p['retailer'] = retailer

    minified = {
        'id': p.get('pid'),
        'n': name,
        'b': brand,
        'p': p.get('price'),
        'pkg': pkg,
        'c': classification,
        'fi': first_ingr,
        'k': is_kitten,
        't': tier,
        's': score,
        'vr': val_ratio,
        'ir': is_ready,
        'ur': unranked_reasons,
        'sug': has_sugar,
        'grn': has_grains,
        'veg': has_veg_protein,
        'org': has_organs,
        'carr': has_carrageenan,
        'tau': has_taurine,
        'omg': has_marine_omega,
        'meat_pct': high_meat_pct,
        'prot': nutri.get('protein', {}).get('value'),
        'fat': nutri.get('fat', {}).get('value'),
        'carb': nutri.get('carbs_dmb'),
        'cb': cb,
        'u': p.get('pdp_url'),
        'r': retailer,
        'fid': p.get('formulation_id'),
        'rec': p.get('is_reconciled', False),
        'conf': p.get('has_material_conflict', False)
    }
    return p, minified

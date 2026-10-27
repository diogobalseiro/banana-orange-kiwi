import re
from .evidence import normalize_nutrients, validate_composition, check_scoring_readiness, FieldStatus

def parse_dry_nutrition(nutri_text):
    return normalize_nutrients(nutri_text, category='dry')

def get_dry_carb_band(carbs):
    if carbs is None:
        return 'N/D'
    if carbs < 22.0:
        return '<22% (Baixo)'
    elif carbs <= 32.0:
        return '22-32% (Moderado)'
    elif carbs <= 40.0:
        return '32-40% (Elevado)'
    else:
        return '>40% (Muito Alto)'

def score_dry_product(p):
    name = p.get('name', '')
    brand = p.get('brand', '')
    desc = p.get('description', '')
    ingr = p.get('ingredients', '')
    nutri_raw = p.get('nutrition_raw', '')

    text_to_check = f"{name} {desc} {ingr} {nutri_raw}".lower()
    name_lower = name.lower()

    # Target demographics
    is_kitten = any(k in f"{name_lower} {desc.lower()}" for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote', 'crescimento'])
    is_sterilised = any(s in f"{name_lower} {desc.lower()}" for s in ['esterilizado', 'esterilizados', 'sterilised', 'sterilized'])

    # 1. Composition Validation
    comp_eval = validate_composition(ingr)
    has_valid_composition = (comp_eval['status'] == FieldStatus.VALID)

    first_ingr = None
    first_is_fresh_animal = False
    first_is_dehydrated_animal = False
    first_is_plant = False
    meat_pct = None
    is_grain_free = None
    has_cheap_grains = None
    has_quality_grains = None
    has_corn_gluten = None
    has_colorants = None
    has_artificial_preservatives = None
    is_fractionated = None

    if has_valid_composition:
        ingr_clean_text = comp_eval['text']
        ingr_lower = ingr_clean_text.lower()

        # First ingredient check
        clean_ingr = re.sub(r'^(?:ingredientes|composição|composição:)\s*[:\-]?\s*', '', ingr_clean_text, flags=re.I).strip()
        if clean_ingr:
            parts = re.split(r'[,;]\s*', clean_ingr)
            if parts:
                first_ingr = parts[0].strip()
                first_lower = first_ingr.lower()

                animal_terms = ['frango', 'salmão', 'salmao', 'peru', 'vaca', 'carne', 'peixe', 'atum', 'borrego', 'aves', 'pato', 'coelho', 'javali']
                fresh_terms = ['fresco', 'fresca', 'desossado', 'desossada', 'frescos', 'frescas']
                plant_terms = ['milho', 'trigo', 'cereais', 'arroz', 'ervilha', 'batata', 'farinha de trigo', 'farinha de milho', 'glúten', 'proteína vegetal', 'cevada']

                if any(f in first_lower for f in fresh_terms) and any(a in first_lower for a in animal_terms):
                    first_is_fresh_animal = True
                elif any(d in first_lower for d in ['desidratad', 'farinha de', 'proteína de aves', 'proteína de frango', 'proteína de salmão', 'proteína desidratada']) and any(a in first_lower for a in animal_terms):
                    first_is_dehydrated_animal = True
                elif any(a in first_lower for a in animal_terms) and not any(p in first_lower for p in ['proteína de ervilha', 'proteína de batata', 'amido']):
                    first_is_dehydrated_animal = True
                elif any(p in first_lower for p in plant_terms):
                    first_is_plant = True

        # Total animal / meat percentage match
        meat_pct_match = re.search(r'(\d+)\s*%\s*(?:de\s*)?(?:carne|frango|peru|salmão|peixe|vaca|borrego|pato|aves|proteína|ingredientes\s+animais)', ingr_lower)
        meat_pct = int(meat_pct_match.group(1)) if meat_pct_match else None

        # Grains & Starches
        is_grain_free = any(gf in text_to_check for gf in ['sem cereais', 'grain free', 'grain-free', 'no grain'])
        has_cheap_grains = any(cg in ingr_lower for cg in ['trigo', 'milho', 'farinha de trigo', 'farinha de milho', 'cevada cervejeira'])
        has_quality_grains = any(qg in ingr_lower for qg in ['aveia', 'cevada integral', 'arroz integral', 'centeio'])
        has_corn_gluten = any(cg in ingr_lower for cg in ['glúten de milho', 'gluten de milho', 'proteína de milho', 'proteina de milho', 'glúten'])
        has_colorants = any(c in ingr_lower for c in ['corantes', 'corante', 'óxido de ferro', 'oxido de ferro', 'tartrazina', 'dióxido de titânio'])
        has_artificial_preservatives = any(p in text_to_check for p in ['bha', 'bht', 'galato de propilo', 'butil-hidroxianisol', 'butil-hidroxitolueno', 'etoxiquina', 'ethoxyquin', 'e320', 'e321', 'e310'])

        # Fractionation
        legume_starch_markers = [
            'proteína de ervilha', 'proteina de ervilha', 'amido de ervilha', 'farinha de ervilha', 'fibra de ervilha',
            'proteína de batata', 'proteina de batata', 'amido de batata', 'flocos de batata', 'batata desidratada', 'farinha de batata',
            'tapioca', 'amido de mandioca', 'grão-de-bico', 'grao-de-bico', 'lentilhas', 'farinha de favas'
        ]
        split_matches = [m for m in legume_starch_markers if m in ingr_lower]
        fractionation_count = len(split_matches)
        has_pea_protein_early = any(p in ingr_lower[:140] for p in ['proteína de ervilha', 'proteina de ervilha', 'proteína de batata', 'proteina de batata', 'amido de ervilha', 'amido de batata'])
        is_fractionated = fractionation_count >= 2 or has_pea_protein_early

    # Functional additives
    has_urinary_support = any(u in text_to_check for u in ['arando', 'mirtilo', 'cranberry', 'dl-metionina', 'metionina', 'saúde urinária', 'trato urinário', 'controlo de ph'])
    has_taurine = any(t in text_to_check for t in ['taurina', 'taurine'])
    has_marine_omega = any(o in text_to_check for o in ['óleo de salmão', 'oleo de salmao', 'óleo de peixe', 'oleo de peixe', 'salmon oil', 'fish oil', 'dha', 'epa'])

    # 2. Parse analytical components using Evidence Contract
    nutri = normalize_nutrients(nutri_raw, category='dry')
    p['nutrition_parsed'] = nutri

    # 3. Check Scoring Readiness Gate
    temp_p = dict(p)
    temp_p['classification'] = 'complete'
    temp_p['nutrition_normalized'] = nutri
    is_ready, unranked_reasons = check_scoring_readiness(temp_p, category='dry')

    score = None
    tier = 'Unranked'
    val_ratio = None
    cb = get_dry_carb_band(nutri.get('carbs_nfe'))
    pkg = p.get('unit_price_kg')

    if is_ready:
        score = 50

        # 1. First ingredient scoring
        if first_is_fresh_animal:
            score += 18
        elif first_is_dehydrated_animal:
            score += 14
        elif first_is_plant:
            score -= 20
        else:
            score -= 5

        # Total meat percentage
        if meat_pct and meat_pct >= 60:
            score += 12
        elif meat_pct and meat_pct >= 40:
            score += 6

        # 2. Grain, Starch & Fractionation scoring
        if is_grain_free:
            if is_fractionated:
                score -= 8
            elif fractionation_count == 1:
                score += 6
            else:
                score += 12
        else:
            if has_cheap_grains:
                score -= 15
            elif has_quality_grains and not has_cheap_grains:
                score += 4
            else:
                score -= 8

        # Detrimental additives
        if has_corn_gluten:
            score -= 12
        if has_colorants:
            score -= 15
        if has_artificial_preservatives:
            score -= 8

        # Functional Additives
        if has_taurine:
            score += 3
        if has_marine_omega:
            score += 3
        if is_sterilised and has_urinary_support:
            score += 3

        # 3. Macronutrients scoring
        prot = nutri.get('protein', {}).get('value')
        if prot:
            if prot >= 40.0:
                score += 12
            elif prot >= 35.0:
                score += 6
            elif prot < 30.0:
                score -= 15

        fat = nutri.get('fat', {}).get('value')
        if fat:
            if is_kitten:
                if fat >= 18.0:
                    score += 8
                elif fat < 14.0:
                    score -= 10
            elif is_sterilised:
                if 10.0 <= fat <= 14.0:
                    score += 5
                elif fat > 16.0:
                    score -= 6

        carbs = nutri.get('carbs_nfe')
        if carbs is not None:
            if carbs <= 22.0:
                score += 14
            elif carbs <= 32.0:
                score += 5
            elif carbs > 40.0:
                score -= 15

        # 4. Mineral balance
        mg = nutri.get('magnesium', {}).get('value')
        if mg:
            if is_sterilised:
                if mg <= 0.08:
                    score += 6
                elif mg <= 0.10:
                    score += 2
                else:
                    score -= 8
            else:
                if mg <= 0.10:
                    score += 4
                elif mg > 0.12:
                    score -= 5

        ca_p = nutri.get('ca_p_ratio')
        if ca_p:
            if 1.0 <= ca_p <= 1.5:
                score += 5
            elif ca_p > 1.8 or ca_p < 0.9:
                score -= 6

        score = max(10, min(95, score))

        if score >= 80:
            tier = 'Tier S (Ultra-Premium)'
        elif score >= 65:
            tier = 'Tier A (Excelente / Alto Teor Carne)'
        elif score >= 50:
            tier = 'Tier B (Médio-Alto / Boa Relação)'
        elif score >= 35:
            tier = 'Tier C (Básico / Cereais e Subprodutos)'
        else:
            tier = 'Tier D (Evitar / Baixa Qualidade)'

        if pkg and pkg > 0:
            val_ratio = round(score / pkg, 2)
    else:
        tier = 'Não classificado (Dados insuficientes)'

    p['score'] = score
    p['tier'] = tier
    p['is_kitten'] = is_kitten
    p['is_sterilised'] = is_sterilised
    p['is_ranked'] = is_ready
    p['unranked_reasons'] = unranked_reasons
    p['first_ingredient'] = first_ingr
    p['is_grain_free'] = is_grain_free
    p['is_fractionated'] = is_fractionated
    p['has_corn_gluten'] = has_corn_gluten
    p['has_colorants'] = has_colorants
    p['has_taurine'] = has_taurine
    p['has_marine_omega'] = has_marine_omega
    p['value_ratio'] = val_ratio
    p['carb_band'] = cb

    retailer = p.get('retailer', 'Continente')
    p['retailer'] = retailer

    minified = {
        'id': p.get('pid'),
        'n': name,
        'b': brand,
        'p': p.get('price'),
        'pkg': pkg,
        'k': is_kitten,
        'st': is_sterilised,
        't': tier,
        's': score,
        'vr': val_ratio,
        'ir': is_ready,
        'ur': unranked_reasons,
        'gf': is_grain_free,
        'fr': is_fractionated,
        'cg': has_corn_gluten,
        'col': has_colorants,
        'carb': nutri.get('carbs_nfe'),
        'cb': cb,
        'u': p.get('pdp_url'),
        'r': retailer
    }
    return p, minified

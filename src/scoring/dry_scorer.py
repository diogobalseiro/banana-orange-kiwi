import re
from .evidence import normalize_nutrients, validate_composition, check_scoring_readiness, extract_first_ingredient, extract_total_meat_percentage, FieldStatus

def parse_dry_nutrition(nutri_text):
    return normalize_nutrients(nutri_text, category='dry')

def get_dry_carb_band(carbs):
    if carbs is None:
        return 'N/D'
    if carbs <= 15.0:
        return '<=15% (Baixo / Ideal)'
    elif carbs <= 25.0:
        return '15-25% (Moderado)'
    elif carbs <= 35.0:
        return '25-35% (Elevado)'
    else:
        return '>35% (Muito Alto)'

def score_dry_product(p):
    name = p.get('name') or ''
    brand = p.get('brand') or ''
    desc = p.get('description') or ''
    ingr = p.get('ingredients') or ''
    nutri_raw = p.get('nutrition_raw') or ''

    text_to_check = f"{name} {desc} {ingr} {nutri_raw}".lower()
    name_lower = name.lower()

    # Non-food items or supplements mistakenly crawled into food categories
    non_food_markers = ['arranhador', 'tapete para', 'comedouro', 'bebedouro', 'brinquedo', 'suplemento', 'megaderm']
    if any(k in name_lower for k in non_food_markers):
        return None, None

    # Classification check: exclude complementary dry products (snacks, treats)
    is_complementary = False
    if 'alimento complementar' in text_to_check or 'snack' in text_to_check:
        if 'alimento completo' not in text_to_check and '100% completo' not in text_to_check:
            is_complementary = True

    if is_complementary or p.get('classification') in ['Complementar', 'complementary']:
        return None, None

    # Target demographics
    is_kitten = any(k in f"{name_lower} {desc.lower()}" for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote', 'crescimento'])
    is_sterilised = any(s in f"{name_lower} {desc.lower()}" for s in ['esterilizado', 'esterilizada', 'esterilizados', 'esterilizadas', 'sterilised', 'sterilized', 'neutered', 'castrado', 'castrada', 'castrados'])

    # 1. Composition Validation
    comp_eval = validate_composition(ingr)
    has_valid_composition = (comp_eval['status'] == FieldStatus.VALID)

    first_ingr = None
    first_is_fresh_animal = False
    first_is_dehydrated_animal = False
    first_is_vague_animal = False
    first_is_plant = False
    meat_pct = None
    is_grain_free = None
    has_grains = False
    has_cheap_grains = None
    has_quality_grains = None
    has_corn_gluten = None
    has_colorants = None
    has_sugar = None
    has_artificial_preservatives = None
    is_fractionated = None

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
            fresh_terms = ['fresco', 'fresca', 'desossado', 'desossada', 'frescos', 'frescas', 'cru', 'crua', 'crus', 'cruas']
            plant_terms = [
                'milho', 'trigo', 'cereais', 'arroz', 'ervilha', 'batata', 'farinha de trigo', 'farinha de milho',
                'glúten', 'proteína vegetal', 'cevada', 'aveia', 'polpa de beterraba', 'soja', 'tapioca', 'lentilhas',
                'grão-de-bico', 'alfafa'
            ]

            if any(f in first_lower for f in fresh_terms) and any(a in first_lower for a in animal_terms):
                first_is_fresh_animal = True
            elif any(d in first_lower for d in ['desidratad', 'farinha de', 'proteína de aves', 'proteína de frango', 'proteína de salmão', 'proteína desidratada', 'proteínas desidratadas']) and any(a in first_lower for a in animal_terms):
                first_is_dehydrated_animal = True
            elif ('carne e subprodutos' in first_lower or 'carnes e subprodutos' in first_lower):
                first_is_vague_animal = True
            elif any(a in first_lower for a in animal_terms) and not any(p in first_lower for p in ['proteína de ervilha', 'proteína de batata', 'amido']):
                first_is_dehydrated_animal = True
            elif any(p in first_lower for p in plant_terms):
                first_is_plant = True

        # Total animal / meat percentage match
        meat_pct = extract_total_meat_percentage(ingr_clean_text)

        # Grains & Starches - Factual composition is strictly authoritative
        grain_terms = ['trigo', 'milho', 'arroz', 'aveia', 'cevada', 'centeio', 'cereais', 'glúten', 'espelta', 'sorgo']
        has_grains = any(g in ingr_lower for g in grain_terms)
        is_grain_free = not has_grains

        has_cheap_grains = any(cg in ingr_lower for cg in ['trigo', 'milho', 'farinha de trigo', 'farinha de milho', 'cevada cervejeira', 'glúten de milho', 'glúten de trigo'])
        has_quality_grains = any(qg in ingr_lower for qg in ['aveia', 'cevada integral', 'arroz integral', 'centeio'])
        has_corn_gluten = any(cg in ingr_lower for cg in ['glúten de milho', 'gluten de milho', 'proteína de milho', 'proteina de milho', 'glúten'])
        if has_corn_gluten and any(neg in ingr_lower for neg in ['sem glúten', 'sem gluten', 'isento de glúten', 'isento de gluten', 'zero glúten', 'gluten free']):
            has_corn_gluten = False

        has_colorants = any(c in ingr_lower for c in ['corantes', 'corante', 'óxido de ferro', 'oxido de ferro', 'tartrazina', 'dióxido de titânio'])
        if has_colorants and any(neg in ingr_lower for neg in ['sem corante', 'sem corantes', 'não contém corante', 'nao contem corante', 'isento de corante', 'isento de corantes']):
            has_colorants = False

        has_sugar = any(s in ingr_lower for s in ['açúcar', 'açucares', 'açúcares', 'açucar', 'sacarose', 'xarope', 'caramelo'])
        if has_sugar and any(neg in ingr_lower for neg in ['sem açúcar', 'sem açucares', 'sem açúcares', 'sem acucar', 'não contém açúcar', 'nao contem acucar']):
            has_sugar = False

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
    has_marine_omega = bool(re.search(r'\b(?:epa|dha)\b', text_to_check, re.I)) or any(o in text_to_check for o in ['óleo de salmão', 'oleo de salmao', 'óleo de peixe', 'oleo de peixe', 'ómega-3', 'omega-3', 'salmon oil', 'fish oil', 'óleo de escamudo'])
    has_organs = any(o in ingr_lower for o in ['coração', 'corações', 'fígado', 'figado', 'moela', 'moelas', 'rins', 'miudezas']) if has_valid_composition else False

    # 2. Parse analytical components using Evidence Contract
    nutri = normalize_nutrients(nutri_raw, category='dry')
    p['nutrition_parsed'] = nutri

    # 3. Check Scoring Readiness Gate
    temp_p = dict(p)
    temp_p['classification'] = 'complete'
    temp_p['nutrition_normalized'] = nutri
    is_ready, unranked_reasons = check_scoring_readiness(temp_p, category='dry')

    score = None
    tier = 'Não classificado (Dados insuficientes)'
    val_ratio = None
    pkg = p.get('unit_price_kg')
    try:
        pkg = float(pkg) if pkg is not None else None
    except (ValueError, TypeError):
        pkg = None

    # Carbohydrate calculation (declared or estimated under EU 767/2009 reference moisture)
    carbs = nutri.get('carbs_nfe')
    carbs_is_estimated = False
    if carbs is None:
        prot_v = nutri.get('protein', {}).get('value')
        fat_v = nutri.get('fat', {}).get('value')
        ash_v = nutri.get('ash', {}).get('value')
        fib_v = nutri.get('fiber', {}).get('value')
        if all(v is not None for v in [prot_v, fat_v, ash_v, fib_v]):
            carbs = round(max(0.0, 100.0 - (prot_v + fat_v + ash_v + fib_v + 8.0)), 1)
            carbs_is_estimated = True

    if carbs is not None:
        cb_label = get_dry_carb_band(carbs)
        cb = f"{cb_label} (Est.)" if carbs_is_estimated else cb_label
    else:
        cb = 'N/D'

    if is_ready:
        score = 50

        # 1. First ingredient scoring
        if first_is_fresh_animal:
            score += 18
        elif first_is_dehydrated_animal:
            score += 14
        elif first_is_vague_animal:
            score -= 5
        elif first_is_plant:
            score -= 20
        else:
            score -= 8

        # Total meat percentage
        if meat_pct and meat_pct >= 65:
            score += 12
        elif meat_pct and meat_pct >= 40:
            score += 6

        # Organ meats bonus
        if has_organs:
            score += 4

        # 2. Grain, Starch & Fractionation scoring
        if is_grain_free:
            score += 10
            if is_fractionated:
                score -= 8
            elif fractionation_count == 1:
                score -= 2
        else:
            if has_cheap_grains:
                score -= 16
            elif has_quality_grains and not has_cheap_grains:
                score -= 5
            else:
                score -= 10
            if is_fractionated:
                score -= 8

        # Detrimental additives
        if has_corn_gluten:
            score -= 12
        if has_colorants:
            score -= 15
        if has_sugar:
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
        if prot is not None:
            if prot >= 40.0:
                score += 10
            elif prot >= 35.0:
                score += 5
            elif prot < 30.0:
                score -= 15

        fat = nutri.get('fat', {}).get('value')
        if fat is not None:
            if is_kitten:
                if fat >= 18.0:
                    score += 6
                elif fat < 14.0:
                    score -= 10
            elif is_sterilised:
                if 10.0 <= fat <= 14.0:
                    score += 4
                elif fat > 16.0:
                    score -= 6
            else:
                if 14.0 <= fat <= 20.0:
                    score += 4

        if carbs is not None:
            if carbs <= 15.0:
                score += 12
            elif carbs <= 25.0:
                score += 4
            elif carbs <= 35.0:
                score -= 5
            else:
                score -= 15

        # 4. Mineral balance
        mg = nutri.get('magnesium', {}).get('value')
        if mg is not None:
            if is_sterilised:
                if mg <= 0.08:
                    score += 5
                elif mg <= 0.10:
                    score += 2
                else:
                    score -= 8
            else:
                if mg <= 0.10:
                    score += 3
                elif mg > 0.12:
                    score -= 5

        ca_p = nutri.get('ca_p_ratio')
        if ca_p is not None:
            if 1.0 <= ca_p <= 1.5:
                score += 4
            elif ca_p > 1.8 or ca_p < 0.9:
                score -= 6

        phos = nutri.get('phosphorus', {}).get('value')
        if phos is not None and phos > 1.3:
            score -= 8

        score = max(10, min(95, score))

        # Grain-inclusive dry kibble cannot exceed Tier A (ceiling of 79)
        # Feline obligate carnivore biology reserves Tier S (80+) strictly for grain-free formulas
        if not is_grain_free and score >= 80:
            score = 79

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
    p['meat_pct'] = meat_pct
    p['is_grain_free'] = is_grain_free
    p['has_grains'] = has_grains
    p['is_fractionated'] = is_fractionated
    p['has_corn_gluten'] = has_corn_gluten
    p['has_colorants'] = has_colorants
    p['has_sugar'] = has_sugar
    p['has_taurine'] = has_taurine
    p['has_marine_omega'] = has_marine_omega
    p['has_organs'] = has_organs
    p['value_ratio'] = val_ratio
    p['carb_band'] = cb
    p['protein'] = nutri.get('protein', {}).get('value')
    p['fat'] = nutri.get('fat', {}).get('value')
    p['carbs'] = carbs

    retailer = p.get('retailer', 'Continente')
    p['retailer'] = retailer

    minified = {
        'id': p.get('pid'),
        'n': name,
        'b': brand,
        'p': p.get('price'),
        'pkg': pkg,
        'fi': first_ingr,
        'fresh': first_is_fresh_animal,
        'meat_pct': meat_pct,
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
        'tau': has_taurine,
        'omg': has_marine_omega,
        'org': has_organs,
        'prot': nutri.get('protein', {}).get('value'),
        'fat': nutri.get('fat', {}).get('value'),
        'carb': carbs,
        'cb': cb,
        'u': p.get('pdp_url'),
        'r': retailer,
        'fid': p.get('formulation_id'),
        'rec': p.get('is_reconciled', False),
        'conf': p.get('has_material_conflict', False)
    }
    return p, minified

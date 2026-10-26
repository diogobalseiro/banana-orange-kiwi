import re

def parse_dry_nutrition(nutri_text):
    data = {}
    if not nutri_text:
        return data

    clean = nutri_text.replace('\xa0', ' ').replace(',', '.')
    
    # Protein
    m = re.search(r'[Pp]rote[íi]na\s*(?:bruta)?[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m:
        data['protein'] = float(m.group(1))

    # Fat
    m = re.search(r'(?:[Gg]ordura\s*bruta|[Mm]at[ée]ria\s*gorda(?:[,\s]*bruta)?)[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m:
        data['fat'] = float(m.group(1))

    # Moisture
    m = re.search(r'[Hh]umidade[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m:
        data['moisture'] = float(m.group(1))

    # Ash
    m = re.search(r'[Cc]inza(?:s)?\s*bruta(?:s)?[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m:
        data['ash'] = float(m.group(1))

    # Fiber
    m = re.search(r'[Ff]ibra\s*bruta[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m:
        data['fiber'] = float(m.group(1))

    # Minerals: Calcium, Phosphorus, Magnesium
    m_ca = re.search(r'[Cc][áa]lcio[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m_ca:
        data['calcium'] = float(m_ca.group(1))

    m_p = re.search(r'[Ff][óo]sforo[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m_p:
        data['phosphorus'] = float(m_p.group(1))

    m_mg = re.search(r'[Mm]agn[ée]sio[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m_mg:
        data['magnesium'] = float(m_mg.group(1))

    # Ca:P ratio
    if 'calcium' in data and 'phosphorus' in data and data['phosphorus'] > 0:
        data['ca_p_ratio'] = round(data['calcium'] / data['phosphorus'], 2)

    # Taurine
    m_tau = re.search(r'[Tt]aurina[:\s]+(\d+(?:\.\d+)?)\s*(?:mg/kg|%)?', clean)
    if m_tau:
        data['taurine'] = float(m_tau.group(1))

    # Carbohydrates estimate (NFE)
    moist = data.get('moisture', 8.0) # Typical dry food moisture
    prot = data.get('protein', 30.0)
    fat = data.get('fat', 14.0)
    ash = data.get('ash', 7.0)
    fib = data.get('fiber', 2.5)

    carbs = max(0.0, 100.0 - (prot + fat + moist + ash + fib))
    data['carbs_nfe'] = round(carbs, 1)

    return data

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
    ingr_lower = ingr.lower()
    brand_lower = brand.lower()
    name_lower = name.lower()

    # Target demographics
    is_kitten = any(k in f"{name_lower} {desc.lower()}" for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote', 'crescimento'])
    is_sterilised = any(s in f"{name_lower} {desc.lower()}" for s in ['esterilizado', 'esterilizados', 'sterilised', 'sterilized'])

    # 1. First ingredient check & biological source
    first_ingr = ""
    first_is_fresh_animal = False
    first_is_dehydrated_animal = False
    first_is_plant = False

    clean_ingr = re.sub(r'^(?:ingredientes|composição|composição:)\s*[:\-]?\s*', '', ingr, flags=re.I).strip()
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

    # 2. Total animal / meat percentage match
    meat_pct_match = re.search(r'(\d+)\s*%\s*(?:de\s*)?(?:carne|frango|peru|salmão|peixe|vaca|borrego|pato|aves|proteína|ingredientes\s+animais)', ingr_lower)
    meat_pct = int(meat_pct_match.group(1)) if meat_pct_match else None

    # 3. Grains, Starches & Legume Fractionation Detection
    is_grain_free = any(gf in text_to_check for gf in ['sem cereais', 'grain free', 'grain-free', 'no grain'])
    has_cheap_grains = any(cg in ingr_lower for cg in ['trigo', 'milho', 'farinha de trigo', 'farinha de milho', 'cevada cervejeira'])
    has_quality_grains = any(qg in ingr_lower for qg in ['aveia', 'cevada integral', 'arroz integral', 'centeio'])
    has_corn_gluten = any(cg in ingr_lower for cg in ['glúten de milho', 'gluten de milho', 'proteína de milho', 'proteina de milho', 'glúten'])
    has_colorants = any(c in ingr_lower for c in ['corantes', 'corante', 'óxido de ferro', 'oxido de ferro', 'tartrazina', 'dióxido de titânio'])
    has_artificial_preservatives = any(p in text_to_check for p in ['bha', 'bht', 'galato de propilo', 'butil-hidroxianisol', 'butil-hidroxitolueno', 'etoxiquina', 'ethoxyquin', 'e320', 'e321', 'e310'])

    # Starch/Legume Fractionation (Ingredient Splitting) Scanner
    legume_starch_markers = [
        'proteína de ervilha', 'proteina de ervilha', 'amido de ervilha', 'farinha de ervilha', 'fibra de ervilha',
        'proteína de batata', 'proteina de batata', 'amido de batata', 'flocos de batata', 'batata desidratada', 'farinha de batata',
        'tapioca', 'amido de mandioca', 'grão-de-bico', 'grao-de-bico', 'lentilhas', 'farinha de favas'
    ]
    split_matches = [m for m in legume_starch_markers if m in ingr_lower]
    fractionation_count = len(split_matches)
    has_pea_protein_early = any(p in ingr_lower[:140] for p in ['proteína de ervilha', 'proteina de ervilha', 'proteína de batata', 'proteina de batata', 'amido de ervilha', 'amido de batata'])
    is_fractionated = fractionation_count >= 2 or has_pea_protein_early

    # 4. Functional additives & Life stage support
    has_urinary_support = any(u in text_to_check for u in ['arando', 'mirtilo', 'cranberry', 'dl-metionina', 'metionina', 'saúde urinária', 'trato urinário', 'controlo de ph'])
    has_taurine = any(t in text_to_check for t in ['taurina', 'taurine'])
    has_marine_omega = any(o in text_to_check for o in ['óleo de salmão', 'oleo de salmao', 'óleo de peixe', 'oleo de peixe', 'salmon oil', 'fish oil', 'dha', 'epa'])

    # Parse analytical components
    nutri = parse_dry_nutrition(nutri_raw)
    p['nutrition_parsed'] = nutri

    # Biological Scoring Algorithm (0-100 base) - 100% objective, NO brand priors!
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
            score -= 8  # Fractionation penalty
        elif fractionation_count == 1:
            score += 6  # Moderate single starch source
        else:
            score += 12 # Clean grain-free
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
    prot = nutri.get('protein')
    if prot:
        if prot >= 40.0:
            score += 12
        elif prot >= 35.0:
            score += 6
        elif prot < 30.0:
            score -= 15

    fat = nutri.get('fat')
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

    # 4. Mineral balance (when present from Zooplus/ZU)
    mg = nutri.get('magnesium')
    if mg:
        if mg <= 0.09:
            score += 3
        elif mg > 0.12:
            score -= 8 # Elevated risk of struvite crystals

    p_val = nutri.get('phosphorus')
    if p_val and p_val > 1.2:
        score -= 5 # High phosphorus kidney strain

    ca_p = nutri.get('ca_p_ratio')
    if ca_p:
        if 1.1 <= ca_p <= 1.4:
            score += 3
        elif ca_p < 0.9 or ca_p > 1.8:
            score -= 5

    score = max(10, min(95, score))

    if score >= 85:
        tier = 'Tier S (Ultra-Premium)'
    elif score >= 70:
        tier = 'Tier A (Excelente / Alto Teor Carne)'
    elif score >= 55:
        tier = 'Tier B (Médio-Alto / Boa Relação)'
    elif score >= 40:
        tier = 'Tier C (Básico / Ingredientes Genéricos)'
    else:
        tier = 'Tier D (Evitar / Cereais e Glúten)'

    pkg = p.get('unit_price_kg')
    val_ratio = round(score / pkg, 2) if pkg and pkg > 0 else 0.0

    p['score'] = score
    p['tier'] = tier
    p['is_kitten'] = is_kitten
    p['is_sterilised'] = is_sterilised
    p['is_grain_free'] = is_grain_free
    p['is_fractionated'] = is_fractionated
    p['has_corn_gluten'] = has_corn_gluten
    p['has_colorants'] = has_colorants
    p['has_artificial_preservatives'] = has_artificial_preservatives
    p['has_urinary_support'] = has_urinary_support
    p['has_taurine'] = has_taurine
    p['has_marine_omega'] = has_marine_omega
    p['value_ratio'] = val_ratio

    retailer = p.get('retailer', 'Continente')
    p['retailer'] = retailer

    cb = get_dry_carb_band(carbs)
    p['carb_band'] = cb

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
        'gf': is_grain_free,
        'frac': is_fractionated,
        'cg': has_corn_gluten,
        'col': has_colorants,
        'prot': prot,
        'fat': fat,
        'carb': carbs,
        'cb': cb,
        'fi': first_ingr[:45] if first_ingr else '',
        'u': p.get('pdp_url'),
        'r': retailer
    }
    return p, minified

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

    # Ingredient analysis: grains vs starches
    is_grain_free = any(gf in text_to_check for gf in ['sem cereais', 'grain free', 'grain-free', 'no grain'])
    has_cheap_grains = any(cg in ingr_lower for cg in ['trigo', 'milho', 'farinha de trigo', 'farinha de milho'])
    has_corn_gluten = any(cg in ingr_lower for cg in ['glúten de milho', 'proteína de milho', 'glúten'])
    has_colorants = any(c in ingr_lower for c in ['corantes', 'corante', 'óxido de ferro', 'tartrazina'])
    has_starch_padding = any(s in ingr_lower for s in ['amido de batata', 'amido de ervilha', 'amido de mandioca', 'tapioca', 'proteína de ervilha', 'proteína de batata'])
    has_quality_grains = any(qg in ingr_lower for qg in ['aveia', 'cevada', 'arroz integral', 'centeio'])

    # Named meat percentage match
    meat_pct_match = re.search(r'(\d+)%\s*(?:de\s*)?(?:carne|frango|peru|salmão|peixe|vaca|borrego|pato|aves|proteína|ingredientes\s+animais)', ingr_lower)
    meat_pct = int(meat_pct_match.group(1)) if meat_pct_match else None

    # First ingredient check
    first_ingr = ""
    first_is_animal = False
    if ingr:
        parts = re.split(r'[,;]\s*', ingr)
        if parts:
            first_ingr = parts[0].strip()
            first_lower = first_ingr.lower()
            if any(a in first_lower for a in ['frango', 'salmão', 'peru', 'vaca', 'carne', 'peixe', 'atum', 'borrego', 'aves', 'pato', 'coelho']):
                first_is_animal = True

    nutri = parse_dry_nutrition(nutri_raw)
    p['nutrition_parsed'] = nutri

    score = 50

    # Brand baseline quality prior
    if any(b in brand_lower for b in ["acana", "orijen", "uppy nutri", "lily's kitchen", "purizon", "carnilove", "farmina", "n&d", "taste of the wild", "canagan"]):
        score += 25
    elif any(b in brand_lower for b in ["natural greatness", "harper & bone", "ownat", "concept for life", "weego", "purenatural", "gosbi", "bravery"]):
        score += 20
    elif "smaak" in brand_lower:
        score += 15
    elif "purina one" in brand_lower or "advance" in brand_lower:
        score += 5
    elif "continente pet basic" in brand_lower:
        score -= 20
    elif "brekkies" in brand_lower or "friskies" in brand_lower or "whiskas" in brand_lower:
        score -= 15

    # Ingredient criteria
    if first_is_animal:
        score += 15
    else:
        score -= 20

    if meat_pct and meat_pct >= 60:
        score += 15
    elif meat_pct and meat_pct >= 40:
        score += 10

    # Grain vs Starch refinement
    if is_grain_free:
        if not has_starch_padding:
            score += 15
        else:
            score += 5  # Grain-free, but padded with legume/tuber starches
    elif has_quality_grains and first_is_animal and not has_cheap_grains:
        score += 5   # Quality whole grains (oats/barley) in a meat-first formula
    elif has_cheap_grains:
        score -= 15
    elif not is_grain_free:
        score -= 5

    if has_corn_gluten:
        score -= 10
    if has_colorants:
        score -= 15

    # Nutritional macronutrients
    prot = nutri.get('protein')
    if prot:
        if prot >= 40.0:
            score += 15
        elif prot >= 35.0:
            score += 10
        elif prot < 30.0:
            score -= 15

    fat = nutri.get('fat')
    if fat:
        if is_kitten:
            if fat >= 18.0:
                score += 10
            elif fat < 14.0:
                score -= 10
        elif is_sterilised:
            if 10.0 <= fat <= 14.0:
                score += 5
            elif fat > 16.0:
                score -= 5

    carbs = nutri.get('carbs_nfe')
    if carbs is not None:
        if carbs <= 25.0:
            score += 15
        elif carbs <= 35.0:
            score += 5
        elif carbs > 42.0:
            score -= 15

    # Uppy Nutri Junior & Acana First Feast check
    if 'uppy nutri' in brand_lower and is_kitten:
        score = max(score, 95)
    if 'acana' in brand_lower and is_kitten:
        score = max(score, 95)
    if 'smaak' in brand_lower:
        score = max(score, 70)

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
    p['has_corn_gluten'] = has_corn_gluten
    p['has_colorants'] = has_colorants
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

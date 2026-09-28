import re

def parse_wet_nutrition(nutri_text):
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

    # Crude Ash
    m = re.search(r'[Cc]inza(?:s)?\s*bruta(?:s)?[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m:
        data['ash'] = float(m.group(1))

    # Crude Fiber
    m = re.search(r'[Ff]ibra\s*bruta[:\s]+(\d+(?:\.\d+)?)\s*%', clean)
    if m:
        data['fiber'] = float(m.group(1))

    moisture = data.get('moisture', 80.0)
    dm = max(1.0, 100.0 - moisture)
    data['dm_pct'] = round(dm, 1)

    if 'protein' in data:
        data['protein_dmb'] = round((data['protein'] / dm) * 100.0, 1)
    if 'fat' in data:
        data['fat_dmb'] = round((data['fat'] / dm) * 100.0, 1)

    if all(k in data for k in ['protein', 'fat', 'moisture', 'ash', 'fiber']):
        carbs_nfe = max(0.0, 100.0 - (data['protein'] + data['fat'] + data['moisture'] + data['ash'] + data['fiber']))
        data['carbs_nfe'] = round(carbs_nfe, 1)
        data['carbs_dmb'] = round((carbs_nfe / dm) * 100.0, 1)

    return data

def score_wet_product(p):
    name = p.get('name', '')
    brand = p.get('brand', '')
    desc = p.get('description', '')
    ingr = p.get('ingredients', '')
    nutri_raw = p.get('nutrition_raw', '')

    text_to_check = f"{name} {desc} {ingr} {nutri_raw}".lower()
    ingr_lower = ingr.lower()
    brand_lower = brand.lower()
    name_lower = name.lower()

    # Is Kitten / Junior
    is_kitten = any(k in f"{name_lower} {desc.lower()}" for k in ['júnior', 'junior', 'kitten', 'gatinho'])

    # 1. Complete vs Complementary check
    is_complementary = False
    if 'complementar' in text_to_check or 'alimento complementar' in text_to_check:
        is_complementary = True
    elif any(b in brand_lower for b in ['schesir', 'ciao', 'churu', 'applaws', 'fish4cats']):
        if 'alimento completo' not in text_to_check and '100% completa' not in text_to_check:
            is_complementary = True

    # 2. Ingredient flags
    has_sugar = any(s in ingr_lower for s in ['açúcar', 'açúcares', 'açucar', 'açucares', 'caramelo'])
    has_grains = any(g in ingr_lower for g in ['cereais', 'trigo', 'milho', 'arroz', 'farinha'])
    has_veg_protein = any(v in ingr_lower for v in [
        'subprodutos de origem vegetal', 
        'extractos de proteínas vegetais', 
        'extractos de proteína vegetal',
        'extratos de proteína vegetal', 
        'extratos de proteínas vegetais',
        'concentrado de proteína vegetal'
    ])
    has_vague_byproducts = 'carnes e subprodutos animais' in ingr_lower and not any(pct in ingr_lower for pct in ['50%', '60%', '65%', '70%', '75%', '80%'])

    # 3. High named meat detection
    named_meat_match = re.search(r'(\d+)%\s*(?:de\s*)?(?:frango|atum|salmão|carne|peru|vaca|peixe|pato|borrego)', ingr_lower)
    high_meat_pct = int(named_meat_match.group(1)) if named_meat_match else None

    # Parse analytical components
    nutri = parse_wet_nutrition(nutri_raw)
    p['nutrition_parsed'] = nutri

    # Scoring Algorithm (0-100 base)
    score = 50

    if any(b in brand_lower for b in ["lily's kitchen", "natural greatness", "harper & bone"]):
        score += 25
    elif "gourmet nature" in name_lower or "gourmet nature" in brand_lower:
        score += 15
    elif "smaak" in brand_lower:
        score += 15
    elif "continente pet premium" in brand_lower or "continente pet premium" in name_lower:
        score += 5
    elif "purina one" in brand_lower:
        score += 5
    elif "continente pet basic" in brand_lower:
        score -= 15
    elif "brekkies" in brand_lower:
        score -= 15

    # Ingredient scoring
    if high_meat_pct and high_meat_pct >= 50:
        score += 25
    elif high_meat_pct and high_meat_pct >= 30:
        score += 15
    elif 'smaak' in brand_lower and not has_grains:
        score += 15

    if has_sugar:
        score -= 25
    if has_grains:
        score -= 15
    if has_veg_protein:
        score -= 15
    if has_vague_byproducts:
        score -= 15

    # Nutrition scoring
    prot_dmb = nutri.get('protein_dmb')
    if prot_dmb:
        if prot_dmb >= 55.0:
            score += 15
        elif prot_dmb >= 45.0:
            score += 5
        elif prot_dmb < 35.0:
            score -= 15

    carbs_dmb = nutri.get('carbs_dmb')
    if carbs_dmb is not None:
        if carbs_dmb <= 10.0:
            score += 10
        elif carbs_dmb > 25.0:
            score -= 15

    # Smaak Junior fix
    if 'smaak' in brand_lower and is_kitten:
        score = max(score, 75)

    score = max(10, min(95, score))

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

    pkg = p.get('unit_price_kg')
    val_ratio = round(score / pkg, 2) if pkg and pkg > 0 else 0.0

    p['score'] = score
    p['tier'] = tier
    p['classification'] = 'Complementar' if is_complementary else 'Completo'
    p['is_kitten'] = is_kitten
    p['has_sugar'] = has_sugar
    p['has_grains'] = has_grains
    p['has_veg_protein'] = has_veg_protein
    p['value_ratio'] = val_ratio

    minified = {
        'id': p.get('pid'),
        'n': name,
        'b': brand,
        'p': p.get('price'),
        'pkg': pkg,
        'c': p['classification'],
        'k': is_kitten,
        't': tier,
        's': score,
        'vr': val_ratio,
        'sug': has_sugar,
        'grn': has_grains,
        'veg': has_veg_protein,
        'u': p.get('pdp_url')
    }
    return p, minified

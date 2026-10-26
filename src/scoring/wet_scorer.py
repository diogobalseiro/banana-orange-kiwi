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

    # Taurine
    m_tau = re.search(r'[Tt]aurina[:\s]+(\d+(?:\.\d+)?)\s*(?:mg/kg|%)?', clean)
    if m_tau:
        data['taurine'] = float(m_tau.group(1))

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

def get_wet_carb_band(carbs_dmb):
    if carbs_dmb is None:
        return 'N/D'
    if carbs_dmb <= 10.0:
        return '<10% DMB (Ideal)'
    elif carbs_dmb <= 20.0:
        return '10-20% DMB (Moderado)'
    else:
        return '>20% DMB (Elevado)'

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

    # 1. Complete vs Complementary check (Exclude complementary entirely)
    is_complementary = False
    if any(k in text_to_check for k in ['complementar', 'alimento complementar', 'snack', 'petisco', 'treat', 'sopa para gato']):
        is_complementary = True
    elif any(b in brand_lower for b in ['schesir', 'ciao', 'churu', 'applaws', 'fish4cats', 'inaba', 'thrive']):
        if 'alimento completo' not in text_to_check and '100% completa' not in text_to_check:
            is_complementary = True

    # If complementary, exclude from ranking entirely
    if is_complementary:
        return None, None

    # Target: Kitten / Junior
    is_kitten = any(k in f"{name_lower} {desc.lower()}" for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote', 'crescimento'])

    # 2. Ingredient Quality & Transparency
    # Check "4% EU token trick"
    is_token_4pct = bool(
        re.search(r'(?:dos quais|mín(?:imo)?\.?)\s*4\s*%', ingr_lower) or
        re.search(r'carnes e subprodutos animais\s*\([^)]*4\s*%', ingr_lower)
    )

    # Genuine named meat percentage match
    high_meat_pct = None
    if not is_token_4pct:
        meat_matches = re.findall(
            r'(?:(\d+)\s*%\s*(?:de\s*)?(?:carne|frango|peru|salmão|atum|vaca|peixe|pato|borrego|javali|coelho|aves)|(?:frango|atum|salmão|carne|peru|vaca|peixe|pato|borrego|javali|coelho|aves)\s*(?:\([^)]*?\))?\s*[:\-]?\s*(\d+)\s*%)',
            ingr_lower
        )
        if meat_matches:
            pcts = []
            for g1, g2 in meat_matches:
                v = g1 or g2
                if v and int(v) > 4:
                    pcts.append(int(v))
            if pcts:
                high_meat_pct = max(pcts)

        # Fallback check for "85% de carne e derivados" / "70% carne"
        if not high_meat_pct:
            m_total = re.search(r'(\d+)\s*%\s*(?:de\s*)?(?:carne|miudezas|ingredientes de origem animal)', ingr_lower)
            if m_total and int(m_total.group(1)) > 20:
                high_meat_pct = int(m_total.group(1))

    # Organ meats (feline superfoods: liver, heart, gizzard, lung, kidneys)
    has_organs = any(o in ingr_lower for o in [
        'coração', 'corações', 'fígado', 'figado', 'moela', 'moelas', 'pulmão', 'pulmões', 'estômago', 'estômagos', 'rins', 'rim'
    ])

    # Monoproteic
    is_monoproteic = any(m in text_to_check for m in ['monoproteico', 'mono-proteico', 'monoproteica', 'single protein', 'uma única fonte de proteína'])

    # Detrimental additives
    has_sugar = any(s in ingr_lower for s in ['açúcar', 'açúcares', 'açucar', 'açucares', 'caramelo', 'xarope', 'dextrose', 'melaço'])
    has_grains = any(g in ingr_lower for g in ['cereais', 'trigo', 'milho', 'arroz', 'farinha de trigo', 'farinha de milho'])
    has_veg_protein = any(v in ingr_lower for v in [
        'subprodutos de origem vegetal',
        'subprodutos vegetais',
        'extractos de proteínas vegetais',
        'extractos de proteína vegetal',
        'extratos de proteína vegetal',
        'extratos de proteínas vegetais',
        'concentrado de proteína vegetal'
    ])
    has_vague_byproducts = 'carnes e subprodutos animais' in ingr_lower and not high_meat_pct and not is_token_4pct

    # Thickeners & Gelling agents
    has_carrageenan = any(c in ingr_lower for c in ['carragenina', 'carragenano', 'carrageenan', 'e407'])
    has_gums = any(g in ingr_lower for g in ['goma cássia', 'goma cassia', 'cassia gum', 'e499'])

    # Beneficial micronutrients
    has_taurine = any(t in text_to_check for t in ['taurina', 'taurine'])
    has_marine_omega = any(o in text_to_check for o in ['óleo de salmão', 'oleo de salmao', 'óleo de peixe', 'oleo de peixe', 'salmon oil', 'fish oil', 'dha', 'epa'])

    # Parse analytical components
    nutri = parse_wet_nutrition(nutri_raw)
    p['nutrition_parsed'] = nutri

    # Biological Scoring Algorithm (0-100 base) - 100% objective, NO brand priors!
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

    # Penalties for low-grade slaughter derivatives
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

    # 4. Analytical Macronutrients (when present)
    prot_dmb = nutri.get('protein_dmb')
    if prot_dmb:
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
        elif carbs_dmb > 22.0:
            score -= 12

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
    p['classification'] = 'Completo'
    p['is_kitten'] = is_kitten
    p['has_sugar'] = has_sugar
    p['has_grains'] = has_grains
    p['has_veg_protein'] = has_veg_protein
    p['has_organs'] = has_organs
    p['has_carrageenan'] = has_carrageenan
    p['has_taurine'] = has_taurine
    p['has_marine_omega'] = has_marine_omega
    p['high_meat_pct'] = high_meat_pct
    p['value_ratio'] = val_ratio

    retailer = p.get('retailer', 'Continente')
    p['retailer'] = retailer

    cb = get_wet_carb_band(carbs_dmb)
    p['carb_band'] = cb

    minified = {
        'id': p.get('pid'),
        'n': name,
        'b': brand,
        'p': p.get('price'),
        'pkg': pkg,
        'c': 'Completo',
        'k': is_kitten,
        't': tier,
        's': score,
        'vr': val_ratio,
        'sug': has_sugar,
        'grn': has_grains,
        'veg': has_veg_protein,
        'org': has_organs,
        'carr': has_carrageenan,
        'tau': has_taurine,
        'carb': carbs_dmb,
        'cb': cb,
        'u': p.get('pdp_url'),
        'r': retailer
    }
    return p, minified

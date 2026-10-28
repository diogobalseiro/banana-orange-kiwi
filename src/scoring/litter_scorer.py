import re
import math
from .litter_evidence import evaluate_litter_evidence, LitterMaterial, _sanitize_numeric

def score_litter_product(p):
    """
    Scores cat litter products based on feline respiratory health, clumping hygiene,
    ingestion safety, dust control, and natural odor neutralization.
    Returns (full_product_dict, minified_product_dict).
    """
    if not p or not isinstance(p, dict):
        return None, None

    name = p.get('name', '')
    desc = p.get('description', '')
    brand = p.get('brand') or 'Desconhecida'
    raw_price = p.get('price')
    price = _sanitize_numeric(raw_price)

    # Non-litter filter: litter boxes, scoops, deodorant sprays, wc filters, bins mistakenly categorized
    name_lower = name.lower()
    desc_lower = (desc or '').lower()
    non_litter_markers = [
        'pá para', 'pa para', 'pá de areia', 'pa de areia', 'pá limpa', 'colher para areia',
        'caixa de areia', 'caixa areia', 'casa de banho', 'tabuleiro de areia', 'wc para gato',
        'areão para aquário', 'areao aquario', 'desodorizante para', 'desodorizante de areia',
        'tapete para', 'tapete pvc', 'resguardo', 'sanitário fechado',
        'filtro de carvão', 'filtro para wc', 'filtro wc', 'litter locker', 'litterlocker',
        'recarga litter', 'balde litter', 'sacos higiénicos', 'sacos higienicos',
        'sacos para caixa', 'sacos plástico', 'spray removedor', 'spray tira', 'absorvedor de odores'
    ]
    if any(k in name_lower for k in non_litter_markers):
        return None, None

    # Evaluate physical and material evidence
    ev = evaluate_litter_evidence(p)
    
    # Store parsed measurements
    p['price'] = price
    p['volume_l'] = ev['volume_l']
    p['weight_kg'] = ev['weight_kg']
    p['unit_price_l'] = ev['unit_price_l']
    p['unit_price_kg'] = ev['unit_price_kg']
    p['material'] = ev['material']
    p['is_clumping'] = ev['is_clumping']
    p['has_perfume'] = ev['has_perfume']
    p['is_unscented'] = ev['is_unscented']
    p['scent_name'] = ev['scent_name']
    p['is_low_dust'] = ev['is_low_dust']
    p['has_active_carbon'] = ev['has_active_carbon']
    p['has_baking_soda'] = ev['has_baking_soda']
    p['is_biodegradable'] = ev['is_biodegradable']
    p['is_flushable'] = ev['is_flushable']
    p['is_kitten_targeted'] = ev['is_kitten_targeted']

    unranked_reasons = []
    
    # Check minimum score readiness: must have price and either volume or weight
    if raw_price is not None:
        try:
            raw_f = float(str(raw_price).replace(',', '.').strip())
            if raw_f < 0:
                unranked_reasons.append('negative_value')
        except (ValueError, TypeError):
            pass

    if price is None or price <= 0:
        if 'negative_value' not in unranked_reasons:
            unranked_reasons.append('missing_price')

    has_valid_vol = (ev['volume_l'] is not None and isinstance(ev['volume_l'], (int, float)) and ev['volume_l'] > 0 and not math.isnan(ev['volume_l']))
    has_valid_wt = (ev['weight_kg'] is not None and isinstance(ev['weight_kg'], (int, float)) and ev['weight_kg'] > 0 and not math.isnan(ev['weight_kg']))
    if not has_valid_vol and not has_valid_wt:
        unranked_reasons.append('missing_measurements')

    is_ranked = (len(unranked_reasons) == 0)

    score = None
    tier = 'Não classificado (Dados insuficientes)'
    pros = []
    cons = []

    if is_ranked:
        score = 50

        # 1. Substrate Material & Ingestion Safety
        mat = ev['material']
        if mat == LitterMaterial.TOFU_PLANT:
            score += 14
            pros.append('Substrato Vegetal / Tofu (+14)')
        elif mat == LitterMaterial.WOOD:
            score += 10
            pros.append('Fibras Naturais de Madeira (+10)')
        elif mat == LitterMaterial.BENTONITE:
            score += 10
            pros.append('Argila Bentonite Natural (+10)')
        elif mat == LitterMaterial.SILICA:
            score -= 6
            cons.append('Cristais de Sílica Sintética (-6)')
        elif mat == LitterMaterial.SEPIOLITE:
            score -= 12
            cons.append('Argila Sepiolite de Baixa Absorção (-12)')
        else:
            score += 2
            pros.append('Argila Mineral Padrão (+2)')

        # Kitten Compaction Risk: Neonatal & juvenile kittens groom paws and risk lethal GI obstruction with clumping clay
        if ev['is_kitten_targeted'] and mat == LitterMaterial.BENTONITE and ev['is_clumping']:
            score -= 15
            cons.append('Perigo de Compactação Digestiva em Gatinhos (-15)')

        # 2. Clumping Hygiene vs Ammonia Buildup
        if ev['is_clumping']:
            score += 15
            pros.append('Aglomerante / Isolamento de Urina (+15)')
        else:
            score -= 12
            cons.append('Não Aglomerante / Acumulação de Urina (-12)')

        # 3. Feline Respiratory Health & Olfactory Protection (Perfume Penalty)
        if ev['is_unscented']:
            score += 6
            pros.append('100% Inodoro / Sem Perfume (+6)')
        elif ev['has_perfume']:
            score -= 15
            cons.append(f"Perfume / Fragrância Artificial ({ev['scent_name'] or 'Sintético'}) (-15)")

        # 4. Respiratory Dust Control (Feline Asthma Prevention)
        if ev['is_low_dust']:
            score += 8
            pros.append('Baixo Pó / Dust-Free (+8)')
        elif mat in [LitterMaterial.BENTONITE, LitterMaterial.SEPIOLITE, LitterMaterial.SILICA, LitterMaterial.OTHER_MINERAL]:
            score -= 8
            cons.append('Sem Garantia Baixo Pó (-8)')

        # 5. Natural Odor Neutralization (Non-masking Adsorption)
        if ev['has_active_carbon']:
            score += 5
            pros.append('Carvão Ativado Neutralizador (+5)')
        if ev['has_baking_soda']:
            score += 3
            pros.append('Bicarbonato Desodorizante (+3)')

        # 6. Environmental & Disposal
        if ev['is_biodegradable']:
            score += 4
            pros.append('Biodegradável / Ecológico (+4)')
        if ev['is_flushable']:
            score += 2
            pros.append('Deitável na Sanita (+2)')

        # Clamping strictly to [10, 95]
        score = max(10, min(95, score))

        # Veterinary Ceiling Cap: Heavily perfumed litters cause respiratory distress and litter box avoidance
        if ev['has_perfume'] and score >= 70:
            score = 69

        # Respiratory Safety Cap: Un-dedusted mineral clay poses chronic asthma/bronchitis risk, cannot exceed Tier B
        if mat in [LitterMaterial.BENTONITE, LitterMaterial.SEPIOLITE, LitterMaterial.OTHER_MINERAL] and not ev['is_low_dust'] and score >= 75:
            score = 74

        # Tier assignment
        if score >= 85:
            tier = 'Tier S (Ultra-Premium)'
        elif score >= 70:
            tier = 'Tier A (Excelente / Alto Desempenho)'
        elif score >= 55:
            tier = 'Tier B (Médio / Boa Relação)'
        elif score >= 40:
            tier = 'Tier C (Básico / Convencional)'
        else:
            tier = 'Tier D (Evitar / Baixa Qualidade)'

    # Calculate Value Ratio: Score / (€ per Liter or € per kg)
    value_ratio = None
    if is_ranked and score is not None:
        ref_price = None
        if ev.get('unit_price_l') is not None and ev['unit_price_l'] > 0:
            ref_price = ev['unit_price_l']
        elif ev.get('unit_price_kg') is not None and ev['unit_price_kg'] > 0:
            ref_price = ev['unit_price_kg']

        if ref_price is not None and ref_price > 0:
            vr = score / ref_price
            if not math.isnan(vr) and not math.isinf(vr) and vr > 0:
                value_ratio = round(vr, 1)

    p['score'] = score
    p['tier'] = tier
    p['is_ranked'] = is_ranked
    p['unranked_reasons'] = unranked_reasons
    p['pros'] = pros
    p['cons'] = cons
    p['value_ratio'] = value_ratio

    # Build minified payload for dashboard table
    min_p = {
        'id': str(p.get('pid', '')),
        'n': name,
        'b': brand,
        'p': price,
        'pl': ev['unit_price_l'],
        'pkg': ev['unit_price_kg'],
        'vol': ev['volume_l'],
        'wt': ev['weight_kg'],
        'mat': ev['material'],
        'clump': ev['is_clumping'],
        'scent': ev['has_perfume'],
        'unscent': ev['is_unscented'],
        'scent_n': ev['scent_name'],
        'dust': ev['is_low_dust'],
        'carb': ev['has_active_carbon'],
        'soda': ev['has_baking_soda'],
        'bio': ev['is_biodegradable'],
        'flush': ev['is_flushable'],
        't': tier,
        's': score,
        'vr': value_ratio,
        'ir': is_ranked,
        'ur': unranked_reasons,
        'u': p.get('pdp_url', ''),
        'r': p.get('retailer', '')
    }

    return p, min_p

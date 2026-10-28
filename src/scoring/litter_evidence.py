import re
import math

class LitterMaterial:
    TOFU_PLANT = 'Tofu / Vegetal'
    WOOD = 'Madeira'
    BENTONITE = 'Bentonite'
    SILICA = 'Sílica'
    SEPIOLITE = 'Sepiolite'
    OTHER_MINERAL = 'Argila Mineral'

def _sanitize_numeric(val):
    """
    Safely sanitizes a numeric value into a positive float or None.
    Rejects strings, booleans, negative values, 0, NaN, and Inf.
    """
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(str(val).replace(',', '.').strip())
        return f if (not math.isnan(f) and not math.isinf(f) and f > 0) else None
    except (ValueError, TypeError):
        return None

def _safe_div(a, b):
    """
    Safely divides a by b, returning rounded float or None on invalid input,
    zero denominator, or overflow.
    """
    try:
        if a is None or b is None:
            return None
        fa = float(a)
        fb = float(b)
        if math.isnan(fa) or math.isnan(fb) or math.isinf(fa) or math.isinf(fb) or fb <= 0:
            return None
        res = fa / fb
        return round(res, 2) if (not math.isnan(res) and not math.isinf(res) and res > 0) else None
    except (ValueError, TypeError, ZeroDivisionError):
        return None

def extract_litter_measurements(text, desc=''):
    """
    Extracts volume in Liters (L) and weight in Kilograms (kg) from title and description.
    Supports multipacks ('2 x 10 L', 'Pack 2x Sanicat 10L', '2 x 6 kg'), decimal commas, 
    and standard Portuguese / European units (l, lt, lts, ltr, ltrs, kgs, quilos, gr).
    Protects against false positives (e.g. '4G', '3 em 1', '7 dias').
    """
    combined = f"{text or ''} {desc or ''}".replace('\xa0', ' ').replace('\u202f', ' ')
    
    volume_l = None
    weight_kg = None
    
    vol_units = r'(?:l|lt|lts|ltr|ltrs|litros?|litres?)'
    wt_units = r'(?:kgs?|quilos?|kilos?|kilograms?|quilogramas?|g|gr|gramas?)'
    
    # 1. Multi-pack volume:
    # A) Contiguous: '2 x 10 L', '2x10l', '2 * 10L', 'pack 2 x 15 L'
    m_vol_multi = re.search(r'\b(\d+)\s*(?:x|\*)\s*(\d+(?:[.,]\d+)?)\s*' + vol_units + r'\b', combined, re.I)
    # B) Discontinuous: 'Pack 2x Sanicat 10L', 'Pack 2 x Areia 10 L'
    if not m_vol_multi:
        m_vol_multi = re.search(r'\bpack\s*(\d+)\s*x\s+.*?\b(\d+(?:[.,]\d+)?)\s*' + vol_units + r'\b', combined, re.I)
        
    if m_vol_multi:
        qty = float(m_vol_multi.group(1))
        unit_v = float(m_vol_multi.group(2).replace(',', '.'))
        if qty > 0 and unit_v > 0:
            volume_l = round(qty * unit_v, 2)
    else:
        # Single volume: '10 L', '15 l', '5,5 litros', '10 lt'
        m_vol_single = re.search(r'\b(\d+(?:[.,]\d+)?)\s*' + vol_units + r'\b', combined, re.I)
        if m_vol_single:
            v_val = float(m_vol_single.group(1).replace(',', '.'))
            if v_val > 0:
                volume_l = v_val
            
    # 2. Multi-pack weight:
    # A) Contiguous: '2 x 6 kg', '2x7kg', '2 * 6 kgs'
    m_wt_multi = re.search(r'\b(\d+)\s*(?:x|\*)\s*(\d+(?:[.,]\d+)?)\s*(' + wt_units + r')\b', combined, re.I)
    # B) Discontinuous: 'Pack 2x Sanicat 6kg'
    if not m_wt_multi:
        m_wt_multi = re.search(r'\bpack\s*(\d+)\s*x\s+.*?\b(\d+(?:[.,]\d+)?)\s*(' + wt_units + r')\b', combined, re.I)

    if m_wt_multi:
        qty = float(m_wt_multi.group(1))
        unit_w = float(m_wt_multi.group(2).replace(',', '.'))
        u = m_wt_multi.group(3).lower()
        if qty > 0 and unit_w > 0:
            # Protect against false positive grams < 50g (e.g. 4G, 5G)
            if u in ['g', 'gr', 'gramas'] and unit_w < 50:
                pass
            else:
                tot = qty * unit_w
                is_kg = u.startswith('k') or u.startswith('q')
                weight_kg = round(tot if is_kg else tot / 1000.0, 2)
    else:
        # Single weight: '6 kg', '10 kgs', '5 quilos', '500 g', '400 gr'
        matches = re.finditer(r'\b(\d+(?:[.,]\d+)?)\s*(' + wt_units + r')\b', combined, re.I)
        for m in matches:
            val_str, u = m.group(1), m.group(2).lower()
            val = float(val_str.replace(',', '.'))
            if val <= 0:
                continue
            # Protect against false positive '4G', '5G', '3G': reject grams < 50g
            if u in ['g', 'gr', 'gramas'] and val < 50:
                continue
            is_kg = u.startswith('k') or u.startswith('q')
            weight_kg = round(val if is_kg else val / 1000.0, 2)
            break

    return volume_l, weight_kg

def classify_litter_material(text, desc=''):
    """
    Identifies the primary substrate material with strict hierarchy:
    1. Composite Bentonite with secondary silica crystals -> Bentonite
    2. Silica Gel / Crystals (guarded against negations like 'sem sílica')
    3. Specific Plant Substrates (Tofu, Mandioca, Milho, Ervilha, Palha, Soja, Papel)
    4. Wood / Pellets / Madeira (Cat's Best, Pinho, Madeira)
    5. Generic Vegetal / Plant-based
    6. Bentonite (Bentonite, Montmorilonite, Sandy, Biokat's, Ever Clean)
    7. Sepiolite & Economy Absorbent Clays
    """
    combined = f"{text or ''} {desc or ''}".lower()

    # Composite Guard: Bentonite with secondary silica crystals (e.g., 'bentonite com cristais de sílica')
    is_bentonite_composite = bool(re.search(
        r'\b(?:bentonit[ae].*?(?:cristais|p[ée]rolas)?.*?(?:de\s+)?s[íi]lica|(?:cristais|p[ée]rolas)\s+de\s+s[íi]lica.*?(?:em|com)\s+bentonit[ae])\b',
        combined
    ))
    if is_bentonite_composite:
        return LitterMaterial.BENTONITE

    # 1. Silica Gel / Crystals (Guarded against negations: 'sem sílica', 'livre de sílica', 'sem cristais de sílica')
    silica_negated = bool(re.search(r'\b(?:sem|livre\s+de|isento\s+de|no|without|alternativa\s+vegetal\s+[àa])\s+(?:cristais\s+de\s+)?s[íi]lica\b', combined))
    if not silica_negated and re.search(r'\b(?:s[íi]lica|silica\s*gel|gel\s+de\s+s[íi]lica|cristais(?:\s+de\s+s[íi]lica)?|p[ée]rolas\s+de\s+s[íi]lica)\b', combined):
        return LitterMaterial.SILICA

    # 2. Specific Plant Substrates (Tofu, Mandioca/Cassava, Corn/Milho, Pea/Ervilha, Palha/Straw, Soja/Soy, Papel)
    if re.search(r'\b(?:tofu|mandioca|cassava|milho|corn|ervilha|pea(?:\s+husk)?|palha|straw|soja|soy(?:bean)?|papel(?:\s+reciclado)?|recycled\s+paper)\b', combined):
        return LitterMaterial.TOFU_PLANT

    # 3. Wood / Pellets / Madeira (Cat's Best, Pinho/Pine, Wood, Pellets, Serradura, Abeto, Cedro)
    if re.search(r"\b(?:madeira|pinho|pine|wood|pellets?(?:\s+de\s+madeira)?|fibra[s]?\s+de\s+madeira|aparas|cat'?s\s+best|cats\s+best|serradura|abeto|cedro)\b", combined):
        return LitterMaterial.WOOD

    # 4. Bentonite Brand & Mineral Primacy (Bentonite, Ever Clean, Biokat's, Tigerino, Sandy, Montmorilonite)
    # Primacy prevents 'carvão vegetal ativado' from hijacking bentonite into plant substrate
    if re.search(r'\b(?:bentonit[ae]|argila\s+bentonit[ae]|bentonit[ae]\s+(?:branca|cinzenta)|montmorilonit[ae]|ever\s+clean|tigerino|biokat\'?s?|sandy)\b', combined):
        return LitterMaterial.BENTONITE

    # 5. Generic Plant-Based / Vegetal (Must not match 'carvão vegetal' or 'óleo vegetal')
    plant_cleaned = re.sub(r'\b(?:carv[ãa]o|carbono|[óo]leo|gordura)\s+vegeta(?:l|is)\b', '', combined)
    if re.search(r'\b(?:areia\s+vegetal|leito\s+vegetal|substrato\s+vegetal|fibra[s]?\s+vegeta(?:l|is)|100%\s*vegeta(?:l|is)|origem\s+vegetal|plant[- ]based)\b', plant_cleaned):
        return LitterMaterial.TOFU_PLANT

    # 6. Sepiolite & Non-clumping Common Clay
    if re.search(r'\b(?:sepiolit[ae]|argila\s+absorvente(?:\s+comum)?|sepiol[íi]tic[oa]|atapulgit[ae]|attapulgite|argila\s+sepiolit[ae])\b', combined):
        return LitterMaterial.SEPIOLITE

    # 7. Generic clumping clay -> Bentonite (Strict: MUST form clumps and not be negated)
    is_negated_clumping = bool(re.search(r'\b(?:n[ãa]o|no|non|sem|sin|sans)\s+(?:forma\s+torr(?:[ãa]o|[õo]es)|aglomerante)\b', combined))
    has_positive_clumping = bool(re.search(r'\b(?:ultra\s+)?aglomerante|clumping\b', combined))
    if has_positive_clumping and not is_negated_clumping and ('argila' in combined or 'areia' in combined):
        return LitterMaterial.BENTONITE

    # 8. Supermarket non-clumping generic mineral areia -> Sepiolite
    if re.search(r'\b(?:areia\s+(?:mineral\s+)?absorvente|areia\s+absorvente|areia\s+higi[ée]nica\s+absorvente|areia\s+de\s+gato\s+absorvente|areia\s+mineral|argila\s+absorvente)\b', combined) and not (has_positive_clumping and not is_negated_clumping):
        return LitterMaterial.SEPIOLITE

    return LitterMaterial.OTHER_MINERAL

def detect_litter_clumping(text, desc=''):
    """
    Determines whether litter forms scooping clumps (aglomerante) or absorbs liquid without clumping.
    Guards against paper/cellulose pellets defaulting to clumping and supports multilingual negations.
    """
    combined = f"{text or ''} {desc or ''}".lower()

    # 1. Explicit non-clumping negations (PT, ES, FR, DE, EN) + Singular/Plural Torrão/Torrões
    negation_pattern = (
        r'\b(?:'
        r'(?:n[ãa]o|no|non)\s+aglomerante|'
        r'(?:n[ãa]o|no)\s+aglomera|'
        r'(?:sem|sin|sans)\s+aglomera[çc][ãa]o|'
        r'sem\s+aglomerar|'
        r'(?:n[ãa]o|no)\s+aglomer[áa]vel|'
        r'(?:n[ãa]o|no)\s+(?:forma|cria)\s+torr(?:[ãa]o|[õo]es)|'
        r'sem\s+(?:forma[çc][ãa]o\s+de\s+)?torr(?:[ãa]o|[õo]es)|'
        r'non[- ]agglom[ée]rante?|'
        r'nicht[- ]klumpend(?:e)?|'
        r'non[- ]clumping|unclumped|'
        r'(?:apenas|somente|exclusivamente|unicamente|puramente)\s+(?:absorvente|absor[çc][ãa]o)'
        r')\b'
    )
    if re.search(negation_pattern, combined):
        return False

    # 2. Positive clumping markers (PT, ES, FR, DE, EN)
    clumping_pattern = (
        r'\b(?:'
        r'aglomerante|clumping|aglomerador|aglomer[áa]vel|'
        r'ultra\s+aglomerante|ultra\s+clumping|compact\s+clumping|instant\s+clumping|fast\s+clumping|'
        r'(?:forma|cria)\s+torr(?:[ãa]o|[õo]es)|'
        r'(?:r[áa]pida|forte|elevada|excelente|boa)\s+aglomera[çc][ãa]o|'
        r'aglomera[çc][ãa]o\s+r[áa]pida|'
        r'forma[çc][ãa]o\s+de\s+torr(?:[ãa]o|[õo]es)|'
        r'torr(?:[ãa]o|[õo]es)\s+compactos?|'
        r'agglom[ée]rante?|klumpend(?:e)?|klumpstreu'
        r')\b'
    )
    has_clumping_marker = bool(re.search(clumping_pattern, combined))
    if has_clumping_marker:
        return True

    # 3. Known Clumping Wood Brands (when snippet omits explicit 'aglomerante')
    if re.search(r"\bcat'?s\s+best\s+(?:original|smart\s+pellets)\b", combined):
        return True

    # 4. Purely absorbent product designation without clumping claims
    is_purely_absorbent_named = bool(re.search(r'\b(?:areia|leito)\s+absorvente\b', combined))
    if is_purely_absorbent_named and not has_clumping_marker:
        return False

    # 5. Substrate-specific defaults
    mat = classify_litter_material(text, desc)

    # Paper/cellulose pellets and non-tofu plant pellets are absorptive, NOT clumping
    is_paper_or_straw_pellet = bool(re.search(r'\b(?:papel|paper|celulose|cellulose|palha|straw)\b', combined))
    if is_paper_or_straw_pellet:
        return False

    if mat == LitterMaterial.TOFU_PLANT:
        return True
    if mat == LitterMaterial.BENTONITE:
        return True
    if mat in [LitterMaterial.SILICA, LitterMaterial.SEPIOLITE, LitterMaterial.WOOD, LitterMaterial.OTHER_MINERAL]:
        return False

    return False

def detect_litter_scent(text, desc=''):
    """
    Detects fragrance status with clinical feline olfactory precision:
    Returns (has_perfume, is_explicitly_unscented, scent_name)
    
    Protections:
    1. Preprocesses and strips negated fragrance claims (e.g. 'sem perfume de lavanda')
       to avoid false penalties on hypoallergenic litters.
    2. Enforces comprehensive dictionary of European/Portuguese fragrance variants.
    3. Prevents odor-control claims ('sem cheiro a urina', 'casa inodora') from leaking
       false unscented bonuses.
    4. Permits title-level 'neutro'/'neutra' while strictly shielding 'pH neutro'.
    """
    combined = f"{text or ''} {desc or ''}".lower()
    title_lower = (text or '').lower()

    # Pre-clean non-fragrance usages of scent words (color indicators, soft texture claims)
    cleaned_combined = re.sub(r'\bcor[- ]de[- ]rosas?\b', '[COLOR_PINK]', combined)
    cleaned_combined = re.sub(r'\b(?:cristais|gr[âa]nulos|part[íi]culas)\s+rosas?\b', '[COLOR_PINK]', cleaned_combined)
    cleaned_combined = re.sub(r'\b(?:suave\s+como|toque\s+de|fibras?\s+de)\s+algod[ãa]o\b', '[COTTON_TEXTURE]', cleaned_combined)

    # 1. Negation-strip: supports coordinate clauses ('sem químicos nem perfume', 'sem pó nem perfume')
    negation_clause_pattern = (
        r'\b(?:sem|livre\s+de|isento\s+de|n[ãa]o\s+cont[ée]m)\s+'
        r'(?:qualquer\s+)?'
        r'(?:(?:qu[íi]micos?|aditivos?|corantes?|p[óo]s?|subst[âa]ncias?\s+qu[íi]micas?)\s+(?:nem|e|ou)\s+)?'
        r'(?:adi[çc][ãa]o\s+de\s+)?'
        r'(?:perfumes?|fragr[âa]ncias?|aromas?|cheiros?|odores?\s+adicionados?|aditivos?)'
        r'(?:\s+(?:artificia[li]s?|sint[ée]ticos?|adicionados?))?'
        r'(?:\s*\([^)]*\))?'
        r'(?:\s+(?:nem|ou|de|a|como|tais\s+como)\s+[^.,;\n]+)?'
    )
    cleaned_combined = re.sub(negation_clause_pattern, '[UNSCENTED_CLAIM]', cleaned_combined, flags=re.I)
    cleaned_combined = re.sub(r'\b(?:nem|e\s+sem)\s+(?:qualquer\s+)?(?:perfumes?|fragr[âa]ncias?|aromas?|cheiros?)\b', '[UNSCENTED_CLAIM]', cleaned_combined, flags=re.I)

    # 2. Comprehensive Scent Dictionary (Synthetic VOCs harmful to felines)
    scent_patterns = [
        (r'\b(?:sab[ãa]o\s+de\s+marselha|marseille(?:\s+soap)?|marselha|savon\s+de\s+marseille)\b', 'Sabão de Marselha'),
        (r'\b(?:flor\s+de\s+l[óo]tus|l[óo]tus|lotus(?:\s+flower)?)\b', 'Flor de Lótus'),
        (r'\b(?:talco(?:\s+de\s+beb[ée])?|baby\s*powder|babypowder|talc|p[óo]\s+de\s+talco)\b', 'Talco / Baby Powder'),
        (r'\b(?:lavanda|lavender|alfazema|lavandina)\b', 'Lavanda / Alfazema'),
        (r'\b(?:baunilha|vanilla)\b', 'Baunilha'),
        (r'\b(?:aroma\s+(?:a|de)\s+alo[ée](?:\s+vera)?|fragr[âa]ncia\s+(?:a|de)\s+alo[ée]|perfume\s+(?:a|de)\s+alo[ée]|alo[ée]\s+vera\s+scent)\b', 'Aloé Vera'),
        (r'\b(?:citrinos?|lim[ãa]o|laranja|citrus|lemon|orange|mandarina|tangerina)\b', 'Citrinos'),
        (r'\b(?:aroma\s+(?:a|de)\s+ma[çc][ãa]|apple\s+scent|perfume\s+(?:a|de)\s+ma[çc][ãa])\b', 'Maçã'),
        (r'\b(?:aroma\s+(?:a|de)\s+rosas?|perfume\s+(?:a|de)\s+rosas?|fragr[âa]ncia\s+(?:a|de)\s+rosas?|rose\s+scent|rosas?|roses?)\b', 'Rosas'),
        (r'\b(?:flor\s+de\s+algod[ãa]o|cotton(?:\s+blossom)?|aroma\s+(?:a|de)\s+algod[ãa]o)\b', 'Flor de Algodão'),
        (r'\b(?:ch[áa]\s+verde|green\s+tea)\b', 'Chá Verde'),
        (r'\b(?:p[êe]ssego|peach|melocot[óo]n)\b', 'Pêssego'),
        (r'\b(?:camomila|chamomile|kamille)\b', 'Camomila'),
        (r'\b(?:eucalipto|eucalyptus)\b', 'Eucalipto'),
        (r'\b(?:aroma\s+(?:a|de)\s+pinho|fragr[âa]ncia\s+(?:a|de)\s+pinho|perfume\s+(?:a|de)\s+pinho|pine\s+scent)\b', 'Pinho'),
        (r'\b(?:aroma\s+floral|fragr[âa]ncia\s+floral|perfume\s+floral|spring\s+flowers?|flores(?:\s+da\s+primavera)?|floral|flowers?|spring\s+garden)\b', 'Floral'),
        (r'\b(?:brisa\s+marinha|marinho|ocean(?:\s+breeze)?|oceano|fresh\s+(?:scent|aroma|breeze|clean|extra)|bianco\s+fresh|ultra\s+fresh|aroma\s+fresco|fragr[âa]ncia\s+fresca|perfume\s+fresco|frescura\s+(?:primaveril|alpina))\b', 'Brisa Marinha / Fresco'),
        (r'\b(?:erva[- ]dos[- ]gatos|catnip)\b', 'Erva-dos-gatos'),
        (r'\b(?:perfumad[oa]|scented|lightly\s+scented|aromatizad[oa]|com\s+aroma|com\s+fragr[âa]ncia|com\s+perfume|com\s+cheiro\s+(?:a|agrad[áa]vel)|aroma\s+(?:a|de)\s+[a-zà-ú]+|fragr[âa]ncia\s+(?:a|de)\s+[a-zà-ú]+)\b', 'Perfumado')
    ]

    # Check scent against cleaned text (ignoring negated fragrance mentions)
    for pat, label in scent_patterns:
        if re.search(pat, cleaned_combined):
            return True, False, label

    # Check if title explicitly designates 'Fresh' variant
    if re.search(r'\b(?:fresh|frescura)\b', title_lower) and not re.search(r'\b(?:keep|mant[ée]m)\b', title_lower):
        return True, False, 'Fresco / Fresh'

    # Title Aloe Vera variant (e.g. Sanicat Aloe Vera)
    if re.search(r'\balo[ée](?:\s+vera)?\b', title_lower):
        return True, False, 'Aloé Vera'

    # 3. Strict Unscented Evaluation:
    # A) Did we strip an explicit negation claim like '[UNSCENTED_CLAIM]'?
    if '[UNSCENTED_CLAIM]' in cleaned_combined:
        return False, True, "Sem perfume (Inodoro)"

    # B) Explicit unscented markers, protected against odor-control leakage ('sem cheiro a urina', 'casa inodora')
    unscented_pattern = (
        r'\b(?:sem\s+(?:perfume|fragr[âa]ncia|aroma|adi[çc][ãa]o\s+de\s+perfume|cheiro\s+adicionado)|'
        r'unscented|fragrance[- ]free|0%\s*perfume|sem\s+odores?\s+adicionados?|'
        r'(?:odor|cheiro|aroma)\s+neutro)\b'
    )
    if re.search(unscented_pattern, cleaned_combined):
        return False, True, "Sem perfume (Inodoro)"

    # C) Pre-filter household claims ('casa inodora', 'ambiente sem cheiro') before evaluating product unscented state
    home_cleaned = re.sub(r'\b(?:casa|ambiente|lar|divis[ãa]o)\s+(?:totalmente\s+)?inodor[oa]\b', '', cleaned_combined)
    home_cleaned = re.sub(r'\b(?:casa|ambiente|lar)\s+sem\s+cheiro\b', '', home_cleaned)

    # Check 'inodoro' after removing household claims
    if re.search(r'\binodor[oa]\b', home_cleaned):
        return False, True, "Sem perfume (Inodoro)"

    # D) Title-level 'neutro' / 'neutra' (standard supermarket unscented SKU naming, protected against 'pH neutro')
    title_ph_cleaned = re.sub(r'\bph\s*(?:[-:]|\s)\s*neutr[oa]\b', '', title_lower)
    title_ph_cleaned = re.sub(r'\bph\s+neutr[oa]\b', '', title_ph_cleaned)
    if re.search(r'\bneutr[oa]\b', title_ph_cleaned):
        return False, True, "Sem perfume (Inodoro)"

    # E) Context-safe 'sem cheiro' (not followed by urine/ammonia/feces/desagradável)
    if re.search(r'\bsem\s+cheiro\b(?!\s+(?:a|de)?\s*(?:urina|fezes|amon[íi]aco|desagrad[áa]vel|mau|maus))\b', home_cleaned):
        return False, True, "Sem perfume (Inodoro)"

    return False, False, None

def detect_litter_dust(text, desc=''):
    """
    Detects low-dust / dust-free guarantees for feline asthma prevention.
    Employs strict negation guards, filters chemical/talc powder false positives,
    and supports Portuguese, Spanish, German, and European decimal notation (99,5%).
    """
    combined = f"{text or ''} {desc or ''}".lower()

    # 1. Negation guards (e.g., 'não é sem pó', 'não é livre de pó', 'pode conter pó')
    negation_pattern = r'\b(?:n[ãa]o\s+(?:[ée]\s+)?(?:100%|totalmente\s+)?(?:sem|livre\s+de|dust[- ]free|isento\s+de|isenta\s+de)\s*(?:p[óo]s?|poeiras?|polvo)?|pode\s+(?:conter|largar|libertar|soltar|fazer)\s+(?:algum\s+)?p[óo])\b'
    if re.search(negation_pattern, combined):
        return False

    # 2. Additive powder false positive guard ('sem pó de talco', 'sem pó químico', 'sem pó de arroz')
    cleaned = re.sub(r'\bsem\s+p[óo]\s+(?:de\s+talco|qu[íi]mico|de\s+arroz)\b', '', combined)

    # 3. Master dust-free / low-dust pattern
    pattern = (
        r'\b(?:'
        # Percentages with dot or comma: 99%, 99.9%, 99,5%, 100%, 0%
        r'(?:99(?:[.,]\d+)?%|100%|zero|0%)\s*(?:sem\s+p[óo]s?|dust[- ]free|livre\s+de\s+poeiras?|livre\s+de\s+p[óo]s?|libre\s+de\s+polvo|isento\s+de\s+p[óo]|isenta\s+de\s+p[óo]|staubfrei)|'
        # Portuguese dust-free phrases & plurals
        r'sem\s+p[óo]s?|sem\s+poeiras?|livre\s+de\s+p[óo]s?|livre\s+de\s+poeiras?|isent[oa]\s+de\s+p[óo]s?|isent[oa]\s+de\s+poeiras?|'
        # Low-dust phrases (baixo/reduzido/pouco teor/nível de/em pó/poeiras)
        r'(?:baixo|reduzido|pouco)\s+(?:teor|n[íi]vel)\s+(?:de|em)\s+(?:p[óo]s?|poeiras?)|'
        r'pouco\s+p[óo]|pouca\s+poeira|baixo\s+p[óo]|quase\s+sem\s+p[óo]|'
        # Action negations: não liberta/gera/levanta/produz/larga/faz/solta/cria pó/poeira
        r'n[ãa]o\s+(?:liberta|gera|levanta|produz|larga|faz|solta|cria)\s+(?:p[óo]s?|poeiras?)|'
        # Compounds: anti-pó, anti-poeira
        r'anti[- ]?(?:p[óo]|poeira)s?|'
        # English
        r'dust[- ]free|dustless|low[- ]dust|virtually\s+dust[- ]free|'
        # Spanish (common on Iberian retailer stock like Kiwoko, Tiendanimal, Zooplus PT)
        r'sin\s+polvo|libre\s+de\s+polvo|bajo\s+en\s+polvo|no\s+levanta\s+polvo|no\s+(?:suelta|genera|produce)\s+polvo|'
        # German
        r'staubfrei|staubarm'
        r')\b'
    )
    return bool(re.search(pattern, cleaned))

def detect_litter_features(text, desc=''):
    """
    Detects natural odor neutralization (carbon, baking soda) and eco-credentials.
    Guards against negations, packaging false positives, and mineral clay greenwashing.
    """
    combined = f"{text or ''} {desc or ''}".lower()
    mat = classify_litter_material(text, desc)
    is_organic = mat in [LitterMaterial.TOFU_PLANT, LitterMaterial.WOOD]

    # 1. Active Carbon / Activated Charcoal
    # Guard against negations: 'sem carvão', 'livre de carvão', 'without charcoal'
    carbon_negated = bool(re.search(r'\b(?:sem|livre\s+de|isento\s+de|no|without)\s+(?:carv[ãa]o|carbono|charcoal|carbon)\b', combined))
    has_active_carbon = False
    if not carbon_negated:
        carbon_pattern = (
            r'\b(?:'
            r'(?:carv[ãa]o|carbono)\s+(?:vegetal\s+)?ac?ti[vv](?:ad)?[oa]s?'
            r'|ac?ti[vv](?:ad)?[oa]s?\s+(?:carv[ãa]o|carbono)'
            r'|activ(?:e|ated)\s+(?:charcoal|carbon)'
            r'|carv[ãa]o\s+vegetal'
            r'|com\s+carv[ãa]o\b(?!\s+(?:ecol[óo]gica|de\s+carbono))'
            r'|charcoal'
            r')\b'
        )
        has_active_carbon = bool(re.search(carbon_pattern, combined))

    # 2. Baking Soda / Sodium Bicarbonate
    # Guard against negations: 'sem bicarbonato', 'no baking soda'
    soda_negated = bool(re.search(r'\b(?:sem|livre\s+de|isento\s+de|no|without)\s+(?:bicarbonato|baking\s+soda|sodium\s+bicarbonate|bicarbonate)\b', combined))
    has_baking_soda = False
    if not soda_negated:
        soda_pattern = (
            r'\b(?:'
            r'bicarbonato(?:\s+de\s+s[óo]dio)?'
            r'|baking\s+soda'
            r'|sodium\s+bicarbonate'
            r'|bicarbonate(?:\s+of\s+soda|\s+de\s+soude)?'
            r')\b'
        )
        has_baking_soda = bool(re.search(soda_pattern, combined))

    # 3. Biodegradable: STRICTLY BOUNDED to organic substrates (Tofu, Wood)
    # Mineral clays and synthetic silica are inorganic minerals that cannot decompose biologically.
    is_biodegradable = False
    if is_organic:
        bio_pattern = r'\b(?:100%\s*biodegrad[áa]vel|biodegrad[áa]vel|compost[áa]vel|100%\s*natural|eco-friendly|ecol[óo]gic[oa])\b'
        is_biodegradable = bool(re.search(bio_pattern, combined))

    # 4. Flushable: STRICTLY BOUNDED to organic substrates + strict negation
    # Flushing bentonite or silica damages municipal plumbing.
    flush_negated_pat = (
        r'\b(?:n[ãa]o|nunca|evitar|proibido|jamais)\s+'
        r'(?:[ée]\s+)?(?:deit[áa]vel|descart[áa]vel|deitar|descartar|lan[çc]ar|despejar)?\s*'
        r'(?:na|pela|no\s+vaso)\s+(?:sanit[áa]ri[oa]|sanita|esgoto)\b'
        r'|\b(?:non[- ]flushable|do\s+not\s+flush|never\s+flush)\b'
    )
    is_flush_negated = bool(re.search(flush_negated_pat, combined))

    is_flushable = False
    if is_organic and not is_flush_negated:
        flush_pos_pat = (
            r'\b(?:deit[áa]vel\s+na\s+sanita|descart[áa]vel\s+na\s+sanita|pode\s+(?:ser\s+)?deitad[oa]\s+na\s+sanita|'
            r'flushable|biodegrad[áa]vel\s+na\s+sanita|deit[áa]vel\s+no\s+wc)\b'
        )
        is_flushable = bool(re.search(flush_pos_pat, combined))

    # 5. Kitten targeting detection (Shielded against safety warnings)
    kitten_warned = bool(re.search(
        r'\b(?:n[ãa]o\s+(?:[ée]\s+)?(?:indicad[oa]|recomendad[oa]|apropriad[oa]|aconselhad[oa]|utilizar|usar)|evitar|proibid[oa])\s+(?:para|em|a)?\s*(?:gatinhos?|kittens?|filhotes?|gatitos?)\b',
        combined
    ))
    is_kitten_targeted = False
    if not kitten_warned:
        is_kitten_targeted = bool(re.search(
            r'\b(?:especial\s+(?:para\s+)?gatinhos?|para\s+gatinhos?|para\s+filhotes?|para\s+gatitos?|indicad[oa]\s+para\s+gatinhos?|ideal\s+para\s+gatinhos?|kitten|junior)\b',
            combined
        ))

    return {
        'has_active_carbon': has_active_carbon,
        'has_baking_soda': has_baking_soda,
        'is_biodegradable': is_biodegradable,
        'is_flushable': is_flushable,
        'is_kitten_targeted': is_kitten_targeted
    }

def evaluate_litter_evidence(product):
    """
    Extracts all structured physical, material, and chemical attributes of a litter product.
    Returns dictionary with volume, weight, unit prices, material, clumping, scent, dust, and eco features.
    """
    name = product.get('name', '')
    desc = product.get('description', '')
    price = _sanitize_numeric(product.get('price'))
    
    vol_l, wt_kg = extract_litter_measurements(name, desc)
    
    # Check pack_size if EITHER volume OR weight is missing
    if (not vol_l or not wt_kg) and product.get('pack_size'):
        v, w = extract_litter_measurements(product['pack_size'])
        vol_l = vol_l or v
        wt_kg = wt_kg or w

    unit_price_l = _safe_div(price, vol_l)
    unit_price_kg = _safe_div(price, wt_kg)
    
    # Fallback to retailer-scraped unit_price_l if not calculated
    if not unit_price_l and product.get('unit_price_l'):
        scraped_pl = _sanitize_numeric(product.get('unit_price_l'))
        if scraped_pl and scraped_pl > 0:
            unit_price_l = scraped_pl

    # Fallback to retailer-scraped unit_price_kg if not calculated
    if not unit_price_kg and product.get('unit_price_kg'):
        scraped_pkg = _sanitize_numeric(product.get('unit_price_kg'))
        if scraped_pkg and scraped_pkg > 0:
            unit_price_kg = scraped_pkg

    # Infer missing volume or weight if unit price and total price are valid
    if not vol_l and price and price > 0 and unit_price_l and unit_price_l > 0:
        vol_l = _safe_div(price, unit_price_l)
        if vol_l: vol_l = round(vol_l, 1)
    if not wt_kg and price and price > 0 and unit_price_kg and unit_price_kg > 0:
        wt_kg = _safe_div(price, unit_price_kg)
        if wt_kg: wt_kg = round(wt_kg, 1)

    material = classify_litter_material(name, desc)
    is_clumping = detect_litter_clumping(name, desc)
    has_perfume, is_unscented, scent_name = detect_litter_scent(name, desc)
    is_low_dust = detect_litter_dust(name, desc)
    features = detect_litter_features(name, desc)

    return {
        'volume_l': vol_l,
        'weight_kg': wt_kg,
        'unit_price_l': unit_price_l,
        'unit_price_kg': unit_price_kg,
        'material': material,
        'is_clumping': is_clumping,
        'has_perfume': has_perfume,
        'is_unscented': is_unscented,
        'scent_name': scent_name,
        'is_low_dust': is_low_dust,
        **features
    }

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from .base import BaseScraper

class ZUScraper(BaseScraper):
    """
    Scraper for ZU.pt (Sonae Pet specialist).
    Base URL: https://www.zu.pt
    Leverages Shopify collections JSON endpoints for reliable cataloging,
    and enriches products via PDP pages.
    """
    BASE_URL = 'https://www.zu.pt'
    WET_HANDLE = 'alimentacao-humida'
    DRY_HANDLE = 'alimentacao-seca'
    LITTER_HANDLE = 'areias'

    def _parse_weight_from_text(self, text):
        """Attempts to parse total weight in kg from text (e.g. '85g', '12 x 85 g', '2kg', '400 g')."""
        if not text:
            return None
        clean = text.replace('\xa0', ' ').lower()
        
        # Check multipack: 12 x 85 g or 12x85g
        m_multi = re.search(r'(\d+)\s*(?:x|un(?:idader?s?)?)\s*(\d+(?:[.,]\d+)?)\s*(k?g)', clean)
        if m_multi:
            qty = float(m_multi.group(1))
            single = float(m_multi.group(2).replace(',', '.'))
            unit = m_multi.group(3)
            weight_g = qty * (single * 1000 if unit == 'kg' else single)
            return weight_g / 1000.0

        # Check single weight: 85 g, 1.5 kg
        m_single = re.search(r'(\d+(?:[.,]\d+)?)\s*(k?g)', clean)
        if m_single:
            val = float(m_single.group(1).replace(',', '.'))
            unit = m_single.group(2)
            return val if unit == 'kg' else (val / 1000.0)

        return None

    def _get_catalog(self, handle, max_pages=None):
        print(f"[ZU] Cataloging collection '{handle}'...")
        products = []
        seen_pids = set()
        page = 1

        while True:
            url = f"{self.BASE_URL}/collections/{handle}/products.json?limit=250&page={page}"
            try:
                raw_json = self.fetch_url(url)
            except Exception as e:
                print(f"[ZU] Error fetching catalog page {page}: {e}")
                raise

            if not raw_json:
                break

            try:
                data = json.loads(raw_json)
            except Exception as e:
                print(f"[ZU] Failed parsing JSON for page {page}: {e}")
                break

            page_products = data.get('products', [])
            if not page_products:
                break

            NON_LITTER_KEYWORDS = {
                'caixa', 'casa de banho', 'tabuleiro', 'pá para', 'pa para',
                'tapete', 'sacos', 'saco', 'neutralizador', 'desodorizante', 'filtro',
                'resguardo', 'sanitário fechado'
            }

            for p in page_products:
                pid = str(p.get('id'))
                if pid in seen_pids:
                    continue

                prod_type = (p.get('product_type') or '').lower()
                tags = [t.lower() for t in p.get('tags', [])]
                title = p.get('title', '')
                title_l = title.lower()

                # Negative check for dogs
                is_dog = any(k in title_l or k in tags for k in ['cão', 'cao', 'dog', 'puppy'])
                if is_dog and 'gato' not in title_l:
                    continue

                # Ensure it's cat-related
                is_cat = (
                    prod_type == 'gato' or
                    'gato' in tags or
                    'gato' in title_l or
                    'kitten' in title_l or
                    'júnior' in title_l or
                    ('areia' in tags and handle == self.LITTER_HANDLE) or
                    ('areia' in title_l and handle == self.LITTER_HANDLE)
                )
                if not is_cat:
                    continue

                # Exclude accessories when scraping litter
                if handle == self.LITTER_HANDLE:
                    if 'acessorios' in tags or any(k in title_l for k in NON_LITTER_KEYWORDS):
                        continue

                seen_pids.add(pid)

                # Variant price & details
                variants = p.get('variants', [])
                price = None
                sku = pid
                if variants:
                    v = variants[0]
                    try:
                        price = float(v.get('price'))
                    except (ValueError, TypeError):
                        pass
                    sku = v.get('sku') or pid

                brand = p.get('vendor') or 'Desconhecida'
                handle_str = p.get('handle')
                pdp_url = f"{self.BASE_URL}/products/{handle_str}" if handle_str else None

                products.append({
                    'pid': sku,
                    'name': title,
                    'brand': brand,
                    'price': price,
                    'unit_price_kg': None,
                    'pack_size': '',
                    'pdp_url': pdp_url,
                    'retailer': 'ZU',
                    'body_html': p.get('body_html', '')
                })

            print(f"[ZU] Page {page}: found {len(page_products)} items (cat items cataloged so far: {len(products)})")
            if len(page_products) < 250:
                break
            page += 1
            if max_pages and page > max_pages:
                break
            time.sleep(self.rate_limit_delay)

        print(f"[ZU] Finished cataloging '{handle}': {len(products)} total cat products.")
        return products

    def _clean_zu_text(self, text):
        if not text:
            return ""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        cleaned = []
        for line in lines:
            if line.lower() in ['caraterísticas', 'características', 'descrição:', 'descrição', 'benefícios:', 'benefícios']:
                continue
            cleaned.append(line)
        return ' '.join(cleaned)

    def _fetch_details(self, p):
        url = p.get('pdp_url')
        if not url:
            if p.get('body_html'):
                soup_body = BeautifulSoup(p['body_html'], 'html.parser')
                p['description'] = self._clean_zu_text(soup_body.get_text(separator=' ', strip=True))
                p.pop('body_html', None)
            return p

        try:
            html = self.fetch_url(url, timeout=12)
            if not html:
                if p.get('body_html'):
                    soup_body = BeautifulSoup(p['body_html'], 'html.parser')
                    p['description'] = self._clean_zu_text(soup_body.get_text(separator=' ', strip=True))
                    p.pop('body_html', None)
                return p
        except Exception as e:
            p['fetch_error'] = str(e)
            if p.get('body_html'):
                soup_body = BeautifulSoup(p['body_html'], 'html.parser')
                p['description'] = self._clean_zu_text(soup_body.get_text(separator=' ', strip=True))
                p.pop('body_html', None)
            return p

        soup = BeautifulSoup(html, 'html.parser')

        # Unit price
        up_span = soup.find('span', class_='unit-price')
        unit_price_val = None
        unit_price_l = None
        if up_span:
            up_text = up_span.get_text().replace('\xa0', ' ')
            m_up_kg = re.search(r'(\d+[.,]\d+)\s*€?\s*/\s*kg', up_text, re.I)
            m_up_l = re.search(r'(\d+[.,]\d+)\s*€?\s*/\s*(?:l|lt|litros?)\b', up_text, re.I)
            if m_up_kg:
                unit_price_val = float(m_up_kg.group(1).replace(',', '.'))
            if m_up_l:
                unit_price_l = float(m_up_l.group(1).replace(',', '.'))
            if not unit_price_val and not unit_price_l:
                m = re.search(r'(\d+[.,]\d+)', up_text)
                if m:
                    unit_price_val = float(m.group(1).replace(',', '.'))

        # Pack size
        pack_span = soup.find('span', class_='metafield-multi_line_text_field')
        pack_size = pack_span.get_text(strip=True) if pack_span else ''

        # If unit price missing, compute from pack size or product name
        if not unit_price_val and p.get('price'):
            weight_kg = self._parse_weight_from_text(pack_size) or self._parse_weight_from_text(p.get('name'))
            if weight_kg and weight_kg > 0:
                unit_price_val = round(p['price'] / weight_kg, 2)

        if not unit_price_l and p.get('price'):
            m_vol = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(?:l|lt|litros?)\b', f"{p.get('name', '')} {pack_size}", re.I)
            if m_vol:
                vol = float(m_vol.group(1).replace(',', '.'))
                if vol > 0:
                    unit_price_l = round(p['price'] / vol, 2)

        # Ingredients, Nutrition & Description from tabs
        ingredients_text = ""
        nutrition_text = ""
        description_text = ""

        collapsible_tabs = soup.find_all(class_=lambda c: c and 'collapsible' in c)
        for el in collapsible_tabs:
            tab_text = el.get_text(separator='\n', strip=True)
            tab_lower = tab_text.lower()

            # Separate description first
            if any(k in tab_lower for k in ['caraterísticas', 'descrição']) and not description_text:
                description_text = self._clean_zu_text(tab_text)

            # Look strictly for composition section
            if any(k in tab_lower for k in ['ingrediente', 'composição']):
                m_ing = re.search(r'(?:Ingredientes|Composição):\s*(.*?)(?=(?:Constituintes\s+anal[íi]ticos|Aditivos|Energia|$))', tab_text, re.I | re.S)
                if m_ing and not ingredients_text:
                    cand = m_ing.group(1).strip()
                    # Must not be marketing copy
                    if not cand.startswith('Caraterísticas') and not cand.startswith('Descrição:'):
                        ingredients_text = cand

            # Look strictly for analytical constituents section
            m_nut = re.search(r'(?:Constituintes\s+anal[íi]ticos|Análise|Informação\s+nutricional|Componentes\s+anal[íi]ticos|Composição\s+anal[íi]tica):\s*(.*?)(?=(?:Aditivos|Energia|$))', tab_text, re.I | re.S)
            if m_nut and not nutrition_text:
                nutrition_text = m_nut.group(1).strip()
            elif any(k in tab_lower for k in ['constituintes analíticos', 'informação nutricional', 'componentes analíticos', 'composição analítica']) and not nutrition_text:
                if '%' in tab_text and any(k in tab_lower for k in ['proteína', 'proteina', 'humidade', 'gordura']):
                    nutrition_text = tab_text

        # Fallback to body_html if available
        if not description_text and p.get('body_html'):
            description_text = self._clean_zu_text(BeautifulSoup(p['body_html'], 'html.parser').get_text(separator=' ', strip=True))

        if not ingredients_text and p.get('body_html'):
            b_soup = BeautifulSoup(p['body_html'], 'html.parser')
            b_text = b_soup.get_text(separator='\n', strip=True)
            m_ing = re.search(r'(?:Ingredientes|Composição):\s*(.*?)(?=(?:Constituintes|Aditivos|$))', b_text, re.I | re.S)
            if m_ing:
                cand = m_ing.group(1).strip()
                if not cand.startswith('Caraterísticas') and not cand.startswith('Descrição:') and not cand.startswith('Benefícios'):
                    ingredients_text = cand

        if not nutrition_text and p.get('body_html'):
            b_soup = BeautifulSoup(p['body_html'], 'html.parser')
            b_text = b_soup.get_text(separator='\n', strip=True)
            m_nut = re.search(r'(?:Constituintes\s+anal[íi]ticos|Análise|Informação\s+nutricional|Componentes\s+anal[íi]ticos|Composição\s+anal[íi]tica):\s*(.*?)(?=(?:Aditivos|Energia|$))', b_text, re.I | re.S)
            if m_nut:
                nutrition_text = m_nut.group(1).strip()
            elif any(k in b_text.lower() for k in ['constituintes analíticos', 'informação nutricional', 'componentes analíticos', 'composição analítica']) and not nutrition_text:
                if '%' in b_text and any(k in b_text.lower() for k in ['proteína', 'proteina', 'humidade', 'gordura']):
                    nutrition_text = b_text

        # Final sanity check: if ingredients or nutrition field somehow contains marketing description header, clear it
        if ingredients_text.startswith('Caraterísticas') or ingredients_text.startswith('Descrição:') or ingredients_text.startswith('Benefícios'):
            if not description_text:
                description_text = ingredients_text
            ingredients_text = ""

        if nutrition_text.startswith('Caraterísticas') or nutrition_text.startswith('Descrição:') or nutrition_text.startswith('Benefícios'):
            if not description_text:
                description_text = nutrition_text
            nutrition_text = ""

        # Clean up temporary field
        p.pop('body_html', None)

        p['unit_price_kg'] = unit_price_val
        p['unit_price_l'] = unit_price_l
        p['pack_size'] = pack_size
        p['ingredients'] = ingredients_text
        p['nutrition_raw'] = nutrition_text
        p['description'] = description_text
        return p

    def _enrich_with_details(self, products, max_workers=5):
        print(f"[ZU] Fetching details for {len(products)} products (concurrency: {max_workers})...")
        enriched = []
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_prod = {executor.submit(self._fetch_details, prod): prod for prod in products}
            for future in as_completed(future_to_prod):
                enriched.append(future.result())
                done += 1
                if done % 50 == 0 or done == len(products):
                    print(f"[ZU] Fetched details: {done}/{len(products)}")
        return enriched

    def scrape_wet(self, max_pages=None, max_workers=5):
        catalog = self._get_catalog(self.WET_HANDLE, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

    def scrape_dry(self, max_pages=None, max_workers=5):
        catalog = self._get_catalog(self.DRY_HANDLE, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

    def scrape_litter(self, max_pages=None, max_workers=3):
        catalog = self._get_catalog(self.LITTER_HANDLE, max_pages=max_pages)
        # Try loading continente_litter_full.json to cross-reference shared Sonae SKUs for exact measurements
        sku_lookup = {}
        try:
            cont_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'continente_litter_full.json')
            if os.path.exists(cont_path):
                with open(cont_path, 'r', encoding='utf-8') as f:
                    for cp in json.load(f):
                        c_sku = str(cp.get('pid', ''))
                        if c_sku:
                            sku_lookup[c_sku] = cp
        except Exception:
            pass

        # Known ZU Portuguese market litter bag sizes by SKU
        known_zu_litter_sizes = {
            '5745302': '10 l',   # Catfield Bentonite Lavanda
            '5745294': '10 l',   # Catfield Bentonite Natural
            '8971658': '10 l',   # Catfield Bentonite Natural
            '6835625': '10 l',   # Catfield Bentonite Platinum
            '7636428': '10 l',   # Sandy Sabão Marselha
            '7636427': '10 l',   # Sandy Talco Baby Powder
            '7614302': '6 l',    # Catfield Tofu
            '8205013': '6 l',    # Catfield Tofu Chá Verde
            '8205012': '6 l',    # Catfield Tofu Lavanda
            '8548645': '6 l',    # Catfield Bambu
            '6085615': '5 l',    # Catfield Sílica Gel
            '7990581': '5 l',    # Weego Sílica Gel
            '8918751': '6 l',    # Moggy Comfort Tofu
            '8918764': '6 l',    # Moggy Charcoal Tofu
        }

        enriched = []
        for p in catalog:
            sku = str(p.get('pid', ''))
            # Clean description directly from body_html
            if p.get('body_html'):
                soup_body = BeautifulSoup(p['body_html'], 'html.parser')
                p['description'] = self._clean_zu_text(soup_body.get_text(separator=' ', strip=True))
                p.pop('body_html', None)
            else:
                p['description'] = p.get('name', '')

            # Cross-reference shared Sonae SKU
            if not p.get('pack_size'):
                if sku in known_zu_litter_sizes:
                    p['pack_size'] = known_zu_litter_sizes[sku]
                elif sku in sku_lookup:
                    cont_p = sku_lookup[sku]
                    p['pack_size'] = cont_p.get('pack_size', '')
                    if cont_p.get('unit_price_l'):
                        p['unit_price_l'] = cont_p['unit_price_l']
                    if cont_p.get('unit_price_kg'):
                        p['unit_price_kg'] = cont_p['unit_price_kg']

            enriched.append(p)

        return enriched

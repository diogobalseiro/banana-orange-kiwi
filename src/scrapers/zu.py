import json
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
                break

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

            for p in page_products:
                pid = str(p.get('id'))
                if pid in seen_pids:
                    continue

                # Ensure it's cat-related
                prod_type = (p.get('product_type') or '').lower()
                tags = [t.lower() for t in p.get('tags', [])]
                title = p.get('title', '')
                title_l = title.lower()

                is_cat = (
                    prod_type == 'gato' or
                    'gato' in tags or
                    'gato' in title_l or
                    'kitten' in title_l or
                    'júnior' in title_l
                )
                if not is_cat:
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
            page += 1
            if max_pages and page > max_pages:
                break
            time.sleep(self.rate_limit_delay)

        print(f"[ZU] Finished cataloging '{handle}': {len(products)} total cat products.")
        return products

    def _fetch_details(self, p):
        url = p.get('pdp_url')
        if not url:
            return p

        try:
            html = self.fetch_url(url, timeout=12)
            if not html:
                return p
        except Exception as e:
            p['fetch_error'] = str(e)
            return p

        soup = BeautifulSoup(html, 'html.parser')

        # Unit price
        up_span = soup.find('span', class_='unit-price')
        unit_price_val = None
        if up_span:
            m = re.search(r'(\d+[.,]\d+)', up_span.get_text())
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
                description_text = tab_text

            # Look strictly for composition section
            if any(k in tab_lower for k in ['ingrediente', 'composição']):
                m_ing = re.search(r'(?:Ingredientes|Composição):\s*(.*?)(?=(?:Constituintes\s+anal[íi]ticos|Aditivos|Energia|$))', tab_text, re.I | re.S)
                if m_ing and not ingredients_text:
                    cand = m_ing.group(1).strip()
                    # Must not be marketing copy
                    if not cand.startswith('Caraterísticas') and not cand.startswith('Descrição:'):
                        ingredients_text = cand

            # Look strictly for analytical constituents section
            m_nut = re.search(r'(?:Constituintes\s+anal[íi]ticos|Análise|Informação\s+nutricional):\s*(.*?)(?=(?:Aditivos|Energia|$))', tab_text, re.I | re.S)
            if m_nut and not nutrition_text:
                nutrition_text = m_nut.group(1).strip()
            elif any(k in tab_lower for k in ['constituintes analíticos', 'informação nutricional']) and not nutrition_text:
                # Only use tab if it contains actual analytical values (e.g. %)
                if '%' in tab_text and any(k in tab_lower for k in ['proteína', 'proteina', 'humidade', 'gordura']):
                    nutrition_text = tab_text

        # Fallback to body_html if available
        if not description_text and p.get('body_html'):
            description_text = BeautifulSoup(p['body_html'], 'html.parser').get_text(separator=' ', strip=True)

        if not ingredients_text and p.get('body_html'):
            b_soup = BeautifulSoup(p['body_html'], 'html.parser')
            b_text = b_soup.get_text(separator='\n', strip=True)
            m_ing = re.search(r'(?:Ingredientes|Composição):\s*(.*?)(?=(?:Constituintes|Aditivos|$))', b_text, re.I | re.S)
            if m_ing:
                cand = m_ing.group(1).strip()
                if not cand.startswith('Caraterísticas') and not cand.startswith('Descrição:'):
                    ingredients_text = cand

        # Final sanity check: if ingredients field somehow contains marketing description header, clear it
        if ingredients_text.startswith('Caraterísticas') or ingredients_text.startswith('Descrição:'):
            if not description_text:
                description_text = ingredients_text
            ingredients_text = ""

        # Clean up temporary field
        p.pop('body_html', None)

        p['unit_price_kg'] = unit_price_val
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

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from .base import BaseScraper

class ZooplusScraper(BaseScraper):
    """
    Scraper for Zooplus.pt (leading online pet specialist).
    Base URL: https://www.zooplus.pt
    Categories:
      - Wet food: /shop/gato/enlatados_gato
      - Dry food: /shop/gato/racao_gato
    """
    BASE_URL = 'https://www.zooplus.pt'
    WET_PATH = '/shop/gato/enlatados_gato'
    DRY_PATH = '/shop/gato/racao_gato'
    LITTER_PATH = '/shop/gato/areia_gatos'

    def _parse_weight_from_text(self, text):
        if not text:
            return None
        clean = text.replace('\xa0', ' ').lower()
        m_multi = re.search(r'(\d+)\s*(?:x|un(?:idader?s?)?)\s*(\d+(?:[.,]\d+)?)\s*(k?g)', clean)
        if m_multi:
            qty = float(m_multi.group(1))
            single = float(m_multi.group(2).replace(',', '.'))
            unit = m_multi.group(3)
            weight_g = qty * (single * 1000 if unit == 'kg' else single)
            return weight_g / 1000.0

        m_single = re.search(r'(\d+(?:[.,]\d+)?)\s*(k?g)', clean)
        if m_single:
            val = float(m_single.group(1).replace(',', '.'))
            unit = m_single.group(2)
            return val if unit == 'kg' else (val / 1000.0)

        return None

    def _get_catalog(self, path, max_pages=18):
        effective_max = max_pages if max_pages is not None else 18
        print(f"[Zooplus] Cataloging '{path}' (max_pages={effective_max})...")
        products = []
        seen_pids = set()
        page = 1

        while page <= effective_max:
            url = f"{self.BASE_URL}{path}?p={page}"
            try:
                html = self.fetch_url(url, timeout=15)
            except Exception as e:
                print(f"[Zooplus] Error fetching page {page}: {e}")
                break

            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')
            cards = soup.find_all(attrs={'data-zta': 'product-card'})
            if not cards:
                print(f"[Zooplus] No cards found on page {page}.")
                break

            new_cards_this_page = 0
            for c in cards:
                product_id = c.get('id')
                variant_id = c.get('data-variant-id')
                unique_card_id = f"{product_id}_{variant_id}" if (product_id and variant_id) else (variant_id or product_id)
                if not unique_card_id or unique_card_id in seen_pids:
                    continue
                seen_pids.add(unique_card_id)
                new_cards_this_page += 1

                # Name
                title_elem = c.find('span', attrs={'data-zta': 'product-link'}) or c.find(attrs={'data-zta': 'product-title'})
                name = title_elem.get_text(strip=True) if title_elem else ''

                # Link
                link_elem = (
                    c.find('a', attrs={'data-zta': 'product-link'}) or
                    c.find('a', attrs={'data-zta': 'product-info'}) or
                    c.find('a', attrs={'data-zta': 'product-image-anchor'}) or
                    c.find('a', href=True)
                )
                pdp_url = link_elem.get('href') if link_elem else None
                if pdp_url and pdp_url.startswith('/'):
                    pdp_url = self.BASE_URL + pdp_url

                # Append activeVariant if variant_id present
                if pdp_url and variant_id and 'activeVariant' not in pdp_url:
                    sep = '&' if '?' in pdp_url else '?'
                    pdp_url = f"{pdp_url}{sep}activeVariant={variant_id}"

                # Price
                price_val = None
                price_elem = c.find('span', class_=re.compile(r'PriceAmount')) or c.find('span', class_=re.compile(r'amount'))
                if price_elem:
                    m = re.search(r'(\d+[.,]\d+)', price_elem.get_text())
                    if m:
                        price_val = float(m.group(1).replace(',', '.'))
                elif c.get_text():
                    m = re.search(r'(\d+[.,]\d+)\s*€', c.get_text())
                    if m:
                        price_val = float(m.group(1).replace(',', '.'))

                # Unit price (€/kg or €/l)
                unit_price_val = None
                unit_price_l = None
                suffix_elem = c.find(attrs={'data-zta': 'reducedPriceSuffix'}) or c.find(class_=re.compile(r'note--suffix'))
                suffix_str = suffix_elem.get_text(strip=True) if suffix_elem else c.get_text()
                m_up_kg = re.search(r'(\d+[.,]\d+)\s*€\s*/\s*kg', suffix_str, re.I)
                if m_up_kg:
                    unit_price_val = float(m_up_kg.group(1).replace(',', '.'))
                m_up_l = re.search(r'(\d+[.,]\d+)\s*€\s*/\s*(?:l|lt|litros?)\b', suffix_str, re.I)
                if m_up_l:
                    unit_price_l = float(m_up_l.group(1).replace(',', '.'))

                # Fallback compute unit price
                if not unit_price_val and price_val:
                    weight_kg = self._parse_weight_from_text(name)
                    if weight_kg and weight_kg > 0:
                        unit_price_val = round(price_val / weight_kg, 2)

                products.append({
                    'pid': str(unique_card_id),
                    'name': name or f'Produto {unique_card_id}',
                    'brand': 'Desconhecida',
                    'price': price_val,
                    'unit_price_kg': unit_price_val,
                    'unit_price_l': unit_price_l,
                    'pack_size': '',
                    'pdp_url': pdp_url,
                    'retailer': 'Zooplus'
                })

            print(f"[Zooplus] Page {page}: found {len(cards)} cards (cataloged so far: {len(products)})")
            if page > 1 and new_cards_this_page == 0:
                print(f"[Zooplus] Page {page} yielded 0 new cards (catalog wraparound detected). Halting pagination.")
                break
            page += 1
            time.sleep(self.rate_limit_delay)

        print(f"[Zooplus] Finished cataloging '{path}': {len(products)} products.")
        return products

    def _parse_analytical_table(self, table, prod_name=''):
        """Extracts analytical constituents without flattening multi-recipe columns."""
        rows = table.find_all('tr')
        if not rows:
            return ''

        headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]

        # Check if multi-column recipe table
        if len(headers) > 2:
            col_names = headers[1:]
            selected_col = None
            p_name_l = prod_name.lower()
            for idx, col_name in enumerate(col_names, start=1):
                if col_name.lower() in p_name_l:
                    selected_col = idx
                    break

            if selected_col is not None:
                lines = [f'Receita: {headers[selected_col]}']
                for r in rows[1:]:
                    cells = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
                    if len(cells) > selected_col:
                        lines.append(f'{cells[0]}: {cells[selected_col]}')
                return '; '.join(lines)
            else:
                lines = ['Multi-recipe table:']
                for idx, col_name in enumerate(col_names, start=1):
                    col_vals = []
                    for r in rows[1:]:
                        cells = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
                        if len(cells) > idx:
                            col_vals.append(f'{cells[0]}: {cells[idx]}')
                    lines.append(f'[{col_name}] ' + ', '.join(col_vals))
                return '\n'.join(lines)
        else:
            # Single recipe column
            lines = []
            start_row = 1 if len(rows) > 1 and headers and any(k in headers[0].lower() for k in ['constituinte', 'anal']) else 0
            for r in rows[start_row:]:
                cells = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
                if len(cells) >= 2:
                    lines.append(f'{cells[0]}: {cells[1]}')
            return '; '.join(lines)

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

        # Brand from JSON-LD or URL
        brand = None
        for s in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(s.string)
                for item in data.get('@graph', []):
                    if item.get('@type') in ['ProductGroup', 'Product'] and item.get('brand'):
                        b = item.get('brand')
                        brand = b.get('name') if isinstance(b, dict) else b
                        break
                if brand:
                    break
            except Exception:
                pass

        if not brand and p.get('pdp_url'):
            CATEGORY_SLUGS = {'areia_aglomerante', 'areia_biodegradavel', 'areia_silica', 'areia_bentonita', 'areia_naoaglomerante_gato', 'areia_vegetal', 'outras_marcas'}
            m_parts = re.findall(r'/shop/gato/areia_gatos/([^/]+)(?:/([^/]+))?', p['pdp_url'])
            if m_parts:
                slug1, slug2 = m_parts[0]
                candidate = slug2 if slug1 in CATEGORY_SLUGS and slug2 and not slug2.isdigit() else slug1
                if candidate not in CATEGORY_SLUGS:
                    clean_brand = re.sub(r'_areia$', '', candidate).replace('_', ' ').title()
                    brand = clean_brand
            else:
                m_b = re.search(r'/shop/gato/(?:enlatados_gato|racao_gato)/([^/]+)/', p['pdp_url'])
                if m_b:
                    brand = m_b.group(1).replace('_', ' ').title()

        if not brand:
            KNOWN_LITTER_BRANDS = ["Cat's Best", "Tigerino", "Sanicat", "Biokat's", "Ever Clean", "KittyBay", "Benek", "Golden Grey", "Catsan", "Almo Nature", "Intersand"]
            for kb in KNOWN_LITTER_BRANDS:
                if kb.lower() in p.get('name', '').lower():
                    brand = kb
                    break

        if brand:
            p['brand'] = brand

        # Subtitle / Variant pack size (critical for cat litter: e.g. '10 l (6 kg)')
        subtitle_el = soup.find(attrs={'data-zta': 'ProductTitle__Subtitle'}) or soup.find(class_=re.compile(r'ProductTitle__Subtitle'))
        if subtitle_el:
            sub_text = subtitle_el.get_text(strip=True)
            if sub_text:
                p['pack_size'] = sub_text

        # SelectedArticleBox for unit price per liter / kg if either is missing
        if not p.get('unit_price_l') or not p.get('unit_price_kg'):
            box_el = soup.find(attrs={'data-zta': 'SelectedArticleBox'}) or soup.find(attrs={'data-zta': 'SelectedArticleBox__TopSection'})
            if box_el:
                box_text = box_el.get_text()
                if not p.get('unit_price_l'):
                    m_box_l = re.search(r'(\d+[.,]\d+)\s*€\s*/\s*(?:l|lt|litros?)\b', box_text, re.I)
                    if m_box_l:
                        p['unit_price_l'] = float(m_box_l.group(1).replace(',', '.'))
                if not p.get('unit_price_kg'):
                    m_box_kg = re.search(r'(\d+[.,]\d+)\s*€\s*/\s*kg\b', box_text, re.I)
                    if m_box_kg:
                        p['unit_price_kg'] = float(m_box_kg.group(1).replace(',', '.'))

        # Ingredients
        ing_el = soup.find(attrs={'data-zta': 'productIngredients'})
        ingredients_text = ing_el.get_text(separator=' ', strip=True) if ing_el else ""

        # Nutrition / Analytical Constituents table
        nutrition_text = ""
        nutri_td = soup.find(lambda e: e.name == 'td' and any(k in e.get_text().lower() for k in ['proteína', 'proteina']))
        if nutri_td:
            nutri_table = nutri_td.find_parent('table')
            if nutri_table:
                nutrition_text = self._parse_analytical_table(nutri_table, prod_name=p.get('name', ''))

        if not nutrition_text:
            nutri_el = soup.find(attrs={'data-zta': 'productAnalyticalConstituents'})
            if nutri_el:
                nutrition_text = nutri_el.get_text(separator=' ', strip=True)

        # Description
        desc_el = soup.find(attrs={'data-zta': 'productDescription'})
        description_text = desc_el.get_text(separator=' ', strip=True) if desc_el else ""

        p['ingredients'] = ingredients_text
        p['nutrition_raw'] = nutrition_text
        p['description'] = description_text
        return p

    def _enrich_with_details(self, products, max_workers=6):
        print(f"[Zooplus] Fetching details for {len(products)} products (concurrency: {max_workers})...")
        enriched = []
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_prod = {executor.submit(self._fetch_details, prod): prod for prod in products}
            for future in as_completed(future_to_prod):
                enriched.append(future.result())
                done += 1
                if done % 25 == 0 or done == len(products):
                    print(f"[Zooplus] Fetched details: {done}/{len(products)}")
        return enriched

    def scrape_wet(self, max_pages=None, max_workers=6):
        catalog = self._get_catalog(self.WET_PATH, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

    def scrape_dry(self, max_pages=None, max_workers=6):
        catalog = self._get_catalog(self.DRY_PATH, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

    def scrape_litter(self, max_pages=None, max_workers=6):
        catalog = self._get_catalog(self.LITTER_PATH, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

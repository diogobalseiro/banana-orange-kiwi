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

            for c in cards:
                pid = c.get('id') or c.get('data-variant-id')
                if not pid or pid in seen_pids:
                    continue
                seen_pids.add(pid)

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

                # Unit price (€/kg)
                unit_price_val = None
                suffix_elem = c.find(attrs={'data-zta': 'reducedPriceSuffix'}) or c.find(class_=re.compile(r'note--suffix'))
                suffix_str = suffix_elem.get_text(strip=True) if suffix_elem else c.get_text()
                m_up = re.search(r'(\d+[.,]\d+)\s*€\s*/\s*kg', suffix_str)
                if m_up:
                    unit_price_val = float(m_up.group(1).replace(',', '.'))

                # Fallback compute unit price
                if not unit_price_val and price_val:
                    weight_kg = self._parse_weight_from_text(name)
                    if weight_kg and weight_kg > 0:
                        unit_price_val = round(price_val / weight_kg, 2)

                products.append({
                    'pid': str(pid),
                    'name': name or f'Produto {pid}',
                    'brand': 'Desconhecida',
                    'price': price_val,
                    'unit_price_kg': unit_price_val,
                    'pack_size': '',
                    'pdp_url': pdp_url,
                    'retailer': 'Zooplus'
                })

            print(f"[Zooplus] Page {page}: found {len(cards)} cards (cataloged so far: {len(products)})")
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
            m_b = re.search(r'/shop/gato/(?:enlatados_gato|racao_gato)/([^/]+)/', p['pdp_url'])
            if m_b:
                brand = m_b.group(1).replace('_', ' ').title()

        if brand:
            p['brand'] = brand

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

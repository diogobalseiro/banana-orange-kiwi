import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from .base import BaseScraper

class ContinenteScraper(BaseScraper):
    BASE_URL = 'https://www.continente.pt'
    WET_CGID = 'animais-gato-comida-humida'
    DRY_CGID = 'animais-gato-racao-seca'

    def _get_catalog(self, cgid, max_pages=None):
        print(f"[Continente] Cataloging {cgid}...")
        products = []
        seen_pids = set()
        start = 0
        sz = 35
        page_count = 0

        while True:
            url = f"{self.BASE_URL}/on/demandware.store/Sites-continente-Site/default/Search-UpdateGrid?cgid={cgid}&pmin=0.01&start={start}&sz={sz}"
            try:
                html = self.fetch_url(url)
            except Exception as e:
                print(f"[Continente] Error at start={start}: {e}")
                break

            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')
            tiles = soup.find_all('div', class_='product')
            if not tiles:
                break

            for t in tiles:
                pid = t.get('data-pid')
                if not pid or pid in seen_pids:
                    continue
                seen_pids.add(pid)

                tile_div = t.find('div', class_='product-tile')
                impression_raw = tile_div.get('data-product-tile-impression') if tile_div else None
                impression = {}
                if impression_raw:
                    try:
                        impression = json.loads(impression_raw)
                    except Exception:
                        pass

                name = impression.get('name')
                brand = impression.get('brand')
                price = impression.get('price')

                link = t.find('a', class_='pwc-tile--header') or t.find('a', href=re.compile(r'/produto/'))
                if not name and link:
                    name = link.get_text(strip=True)
                pdp_url = link.get('href') if link else None
                if pdp_url and not pdp_url.startswith('http'):
                    pdp_url = self.BASE_URL + pdp_url

                unit_price_elem = t.find('span', class_='pwc-tile--price-secondary') or t.find('div', class_='pwc-tile--price-secondary')
                unit_price_str = unit_price_elem.get_text(strip=True) if unit_price_elem else ''
                
                unit_price_val = None
                m_up = re.search(r'(\d+[.,]\d+)\s*€\s*/\s*kg', unit_price_str.replace('\xa0', ' '))
                if m_up:
                    unit_price_val = float(m_up.group(1).replace(',', '.'))

                pack_elem = t.find('p', class_='pwc-tile--quantity') or t.find('span', class_='pwc-tile--quantity')
                pack_size = pack_elem.get_text(strip=True) if pack_elem else ''

                products.append({
                    'pid': pid,
                    'name': name or f'Produto {pid}',
                    'brand': brand or 'Desconhecida',
                    'price': price,
                    'unit_price_str': unit_price_str,
                    'unit_price_kg': unit_price_val,
                    'pack_size': pack_size,
                    'pdp_url': pdp_url
                })

            start += len(tiles)
            page_count += 1
            if max_pages and page_count >= max_pages:
                break
            time.sleep(self.rate_limit_delay)

        print(f"[Continente] Found {len(products)} products for {cgid}")
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
        ingredients_text = ""
        nutrition_text = ""
        description_text = ""

        for el in soup.find_all(['p', 'div', 'span']):
            t = el.get_text(strip=True)
            if t.startswith('Ingredientes:') and not ingredients_text:
                nxt = el.find_next_sibling()
                if nxt:
                    ingredients_text = nxt.get_text(strip=True, separator=' ')
            elif ('Informa' in t and 'Nutricional' in t and ':' in t) and not nutrition_text:
                nxt = el.find_next_sibling()
                if nxt:
                    nutrition_text = nxt.get_text(strip=True, separator=' ')
            elif t.startswith('Descrição:') and not description_text:
                nxt = el.find_next_sibling()
                if nxt:
                    description_text = nxt.get_text(strip=True, separator=' ')

        desc_wrap = soup.find('div', class_='ct-pdp--description-wrapper')
        if desc_wrap and (not ingredients_text or not nutrition_text):
            all_text = desc_wrap.get_text(separator='\n')
            if not ingredients_text:
                m_ing = re.search(r'Ingredientes:\s*\n(.*?)(?=\n[A-Z][a-z]+:|$)', all_text, re.DOTALL)
                if m_ing:
                    ingredients_text = m_ing.group(1).strip()
            if not nutrition_text:
                m_nut = re.search(r'Informaç.*?Nutricional:\s*\n(.*?)(?=\n[A-Z][a-z]+:|$)', all_text, re.DOTALL)
                if m_nut:
                    nutrition_text = m_nut.group(1).strip()

        p['ingredients'] = ingredients_text
        p['nutrition_raw'] = nutrition_text
        p['description'] = description_text
        return p

    def _enrich_with_details(self, products, max_workers=6):
        print(f"[Continente] Fetching details for {len(products)} products (concurrency: {max_workers})...")
        enriched = []
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_prod = {executor.submit(self._fetch_details, prod): prod for prod in products}
            for future in as_completed(future_to_prod):
                enriched.append(future.result())
                done += 1
                if done % 50 == 0 or done == len(products):
                    print(f"[Continente] Fetched details: {done}/{len(products)}")
        return enriched

    def scrape_wet(self, max_pages=None, max_workers=6):
        catalog = self._get_catalog(self.WET_CGID, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

    def scrape_dry(self, max_pages=None, max_workers=6):
        catalog = self._get_catalog(self.DRY_CGID, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

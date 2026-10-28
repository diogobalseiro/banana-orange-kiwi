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
    LITTER_CGID = 'animais-gato-absorventes'

    def _get_catalog(self, cgid, max_pages=None):
        print(f"[Continente] Cataloging {cgid}...")
        products = []
        seen_pids = set()
        start = 0
        sz = 35
        page_count = 0

        while True:
            if max_pages is not None and page_count >= max_pages:
                break

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

            new_pids_this_page = 0
            for t in tiles:
                pid = t.get('data-pid')
                if not pid or pid in seen_pids:
                    continue
                seen_pids.add(pid)
                new_pids_this_page += 1

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

                # DOM price fallback if impression JSON has no price
                if price is None:
                    price_elem = t.find('span', class_='pwc-tile--price-primary') or t.find('span', class_='js-product-price')
                    if price_elem:
                        m_p = re.search(r'(\d+(?:[.,]\d+)?)\s*€', price_elem.get_text())
                        if m_p:
                            try:
                                price = float(m_p.group(1).replace(',', '.'))
                            except ValueError:
                                pass

                link = t.find('a', class_='pwc-tile--header') or t.find('a', href=re.compile(r'/produto/'))
                if not name and link:
                    name = link.get_text(strip=True)
                pdp_url = link.get('href') if link else None
                if pdp_url and not pdp_url.startswith('http'):
                    pdp_url = self.BASE_URL + pdp_url

                unit_price_elem = t.find('span', class_='pwc-tile--price-secondary') or t.find('div', class_='pwc-tile--price-secondary')
                unit_price_str = unit_price_elem.get_text(strip=True) if unit_price_elem else ''
                
                unit_price_val = None
                unit_price_l = None
                cleaned_up_str = unit_price_str.replace('\xa0', ' ').replace('\u202f', ' ')
                
                m_up_kg = re.search(r'(\d+(?:[.,]\d+)?)\s*€\s*/\s*(?:kg|kgs|quilos?)\b', cleaned_up_str, re.I)
                if m_up_kg:
                    try:
                        unit_price_val = float(m_up_kg.group(1).replace(',', '.'))
                    except ValueError:
                        pass
                m_up_l = re.search(r'(\d+(?:[.,]\d+)?)\s*€\s*/\s*(?:l|lt|lts|litros?)\b', cleaned_up_str, re.I)
                if m_up_l:
                    try:
                        unit_price_l = float(m_up_l.group(1).replace(',', '.'))
                    except ValueError:
                        pass

                pack_elem = t.find('p', class_='pwc-tile--quantity') or t.find('span', class_='pwc-tile--quantity')
                pack_size = pack_elem.get_text(strip=True) if pack_elem else ''

                products.append({
                    'pid': pid,
                    'name': name or f'Produto {pid}',
                    'brand': brand or 'Desconhecida',
                    'price': price,
                    'unit_price_str': unit_price_str,
                    'unit_price_kg': unit_price_val,
                    'unit_price_l': unit_price_l,
                    'pack_size': pack_size,
                    'pdp_url': pdp_url,
                    'retailer': 'Continente'
                })

            start += sz
            page_count += 1
            if len(tiles) < sz or new_pids_this_page == 0:
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
        beneficios_text = ""

        # Scope search to description container to prevent matching whole page / footer elements
        desc_container = (
            soup.find('div', class_='ct-pdp--description-wrapper') or
            soup.find('div', class_='ct-pdp--description-container') or
            soup.find('div', class_='product-description') or
            soup.find('div', class_='tabContainer') or
            soup.find('main')
        )
        if not desc_container:
            desc_container = soup

        NEWSLETTER_TRAPS = ['As novidades mais frescas', 'Subscreva e descubra', 'campanhas exclusivas']

        # Look strictly for section headers (short text labels, not large parent wrappers)
        for el in desc_container.find_all(['p', 'span', 'strong', 'b', 'h2', 'h3', 'h4', 'h5']):
            t = el.get_text(strip=True).lower().rstrip(':')
            if len(t) > 50:
                continue

            # Support both 'ingredientes' and 'composição' (vital for cat litter)
            if (t.startswith('ingredientes') or t.startswith('composição') or t.startswith('composicao')) and not ingredients_text:
                nxt = el.find_next_sibling()
                if nxt and nxt.name != 'footer':
                    nxt_text = nxt.get_text(strip=True, separator=' ')
                    if not any(trap in nxt_text for trap in NEWSLETTER_TRAPS):
                        ingredients_text = nxt_text

            elif any(k in t for k in ['informação nutricional', 'informacao nutricional']) and not nutrition_text:
                nxt = el.find_next_sibling()
                if nxt and nxt.name != 'footer':
                    nxt_text = nxt.get_text(strip=True, separator=' ')
                    if not any(trap in nxt_text for trap in NEWSLETTER_TRAPS):
                        nutrition_text = nxt_text

            elif (t.startswith('descrição') or t.startswith('descricao')) and not description_text:
                nxt = el.find_next_sibling()
                if nxt and nxt.name != 'footer':
                    nxt_text = nxt.get_text(strip=True, separator=' ')
                    if not any(trap in nxt_text for trap in NEWSLETTER_TRAPS):
                        description_text = nxt_text

            elif (t.startswith('benefícios') or t.startswith('beneficios') or t.startswith('informação adicional')) and not beneficios_text:
                nxt = el.find_next_sibling()
                if nxt and nxt.name != 'footer':
                    nxt_text = nxt.get_text(strip=True, separator=' ')
                    if not any(trap in nxt_text for trap in NEWSLETTER_TRAPS):
                        beneficios_text = nxt_text

        # Combine description and benefits if available
        if beneficios_text:
            description_text = f"{description_text} {beneficios_text}".strip()

        desc_wrap = soup.find('div', class_='ct-pdp--description-wrapper')
        if desc_wrap and (not ingredients_text or not nutrition_text):
            all_text = desc_wrap.get_text(separator='\n')
            if not ingredients_text:
                m_ing = re.search(r'(?:Ingredientes|Composição):\s*\n(.*?)(?=\n[A-Z][a-z]+:|$)', all_text, re.DOTALL | re.I)
                if m_ing:
                    candidate = m_ing.group(1).strip()
                    if not any(trap in candidate for trap in NEWSLETTER_TRAPS):
                        ingredients_text = candidate
            if not nutrition_text:
                m_nut = re.search(r'Informaç.*?Nutricional:\s*\n(.*?)(?=\n[A-Z][a-z]+:|$)', all_text, re.DOTALL | re.I)
                if m_nut:
                    candidate = m_nut.group(1).strip()
                    if not any(trap in candidate for trap in NEWSLETTER_TRAPS):
                        nutrition_text = candidate

        # Discard any corrupted footer/newsletter text across all fields
        for trap in NEWSLETTER_TRAPS:
            if trap in nutrition_text:
                nutrition_text = ""
            if trap in ingredients_text:
                ingredients_text = ""
            if trap in description_text:
                description_text = ""

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

    def scrape_litter(self, max_pages=None, max_workers=6):
        catalog = self._get_catalog(self.LITTER_CGID, max_pages=max_pages)
        return self._enrich_with_details(catalog, max_workers=max_workers)

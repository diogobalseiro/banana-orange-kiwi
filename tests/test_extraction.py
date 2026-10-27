import os
import unittest
from bs4 import BeautifulSoup
from src.scrapers.continente import ContinenteScraper
from src.scrapers.zu import ZUScraper
from src.scrapers.zooplus import ZooplusScraper

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')

def load_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), 'r', encoding='utf-8') as f:
        return f.read()

class TestScraperExtraction(unittest.TestCase):
    def setUp(self):
        self.continente = ContinenteScraper()
        self.zu = ZUScraper()
        self.zooplus = ZooplusScraper()

    def test_continente_rejects_footer_newsletter_trap(self):
        """Continente extraction must reject footer/newsletter text and find valid sections."""
        html = load_fixture('continente_footer_trap.html')
        # Simulate _fetch_details with fixture HTML
        p = {'pdp_url': 'http://dummy.url'}
        # Patch fetch_url to return fixture
        self.continente.fetch_url = lambda url, **kwargs: html
        res = self.continente._fetch_details(p)

        self.assertNotIn('As novidades mais frescas', res.get('nutrition_raw', ''))
        self.assertIn('Proteína', res.get('nutrition_raw', ''))
        self.assertIn('vitela', res.get('ingredients', '').lower())

    def test_zu_rejects_description_as_composition(self):
        """ZU extraction must NOT classify marketing description copy as ingredients."""
        html = load_fixture('zu_description_trap.html')
        p = {'pdp_url': 'http://dummy.url', 'price': 0.85, 'name': 'Gourmet Gold Junior'}
        self.zu.fetch_url = lambda url, **kwargs: html
        res = self.zu._fetch_details(p)

        # Should not take marketing description as ingredients
        self.assertNotIn('uma suave e aveludada mousse', res.get('ingredients', '').lower())
        self.assertIn('uma suave e aveludada mousse', res.get('description', '').lower())

    def test_zu_valid_pdp_extraction(self):
        """ZU extracts separate composition, analytical constituents, and additives."""
        html = load_fixture('zu_valid_pdp.html')
        p = {'pdp_url': 'http://dummy.url', 'price': 5.0}
        self.zu.fetch_url = lambda url, **kwargs: html
        res = self.zu._fetch_details(p)

        self.assertIn('70% frango', res.get('ingredients', ''))
        self.assertIn('Proteína', res.get('nutrition_raw', ''))
        self.assertNotIn('Proteína', res.get('ingredients', ''))

    def test_zooplus_single_recipe_table(self):
        """Zooplus extracts single analytical table cleanly."""
        html = load_fixture('zooplus_single_recipe.html')
        p = {'pdp_url': 'http://dummy.url'}
        self.zooplus.fetch_url = lambda url, **kwargs: html
        res = self.zooplus._fetch_details(p)

        self.assertIn('Proteína', res.get('nutrition_raw', ''))
        self.assertIn('10.6', res.get('nutrition_raw', ''))

    def test_zooplus_multi_recipe_table_no_flattening(self):
        """Zooplus should not blindly flatten multiple recipe columns into one single row of values."""
        html = load_fixture('zooplus_multi_recipe.html')
        # Test 1: Ambiguous product name (multipack)
        p_amb = {'pdp_url': 'http://dummy.url', 'name': 'Feringa Pure Meat 6 x 200 g'}
        self.zooplus.fetch_url = lambda url, **kwargs: html
        res_amb = self.zooplus._fetch_details(p_amb)
        self.assertIn('Multi-recipe table:', res_amb.get('nutrition_raw', ''))
        self.assertIn('[Frango]', res_amb.get('nutrition_raw', ''))
        self.assertIn('[Salmão]', res_amb.get('nutrition_raw', ''))

        # Test 2: Specific recipe product name
        p_spec = {'pdp_url': 'http://dummy.url', 'name': 'Feringa Frango com abóbora 200 g'}
        res_spec = self.zooplus._fetch_details(p_spec)
        self.assertIn('Receita: Frango', res_spec.get('nutrition_raw', ''))
        self.assertIn('10.8 %', res_spec.get('nutrition_raw', ''))
        self.assertNotIn('Multi-recipe table:', res_spec.get('nutrition_raw', ''))

    def test_base_scraper_raises_explicit_fetch_error(self):
        """BaseScraper raises ScraperFetchError on exhausted failures."""
        from src.scrapers.base import ScraperFetchError
        # Test with invalid url/port
        with self.assertRaises(ScraperFetchError):
            self.continente.fetch_url('http://127.0.0.1:1/nonexistent', timeout=0.1, max_retries=1)

if __name__ == '__main__':
    unittest.main()

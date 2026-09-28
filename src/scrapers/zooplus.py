from .base import BaseScraper

class ZooplusScraper(BaseScraper):
    """
    Scraper template for Zooplus.pt.
    Base URL: https://www.zooplus.pt
    Categories:
      - Wet food: /shop/gato/comida_humida
      - Dry food: /shop/gato/racao_seca
    """
    BASE_URL = 'https://www.zooplus.pt'

    def scrape_wet(self):
        raise NotImplementedError("Zooplus.pt wet food scraper will be enabled in next release.")

    def scrape_dry(self):
        raise NotImplementedError("Zooplus.pt dry food scraper will be enabled in next release.")

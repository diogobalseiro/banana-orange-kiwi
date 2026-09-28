from .base import BaseScraper

class ZUScraper(BaseScraper):
    """
    Scraper template for ZU.pt (Sonae Pet specialist).
    Base URL: https://www.zu.pt
    Categories:
      - Wet food: /gato/alimentacao/comida-humida/
      - Dry food: /gato/alimentacao/comida-seca/
    """
    BASE_URL = 'https://www.zu.pt'

    def scrape_wet(self):
        raise NotImplementedError("ZU.pt wet food scraper will be enabled in next release.")

    def scrape_dry(self):
        raise NotImplementedError("ZU.pt dry food scraper will be enabled in next release.")

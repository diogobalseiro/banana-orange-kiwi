# Adding New Retailers (ZU.pt, Zooplus.pt, etc.)

To add a new pet food retailer to the ranking pipeline, follow this checklist:

## 1. Subclass `BaseScraper`
Create a new file in `src/scrapers/<retailer>.py`:

```python
from .base import BaseScraper

class NewRetailerScraper(BaseScraper):
    BASE_URL = 'https://www.example.pt'

    def scrape_wet(self, max_pages=None):
        # 1. Fetch catalog listing
        # 2. Extract PDP links, prices, unit prices
        # 3. Fetch each PDP for ingredients and analytical components
        # 4. Return list of product dictionaries
        pass

    def scrape_dry(self, max_pages=None):
        pass
```

## 2. Product Dictionary Schema
Each product returned by `scrape_wet()` and `scrape_dry()` must match this schema:

```python
{
    'pid': 'unique_product_id_or_sku',
    'name': 'Full Product Name',
    'brand': 'Brand Name',
    'price': 2.49,              # Total price (float or None)
    'unit_price_kg': 12.45,      # Price per kg (float or None)
    'pack_size': '4 x 85g',      # Raw pack size string
    'pdp_url': 'https://...',    # Product detail page URL
    'ingredients': 'Frango (50%), caldo de galinha...',
    'nutrition_raw': 'Proteína bruta: 12%, Gordura bruta: 6%...',
    'description': 'Alimento completo para gatinhos...'
}
```

## 3. Register in `refresh.py`
Import your scraper in `refresh.py` and add it to the CLI `--retailer` argument choices:

```python
from src.scrapers.zu import ZUScraper

if args.retailer == 'zu':
    scraper = ZUScraper()
```

## 4. Run & Test
Run a test run with a limited page count:
```bash
python3 refresh.py --retailer zu --type wet --max-pages 1
```
Verify that `data/zu_wet.json` and `data/zu_wet_full.json` are created correctly.

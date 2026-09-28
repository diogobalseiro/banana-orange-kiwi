---
name: cat-food-dashboard
description: >-
  Use this skill to inspect, refresh, or expand cat food rankings and dashboards (wet and dry).
  Guides data scraping, biological quality scoring, and building the unified GitHub Pages dashboard.
---

# Cat Food Ranking & Dashboard Skill

This skill provides the end-to-end workflow to audit cat food (wet pouches/cans and dry kibble) across Portuguese retailers (Continente, and expandable to ZU.pt / Zooplus.pt), score them according to feline obligate carnivore biological criteria, and build the interactive GitHub Pages dashboard.

---

## 1. Quick Reference Commands

### Refresh Pipeline
To refresh data and regenerate `index.html`:

```bash
# Refresh all (Wet + Dry for Continente)
python3 refresh.py --retailer continente --type all

# Refresh wet food only
python3 refresh.py --retailer continente --type wet

# Refresh dry food only
python3 refresh.py --retailer continente --type dry

# Re-score and re-build HTML without scraping
python3 refresh.py --skip-scrape
```

Alternatively, run the convenience shell script:
```bash
./.agents/skills/cat-food-dashboard/scripts/refresh.sh
```

---

## 2. Directory Architecture

- **`src/scrapers/`**: Scraper modules inheriting from `BaseScraper`.
  - `continente.py`: Continente catalog grid pagination and PDP product detail extraction.
  - `zu.py`: Scraper template for ZU.pt.
  - `zooplus.py`: Scraper template for Zooplus.pt.
- **`src/scoring/`**: Feline biological scoring engines.
  - `wet_scorer.py`: Analyzes wet food (meat %, absence of sugar/grains, DMB protein, complete vs complementary).
  - `dry_scorer.py`: Analyzes dry kibble (1st ingredient, grain-free, corn-gluten, colorants, protein, fat, carbohydrates NFE).
- **`src/builder/`**:
  - `build_site.py`: Injects minified JSON datasets into `index.html` (single-page app with dual-mode switch).
- **`data/`**: Stores raw, full, and minified JSON datasets and CSV exports.
- **`index.html`**: The unified dashboard published to GitHub Pages.

---

## 3. Workflows

### Workflow A: Periodic Data Refresh
1. Run `python3 refresh.py --retailer continente --type all`.
2. Inspect the output summary (number of wet and dry products cataloged).
3. Test `index.html` by opening it in a browser.
4. Commit and push changes:
   ```bash
   git add data/ index.html
   git commit -m "chore: refresh cat food catalog data"
   git push origin main
   ```

### Workflow B: Adding a New Retailer (e.g. ZU or Zooplus)
1. Open `src/scrapers/zu.py` (or `zooplus.py`).
2. Implement `scrape_wet()` and `scrape_dry()` to yield dictionaries with keys:
   `pid`, `name`, `brand`, `price`, `unit_price_kg`, `pack_size`, `pdp_url`, `ingredients`, `nutrition_raw`, `description`.
3. Test extraction with a small batch (`max_pages=1`).
4. See [references/adding_retailers.md](./references/adding_retailers.md) for detailed guidelines.

### Workflow C: Modifying Scoring Rules
1. Refer to [references/scoring_criteria.md](./references/scoring_criteria.md).
2. Adjust point weights or penalties in `src/scoring/wet_scorer.py` or `src/scoring/dry_scorer.py`.
3. Run `python3 refresh.py --skip-scrape` to immediately recalculate all scores and update the dashboard.

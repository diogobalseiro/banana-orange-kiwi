# 🐱 Cat Food Biological Ranking & Dashboard (Continente, ZU & Zooplus)

An interactive dashboard and biological/nutritional auditing engine for cat food (wet pouches/cans and dry kibble) across Portuguese pet food retailers (**Continente**, **ZU.pt**, and **Zooplus.pt**), specifically tailored to feline obligate carnivore dietary requirements and growing kittens.

🌐 **Live Dashboard**: [https://diogobalseiro.github.io/banana-orange-kiwi/](https://diogobalseiro.github.io/banana-orange-kiwi/)

---

## 🌟 Dashboard Features

- **Multi-Retailer Unified Catalog**:
  - Compares and audits products across **Continente**, **ZU.pt**, and **Zooplus.pt** in one interface with instant store-level filtering or cross-market comparison.
- **Dual-Mode Category Architecture**:
  - 🥫 **Wet Food (Comida Húmida)**: Audits 750+ wet food items focusing on named animal meat percentages, absence of added sugars/grains, proper hydration, and clear distinction between **Complete** and **Complementary** food.
  - 🥣 **Dry Kibble (Ração Seca)**: Audits 590+ dry formulas evaluating the 1st ingredient, crude protein, growth fat for kittens, estimated carbohydrates (NFE), and absence of corn gluten and artificial dyes.
- **Dedicated Kitten Filter (🍼 Júnior / Kitten)**:
  - Highlights calorie-dense, high-protein, and high-fat options formulated for rapid growth. Alerts against using complementary wet food or adult sterilised kibble as sole diets.
- **Value-for-Money Ratio (Q/P)**:
  - Calculates a normalized value ratio (`Score / €/kg`) to spotlight the highest-quality budget-friendly products on the market.

---

## 🚀 How to Run & Refresh Data Locally

### Prerequisites
```bash
pip install -r requirements.txt
```

### Refreshing Catalog Data
To scrape live retailer catalogs, parse ingredients, calculate biological quality scores, and rebuild `index.html`:

```bash
# Refresh all retailers (Continente, ZU, Zooplus)
python3 refresh.py --retailer all --type all

# Refresh specific retailer
python3 refresh.py --retailer continente --type all
python3 refresh.py --retailer zu --type all
python3 refresh.py --retailer zooplus --type all

# Refresh specific category (wet or dry)
python3 refresh.py --retailer zu --type wet

# Diagnostic run with limited pagination (requires --allow-partial to publish)
python3 refresh.py --retailer zooplus --type dry --max-pages 4 --allow-partial

# Recalculate scores and rebuild index.html from local cache (preserves original retrieval dates)
python3 refresh.py --skip-scrape
```

---

## 🛡️ Reliability & Evidence Architecture

The dashboard implements the Pareto Reliability Model:

1. **Zero Nutrient Imputation Policy**:
   - The parser extracts declared analytical constituents (protein, fat, fibre, ash, moisture) without assuming default values.
   - Missing declared moisture or analytical values produces unavailable carbohydrate/dry-matter estimates rather than artificial precision.

2. **Honest Uncertainty & Ranking Eligibility**:
   - Products require complete composition and verified core macronutrients to enter ranked leaderboards.
   - Products with missing declarations or complementary classification remain visible in catalog searches with an explicit `Unranked` status and transparent diagnostics explaining missing inputs.

3. **Reconciled Product Formulations (`data/product_matches.json`)**:
   - Cross-retailer identical recipes (e.g. Purina Gourmet Gold varieties across Continente and ZU) share identical nutritional assessments derived from verified manufacturer declarations.
   - Retailer-specific prices, pack sizes, and value ratios remain independent.

4. **Publication Quality Gates & Generation Manifests**:
   - File-based mutex lock (`.refresh.lock`) serializes refresh runs and prevents concurrent write corruption.
   - Candidate datasets are evaluated against the active baseline: zero counts, >30% drops, or >40% field loss are rejected and logged to `last_rejected_candidate.json`.
   - The active manifest (`data/manifest.json`) and `index.html` are swapped atomically. In the event of a scrape failure, previous accepted snapshots are retained and displayed with freshness notices.

5. **Limitations**:
   - Scores represent an algorithmic biological heuristic based on declared commercial pet food labels, not a certified clinical or laboratory feed analysis.

---

## 🤖 Antigravity Personal Skill

This repository includes a personal Antigravity skill located at `.agents/skills/cat-food-dashboard/`.

When opened in Antigravity, the assistant automatically knows how to:
- Execute periodic catalog refresh routines on demand;
- Tune biological scoring criteria and penalty thresholds;
- Scaffold and test new retailer scrapers (such as ZU.pt or Zooplus.pt).

---

## 🌐 GitHub Pages Deployment

The dashboard is generated as a standalone single-page application inside `index.html`.

### Enabling GitHub Pages:
1. In the repository settings on GitHub ([banana-orange-kiwi/settings/pages](https://github.com/diogobalseiro/banana-orange-kiwi/settings/pages)):
2. Under **Build and deployment > Source**, select:
   - **Deploy from a branch** (Branch: `main`, folder: `/ (root)`), **OR**
   - **GitHub Actions** (to use `.github/workflows/deploy.yml`).
3. Your dashboard will be live at:
   `https://diogobalseiro.github.io/banana-orange-kiwi/`

### Running a Catalog Refresh on GitHub:
You can trigger a full catalog scrape and dashboard rebuild directly from GitHub at any time without running code on your machine:
1. Go to the **Actions** tab in your repository.
2. Select **Refresh Cat Food Catalog** in the left sidebar.
3. Click **Run workflow** (and choose `all`, `wet`, or `dry`).
4. GitHub Actions will scrape Continente, re-score products, rebuild `index.html`, and commit the updated data automatically.

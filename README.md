# 🐱 Cat Food Biological Ranking & Dashboard (Continente)

An interactive dashboard and biological/nutritional auditing engine for cat food (wet pouches/cans and dry kibble), specifically tailored to feline obligate carnivore dietary requirements and growing kittens.

🌐 **Live Dashboard**: [https://diogobalseiro.github.io/banana-orange-kiwi/](https://diogobalseiro.github.io/banana-orange-kiwi/)

---

## 🌟 Dashboard Features

- **Unified Dual-Mode Architecture**:
  - 🥫 **Wet Food (Comida Húmida)**: Audits 295 wet food items focusing on named animal meat percentages, absence of added sugars/grains, proper hydration, and clear distinction between **Complete** and **Complementary** food.
  - 🥣 **Dry Kibble (Ração Seca)**: Audits 246 dry formulas evaluating the 1st ingredient, crude protein, growth fat for kittens, estimated carbohydrates (NFE), and absence of corn gluten and artificial dyes.
  - *Datasets are strictly isolated* — switching categories seamlessly updates the KPI cards, relevant nutritional columns, and specialized filter controls without mixing products.
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
To scrape Continente's live catalog, parse ingredients, calculate biological quality scores, and rebuild `index.html`:

```bash
# Full refresh (Wet + Dry food)
python3 refresh.py --retailer continente --type all

# Refresh wet food only
python3 refresh.py --retailer continente --type wet

# Refresh dry food only
python3 refresh.py --retailer continente --type dry

# Recalculate scores and rebuild index.html from local cache (instant)
python3 refresh.py --skip-scrape
```

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

# 🐱 Ranking & Auditoria de Alimentação para Gatos (Continente)

Painel interativo e motor de auditoria nutricional e biológica para comida de gato (húmida e seca), focado nas necessidades estritas de carnívoros obrigatórios e gatinhos em crescimento.

🌐 **Dashboard Online**: [https://diogobalseiro.github.io/banana-orange-kiwi/](https://diogobalseiro.github.io/banana-orange-kiwi/)

---

## 🌟 Funcionalidades do Dashboard

- **Visão Unificada com Modo Duplo**:
  - 🥫 **Comida Húmida**: Avaliação de 295 saquetas e latas com foco em carne nominada, carência de açúcares/cereais, hidratação e distinção entre alimento **Completo** vs **Complementar**.
  - 🥣 **Comida Seca (Ração)**: Auditoria de 246 rações com análise do 1º ingrediente, teor de proteína bruta, matéria gorda para gatinhos, estimativa de hidratos de carbono (NFE), ausência de glúten de milho e corantes artificiais.
  - *As listas nunca são misturadas* — a troca de aba recalcula instantaneamente os cartões de KPI, colunas relevantes e filtros específicos.
- **Filtro Especial de Gatinhos (🍼 Júnior / Kitten)**:
  - Destaca opções ricas em calorias, proteína e gordura de crescimento, alertando contra o uso de alimentos complementares ou fórmulas para adultos esterilizados.
- **Rácio Qualidade / Preço**:
  - Pontuação ponderada pelo preço por quilograma (`Pontuação / €/kg`) para identificar as melhores pechinchas do mercado.

---

## 🚀 Como Executar e Atualizar os Dados

### Pré-requisitos
```bash
pip install -r requirements.txt
```

### Atualização Periódica de Dados
Para raspar o catálogo do Continente, analisar ingredientes, recalcular pontuações e reconstruir o dashboard `index.html`:

```bash
# Atualização completa (Húmida + Seca)
python3 refresh.py --retailer continente --type all

# Apenas comida húmida
python3 refresh.py --retailer continente --type wet

# Apenas comida seca
python3 refresh.py --retailer continente --type dry

# Recalcular pontuações e reconstruir HTML sem raspar de novo
python3 refresh.py --skip-scrape
```

---

## 🤖 Skill do Antigravity

Este repositório inclui a skill pessoal **`cat-food-dashboard`** configurada em `.agents/skills/cat-food-dashboard/`.

Ao abrir este repositório no Antigravity, o assistente pode automaticamente:
- Executar rotinas de refresh sob pedido (`"atualiza o catálogo do continente"`);
- Ajustar os critérios de pontuação nutricional;
- Implementar e testar novos scrapers (como ZU.pt ou Zooplus.pt).

---

## 🌐 Publicação no GitHub Pages

O site é gerado como uma aplicação estática autónoma no ficheiro `index.html`.

### Configuração no GitHub:
1. No repositório [diogobalseiro/banana-orange-kiwi](https://github.com/diogobalseiro/banana-orange-kiwi), vá a **Settings** > **Pages**.
2. Sob **Build and deployment**:
   - **Source**: Selecione `Deploy from a branch` (Branch: `main`, pasta: `/ (root)`), **OU** selecione `GitHub Actions` para usar o workflow automático incluído em `.github/workflows/deploy.yml`.
3. O painel ficará acessível em:
   `https://diogobalseiro.github.io/banana-orange-kiwi/`

### Atualizações Automáticas Semanais:
O repositório inclui um GitHub Action (`.github/workflows/scheduled_refresh.yml`) configurado para rodar todas as segundas-feiras às 05:00 UTC, verificando novos produtos e preços automaticamente.

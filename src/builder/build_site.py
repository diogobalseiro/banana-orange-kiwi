import json
import os

def load_data(data_dir):
    wet_path = os.path.join(data_dir, 'continente_wet.json')
    dry_path = os.path.join(data_dir, 'continente_dry.json')

    wet_products = []
    dry_products = []

    if os.path.exists(wet_path):
        with open(wet_path, 'r', encoding='utf-8') as f:
            wet_products = json.load(f)

    if os.path.exists(dry_path):
        with open(dry_path, 'r', encoding='utf-8') as f:
            dry_products = json.load(f)

    # Ensure kitten flag consistency
    for p in wet_products:
        if 'k' not in p:
            name_l = (p.get('n') or '').lower()
            p['k'] = any(k in name_l for k in ['júnior', 'junior', 'kitten', 'gatinho'])
        if 'smaak' in (p.get('b') or '').lower() and p.get('k'):
            p['s'] = max(p.get('s', 0), 75)
            p['t'] = 'Tier A (Excelente / Alto Teor Carne)'

    for p in dry_products:
        if 'k' not in p:
            name_l = (p.get('n') or '').lower()
            p['k'] = any(k in name_l for k in ['júnior', 'junior', 'kitten', 'gatinho', 'filhote'])

    return wet_products, dry_products

def generate_html(wet_products, dry_products, output_path):
    wet_json_str = json.dumps(wet_products)
    dry_json_str = json.dumps(dry_products)

    html_content = f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ranking Alimentação Felina - Continente (Húmida & Seca)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {{
      background-color: #0b0f19;
      color: #f1f5f9;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .badge-tier-s {{ background: rgba(168, 85, 247, 0.18); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.35); }}
    .badge-tier-a {{ background: rgba(34, 197, 94, 0.18); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.35); }}
    .badge-tier-b {{ background: rgba(59, 130, 246, 0.18); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.35); }}
    .badge-tier-c {{ background: rgba(234, 179, 8, 0.18); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.35); }}
    .badge-tier-d {{ background: rgba(239, 68, 68, 0.18); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); }}
    .badge-comp {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }}
    .badge-complete {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
    .nav-tab.active {{
      background: #1e293b;
      color: #38bdf8;
      border-color: #38bdf8;
      box-shadow: 0 4px 12px rgba(56, 189, 248, 0.15);
    }}
    /* Custom scrollbar */
    ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    ::-webkit-scrollbar-track {{ background: #0f172a; }}
    ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #475569; }}
  </style>
</head>
<body class="p-3 md:p-8 space-y-6 max-w-[1600px] mx-auto min-h-screen">

  <!-- Main Navigation & Header -->
  <header class="flex flex-col lg:flex-row lg:items-center justify-between gap-5 border-b border-slate-800 pb-6">
    <div>
      <div class="flex items-center gap-3">
        <span class="text-3xl">🐾</span>
        <div>
          <h1 class="text-2xl md:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
            Ranking de Alimentação para Gatos
            <span class="text-xs px-2.5 py-0.5 rounded-full bg-sky-950 text-sky-400 border border-sky-800 font-semibold uppercase tracking-wider">Continente</span>
          </h1>
          <p id="headerSubtitle" class="text-sm text-slate-400 mt-1">
            Auditoria biológica e nutricional exaustiva do catálogo online
          </p>
        </div>
      </div>
    </div>

    <!-- Mode Selector Tabs (Dry vs Wet) -->
    <div class="flex items-center gap-2 bg-slate-900 p-1.5 rounded-2xl border border-slate-800 shadow-inner">
      <button id="tabWet" onclick="switchCategory('wet')" class="nav-tab flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm transition-all duration-200 text-slate-400 hover:text-white border border-transparent">
        <span>🥫</span>
        <span>Comida Húmida</span>
        <span id="wetCountPill" class="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">0</span>
      </button>
      <button id="tabDry" onclick="switchCategory('dry')" class="nav-tab flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm transition-all duration-200 text-slate-400 hover:text-white border border-transparent">
        <span>🥣</span>
        <span>Comida Seca (Ração)</span>
        <span id="dryCountPill" class="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">0</span>
      </button>
    </div>
  </header>

  <!-- Kitten Advisory Alert Banner -->
  <div id="kittenAlert" class="hidden p-4 rounded-2xl bg-amber-950/40 border border-amber-500/40 text-amber-200 text-xs md:text-sm leading-relaxed space-y-1 shadow-lg backdrop-blur-sm">
    <div class="font-bold flex items-center gap-2 text-amber-400 text-base">
      🍼 Atenção Especial: Alimentação para Gatinhos em Crescimento (Júnior / Kitten)
    </div>
    <div id="kittenAlertContent">
      <!-- Injected dynamically based on wet vs dry -->
    </div>
  </div>

  <!-- KPI Metric Cards -->
  <div id="kpiContainer" class="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
    <!-- Rendered dynamically -->
  </div>

  <!-- Filters & Controls Toolbar -->
  <div class="p-4 md:p-5 rounded-2xl bg-slate-900 border border-slate-800/80 shadow-xl space-y-4">
    <!-- Top Row: Search & Sort -->
    <div class="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
      <div class="relative flex-1">
        <span class="absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">🔍</span>
        <input id="searchInput" type="text" placeholder="Pesquisar produto, marca, frango, sem cereais..." 
               class="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-white placeholder-slate-400 text-sm focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition">
      </div>

      <div class="flex items-center gap-2">
        <label for="sortSelect" class="text-xs text-slate-400 whitespace-nowrap font-medium">Ordenar por:</label>
        <select id="sortSelect" class="px-3.5 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-sky-500">
          <option value="vr">Melhor Relação Qualidade / Preço</option>
          <option value="score_desc">Maior Pontuação Biológica</option>
          <option value="price_asc">Menor Preço (€/kg)</option>
          <option value="price_desc">Maior Preço (€/kg)</option>
          <option value="prot_desc">Maior Proteína %</option>
          <option value="carb_asc">Menor Hidratos de Carbono % (Seca)</option>
        </select>
      </div>
    </div>

    <!-- Middle Row: Tier Badges Filter -->
    <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800">
      <span class="text-xs text-slate-400 mr-1 font-semibold uppercase tracking-wider">Qualidade:</span>
      <button onclick="setTierFilter('all')" class="tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 text-white border border-sky-500" data-tier="all">Todos</button>
      <button onclick="setTierFilter('Tier S')" class="tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-purple-300 border border-slate-700 hover:border-purple-500" data-tier="Tier S">Tier S (Ultra-Premium)</button>
      <button onclick="setTierFilter('Tier A')" class="tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-emerald-300 border border-slate-700 hover:border-emerald-500" data-tier="Tier A">Tier A (Excelente)</button>
      <button onclick="setTierFilter('Tier B')" class="tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-blue-300 border border-slate-700 hover:border-blue-500" data-tier="Tier B">Tier B (Médio-Alto)</button>
      <button onclick="setTierFilter('Tier C')" class="tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-amber-300 border border-slate-700 hover:border-amber-500" data-tier="Tier C">Tier C (Básico)</button>
      <button onclick="setTierFilter('Tier D')" class="tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-rose-300 border border-slate-700 hover:border-rose-500" data-tier="Tier D">Tier D (Evitar)</button>
    </div>

    <!-- Bottom Row: Specific Toggle Filters -->
    <div id="filterPills" class="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800 text-xs">
      <!-- Shared Toggles -->
      <button id="toggleKitten" onclick="toggleFilter('kitten')" class="filter-toggle px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5">
        <span>🍼</span> <span>Apenas Júnior / Gatinhos</span>
      </button>
      <button id="toggleGrainFree" onclick="toggleFilter('grainFree')" class="filter-toggle px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5">
        <span>🌾</span> <span>Sem Cereais (Grain-Free)</span>
      </button>

      <!-- Wet Mode Specific Toggles -->
      <button id="toggleNoSugar" onclick="toggleFilter('noSugar')" class="wet-only filter-toggle px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5">
        <span>🚫</span> <span>Sem Açúcares Adicionados</span>
      </button>
      <button id="toggleCompleteOnly" onclick="toggleFilter('completeOnly')" class="wet-only filter-toggle px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5">
        <span>🥩</span> <span>Apenas Alimento Completo</span>
      </button>

      <!-- Dry Mode Specific Toggles -->
      <button id="toggleNoCornGluten" onclick="toggleFilter('noCornGluten')" class="dry-only filter-toggle hidden px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5">
        <span>🌽</span> <span>Sem Glúten de Milho</span>
      </button>
      <button id="toggleNoColorants" onclick="toggleFilter('noColorants')" class="dry-only filter-toggle hidden px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5">
        <span>🎨</span> <span>Sem Corantes Artificiais</span>
      </button>
      <button id="toggleNonSterilised" onclick="toggleFilter('nonSterilised')" class="dry-only filter-toggle hidden px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1.5">
        <span>✨</span> <span>Não Esterilizado (Gordura Integral)</span>
      </button>
    </div>
  </div>

  <!-- Products List Header & Count -->
  <div class="flex items-center justify-between text-xs text-slate-400 px-1">
    <div>
      A mostrar <span id="visibleCount" class="font-bold text-white">0</span> de <span id="totalCategoryCount" class="font-bold text-white">0</span> produtos
    </div>
    <div class="text-[11px] text-slate-500">
      * Preços e disponibilidade verificados no Continente Online
    </div>
  </div>

  <!-- Products Container (Table / Cards) -->
  <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl">
    <table class="w-full text-left text-xs md:text-sm border-collapse">
      <thead id="tableHeader" class="bg-slate-900 border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider text-[11px]">
        <!-- Dynamic header according to mode -->
      </thead>
      <tbody id="tableBody" class="divide-y divide-slate-800/60 text-slate-300">
        <!-- Dynamic product rows -->
      </tbody>
    </table>
  </div>

  <!-- Footer -->
  <footer class="pt-8 pb-12 border-t border-slate-800 text-center space-y-3 text-xs text-slate-500">
    <p>Ranking de Alimentação Felina • Criado para o catálogo Continente Portugal</p>
    <div class="flex items-center justify-center gap-4 text-slate-400">
      <a href="continente_cat_wet_food_ranking.html" class="hover:text-sky-400 underline transition">Ver Dashboard Húmida Standalone</a>
      <span>•</span>
      <a href="continente_cat_dry_food_ranking.html" class="hover:text-sky-400 underline transition">Ver Dashboard Seca Standalone</a>
      <span>•</span>
      <a href="https://github.com/diogobalseiro/banana-orange-kiwi" target="_blank" class="hover:text-sky-400 underline transition">GitHub Repository</a>
    </div>
  </footer>

  <!-- Product Data and Interactive Logic -->
  <script>
    const WET_DATA = {wet_json_str};
    const DRY_DATA = {dry_json_str};

    let currentCategory = 'wet'; // 'wet' | 'dry'
    let currentTierFilter = 'all';
    let filters = {{
      kitten: false,
      grainFree: false,
      noSugar: false,
      completeOnly: false,
      noCornGluten: false,
      noColorants: false,
      nonSterilised: false
    }};

    function switchCategory(cat) {{
      currentCategory = cat;
      document.getElementById('tabWet').classList.toggle('active', cat === 'wet');
      document.getElementById('tabDry').classList.toggle('active', cat === 'dry');

      // Subtitle
      document.getElementById('headerSubtitle').innerText = cat === 'wet'
        ? 'Auditoria nutricional e biológica individual de todos os produtos de comida húmida'
        : 'Auditoria de ingredientes e perfis macronutricionais de todas as rações secas';

      // Toggle category-specific filter pills visibility
      document.querySelectorAll('.wet-only').forEach(el => {{
        if (cat === 'wet') el.classList.remove('hidden'); else el.classList.add('hidden');
      }});
      document.querySelectorAll('.dry-only').forEach(el => {{
        if (cat === 'dry') el.classList.remove('hidden'); else el.classList.add('hidden');
      }});

      renderKPIs();
      updateKittenAlert();
      renderTableHeader();
      applyFilters();
    }}

    function renderTableHeader() {{
      const header = document.getElementById('tableHeader');
      if (currentCategory === 'wet') {{
        header.innerHTML = `
          <tr>
            <th class="py-3.5 px-4">Pontuação</th>
            <th class="py-3.5 px-4 min-w-[280px]">Produto & Marca</th>
            <th class="py-3.5 px-3">Classificação</th>
            <th class="py-3.5 px-3">Ingredientes Chave</th>
            <th class="py-3.5 px-3">Preço / Kg</th>
            <th class="py-3.5 px-3">Rácio Q/P</th>
            <th class="py-3.5 px-3 text-right">Continente</th>
          </tr>
        `;
      }} else {{
        header.innerHTML = `
          <tr>
            <th class="py-3.5 px-4">Pontuação</th>
            <th class="py-3.5 px-4 min-w-[280px]">Produto & Marca</th>
            <th class="py-3.5 px-3">Perfil Nutricional</th>
            <th class="py-3.5 px-3">1º Ingrediente & Fórmulas</th>
            <th class="py-3.5 px-3">Preço / Kg</th>
            <th class="py-3.5 px-3">Rácio Q/P</th>
            <th class="py-3.5 px-3 text-right">Continente</th>
          </tr>
        `;
      }}
    }}

    function renderKPIs() {{
      const container = document.getElementById('kpiContainer');
      const data = currentCategory === 'wet' ? WET_DATA : DRY_DATA;
      const count = data.length;

      if (currentCategory === 'wet') {{
        const kittens = data.filter(p => p.k).length;
        const withSugar = data.filter(p => p.sug).length;
        const sugarPct = Math.round((withSugar / count) * 100);

        container.innerHTML = `
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Total Analisados (Húmida)</div>
            <div class="text-2xl font-black mt-1 text-white">${{count}}</div>
            <div class="text-[11px] text-emerald-400 mt-1">100% catálogo Continente</div>
          </div>
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Opções Júnior / Kitten</div>
            <div class="text-2xl font-black mt-1 text-amber-400">${{kittens}}</div>
            <div class="text-[11px] text-slate-400 mt-1">Crescimento acelerado</div>
          </div>
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Com Açúcares Adicionados</div>
            <div class="text-2xl font-black mt-1 text-rose-400">${{withSugar}}</div>
            <div class="text-[11px] text-rose-300 mt-1">${{sugarPct}}% das saquetas/latas</div>
          </div>
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Top Júnior Recomendada</div>
            <div class="text-sm font-bold mt-1.5 text-sky-400 truncate" title="Smaak Júnior Sem Cereais">Smaak Júnior Frango</div>
            <div class="text-[11px] text-slate-400 mt-1">Score 75 • 6.80 €/kg • Completa</div>
          </div>
        `;
      }} else {{
        const kittens = data.filter(p => p.k).length;
        const cornGluten = data.filter(p => p.cg).length;

        container.innerHTML = `
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Total Rações Secas</div>
            <div class="text-2xl font-black mt-1 text-white">${{count}}</div>
            <div class="text-[11px] text-emerald-400 mt-1">Catálogo completo auditado</div>
          </div>
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Fórmulas Júnior / Kitten</div>
            <div class="text-2xl font-black mt-1 text-amber-400">${{kittens}}</div>
            <div class="text-[11px] text-slate-400 mt-1">Alta proteína e gordura</div>
          </div>
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Top 1 Biológica Absoluta</div>
            <div class="text-sm font-bold mt-1.5 text-purple-400 truncate" title="Acana First Feast Júnior">Acana First Feast Júnior</div>
            <div class="text-[11px] text-slate-400 mt-1">Score 95 • 70%+ Carnes Nobres</div>
          </div>
          <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow">
            <div class="text-xs text-slate-400 font-medium">Melhor Relação Qualidade/Preço</div>
            <div class="text-sm font-bold mt-1.5 text-sky-400 truncate" title="Uppy Nutri Júnior (3kg)">Uppy Nutri Júnior Sem Cereais</div>
            <div class="text-[11px] text-slate-400 mt-1">Score 95 • 4.99 €/kg (3kg)</div>
          </div>
        `;
      }}
    }}

    function updateKittenAlert() {{
      const alert = document.getElementById('kittenAlert');
      const content = document.getElementById('kittenAlertContent');
      if (!filters.kitten) {{
        alert.classList.add('hidden');
        return;
      }}
      alert.classList.remove('hidden');
      if (currentCategory === 'wet') {{
        content.innerHTML = `
          <p>
            Gatinhos de 4 meses estão em crescimento ósseo e muscular acelerado. 
            <strong>Nunca utilize alimentos Complementares (ex: Schesir Júnior, Applaws) como refeição principal exclusiva</strong> — 
            alimente com fórmulas <strong>COMPLETAS</strong> (ex: Smaak Júnior Sem Cereais) para garantir a ingestão correta de taurina, cálcio e fósforo.
          </p>
        `;
      }} else {{
        content.innerHTML = `
          <p>
            Para um gatinho de 4 meses, a ração seca deve conter <strong>pelo menos 36–40% de proteína bruta</strong> e <strong>18–22% de matéria gorda</strong>. 
            <strong>Nunca dê ração para gatos adultos esterilizados</strong> nesta fase, pois têm restrição de gordura e calorias essenciais para o desenvolvimento dos órgãos.
          </p>
        `;
      }}
    }}

    function setTierFilter(tier) {{
      currentTierFilter = tier;
      document.querySelectorAll('.tier-btn').forEach(btn => {{
        const bTier = btn.getAttribute('data-tier');
        if (bTier === tier) {{
          btn.className = 'tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 text-white border border-sky-500 shadow';
        }} else {{
          btn.className = 'tier-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700 hover:border-slate-500';
        }}
      }});
      applyFilters();
    }}

    function toggleFilter(filterKey) {{
      filters[filterKey] = !filters[filterKey];
      const btnIdMap = {{
        kitten: 'toggleKitten',
        grainFree: 'toggleGrainFree',
        noSugar: 'toggleNoSugar',
        completeOnly: 'toggleCompleteOnly',
        noCornGluten: 'toggleNoCornGluten',
        noColorants: 'toggleNoColorants',
        nonSterilised: 'toggleNonSterilised'
      }};

      const btn = document.getElementById(btnIdMap[filterKey]);
      if (btn) {{
        if (filters[filterKey]) {{
          btn.classList.add('bg-sky-600', 'text-white', 'border-sky-500');
          btn.classList.remove('bg-slate-800', 'text-slate-300', 'border-slate-700');
        }} else {{
          btn.classList.remove('bg-sky-600', 'text-white', 'border-sky-500');
          btn.classList.add('bg-slate-800', 'text-slate-300', 'border-slate-700');
        }}
      }}
      if (filterKey === 'kitten') {{
        updateKittenAlert();
      }}
      applyFilters();
    }}

    function applyFilters() {{
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const sortMode = document.getElementById('sortSelect').value;
      const data = currentCategory === 'wet' ? WET_DATA : DRY_DATA;

      document.getElementById('totalCategoryCount').innerText = data.length;

      let filtered = data.filter(p => {{
        // Search query
        if (query) {{
          const name = (p.n || '').toLowerCase();
          const brand = (p.b || '').toLowerCase();
          const fi = (p.fi || '').toLowerCase();
          if (!name.includes(query) && !brand.includes(query) && !fi.includes(query)) {{
            return false;
          }}
        }}

        // Tier filter
        if (currentTierFilter !== 'all') {{
          if (!p.t || !p.t.startsWith(currentTierFilter)) {{
            return false;
          }}
        }}

        // Shared filters
        if (filters.kitten && !p.k) return false;
        if (filters.grainFree) {{
          if (currentCategory === 'wet' && p.grn) return false;
          if (currentCategory === 'dry' && !p.gf) return false;
        }}

        // Wet-specific filters
        if (currentCategory === 'wet') {{
          if (filters.noSugar && p.sug) return false;
          if (filters.completeOnly && p.c !== 'Completo') return false;
        }}

        // Dry-specific filters
        if (currentCategory === 'dry') {{
          if (filters.noCornGluten && p.cg) return false;
          if (filters.noColorants && p.col) return false;
          if (filters.nonSterilised && p.st) return false;
        }}

        return true;
      }});

      // Sorting
      filtered.sort((a, b) => {{
        if (sortMode === 'vr') return (b.vr || 0) - (a.vr || 0);
        if (sortMode === 'score_desc') return (b.s || 0) - (a.s || 0);
        if (sortMode === 'price_asc') return (a.pkg || 999) - (b.pkg || 999);
        if (sortMode === 'price_desc') return (b.pkg || 0) - (a.pkg || 0);
        if (sortMode === 'prot_desc') return (b.prot || 0) - (a.prot || 0);
        if (sortMode === 'carb_asc') return (a.carb || 999) - (b.carb || 999);
        return 0;
      }});

      document.getElementById('visibleCount').innerText = filtered.length;
      renderTableBody(filtered);
    }}

    function getTierBadgeClass(tier) {{
      if (!tier) return 'badge-tier-c';
      if (tier.startsWith('Tier S')) return 'badge-tier-s';
      if (tier.startsWith('Tier A')) return 'badge-tier-a';
      if (tier.startsWith('Tier B')) return 'badge-tier-b';
      if (tier.startsWith('Tier C')) return 'badge-tier-c';
      return 'badge-tier-d';
    }}

    function renderTableBody(products) {{
      const tbody = document.getElementById('tableBody');
      if (products.length === 0) {{
        tbody.innerHTML = `
          <tr>
            <td colspan="7" class="py-12 text-center text-slate-500">
              Nenhum produto encontrado com os filtros atuais.
            </td>
          </tr>
        `;
        return;
      }}

      let rowsHtml = '';
      for (const p of products) {{
        const tierClass = getTierBadgeClass(p.t);
        const priceKgStr = p.pkg ? `${{p.pkg.toFixed(2)}} €/kg` : 'N/D';
        const priceStr = p.p ? `${{p.p.toFixed(2)}} €` : 'N/D';
        const pdpUrl = p.u || '#';

        if (currentCategory === 'wet') {{
          // Wet Food Row
          const compBadge = p.c === 'Completo' 
            ? '<span class="px-2 py-0.5 rounded text-[11px] font-semibold badge-complete">Completo</span>'
            : '<span class="px-2 py-0.5 rounded text-[11px] font-semibold badge-comp">Complementar</span>';

          const sugarBadge = p.sug 
            ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-rose-950/80 text-rose-300 border border-rose-800 font-medium">Açúcar</span>'
            : '<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-300 border border-emerald-800 font-medium">Sem Açúcar</span>';

          const grainBadge = p.grn
            ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-950/80 text-amber-300 border border-amber-800 font-medium">Cereais</span>'
            : '<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-300 border border-emerald-800 font-medium">Sem Cereais</span>';

          const kittenBadge = p.k
            ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-900/80 text-amber-200 border border-amber-600 font-bold">🍼 Júnior</span>'
            : '';

          rowsHtml += `
            <tr class="hover:bg-slate-800/40 transition">
              <td class="py-3 px-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span class="text-base font-black px-2.5 py-1 rounded-lg ${{tierClass}}">${{p.s}}</span>
                  <span class="text-[11px] text-slate-400 hidden sm:inline">${{p.t.split(' ')[0]}}</span>
                </div>
              </td>
              <td class="py-3 px-4">
                <div class="font-semibold text-white leading-tight">${{p.n}}</div>
                <div class="flex items-center gap-2 mt-1">
                  <span class="text-xs text-sky-400 font-medium">${{p.b}}</span>
                  ${{kittenBadge}}
                </div>
              </td>
              <td class="py-3 px-3 whitespace-nowrap">${{compBadge}}</td>
              <td class="py-3 px-3">
                <div class="flex flex-wrap gap-1">${{sugarBadge}}${{grainBadge}}</div>
              </td>
              <td class="py-3 px-3 whitespace-nowrap">
                <div class="font-bold text-white">${{priceKgStr}}</div>
                <div class="text-[11px] text-slate-400">${{priceStr}}</div>
              </td>
              <td class="py-3 px-3 whitespace-nowrap">
                <span class="font-black text-emerald-400 text-sm">${{p.vr ? p.vr.toFixed(1) : '-'}}</span>
              </td>
              <td class="py-3 px-3 text-right whitespace-nowrap">
                <a href="${{pdpUrl}}" target="_blank" class="px-3 py-1.5 rounded-lg bg-sky-950 text-sky-300 border border-sky-800 text-xs font-semibold hover:bg-sky-900 transition inline-block">
                  Ver ↗
                </a>
              </td>
            </tr>
          `;
        }} else {{
          // Dry Food Row
          const protStr = p.prot ? `${{p.prot}}% Prot` : '-';
          const fatStr = p.fat ? `${{p.fat}}% Gord` : '-';
          const carbStr = p.carb ? `${{p.carb}}% Carb` : '-';

          const gfBadge = p.gf
            ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-300 border border-emerald-800 font-medium">Sem Cereais</span>'
            : '<span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-950/80 text-amber-300 border border-amber-800 font-medium">Com Cereais</span>';

          const cgBadge = p.cg
            ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-rose-950/80 text-rose-300 border border-rose-800 font-medium">Glúten Milho</span>'
            : '';

          const colBadge = p.col
            ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-rose-950/80 text-rose-300 border border-rose-800 font-medium">Corantes</span>'
            : '';

          const kittenBadge = p.k
            ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-900/80 text-amber-200 border border-amber-600 font-bold">🍼 Júnior</span>'
            : (p.st ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-purple-950/80 text-purple-300 border border-purple-800">Esterilizado</span>' : '');

          rowsHtml += `
            <tr class="hover:bg-slate-800/40 transition">
              <td class="py-3 px-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span class="text-base font-black px-2.5 py-1 rounded-lg ${{tierClass}}">${{p.s}}</span>
                  <span class="text-[11px] text-slate-400 hidden sm:inline">${{p.t.split(' ')[0]}}</span>
                </div>
              </td>
              <td class="py-3 px-4">
                <div class="font-semibold text-white leading-tight">${{p.n}}</div>
                <div class="flex items-center gap-2 mt-1">
                  <span class="text-xs text-sky-400 font-medium">${{p.b}}</span>
                  ${{kittenBadge}}
                </div>
              </td>
              <td class="py-3 px-3 whitespace-nowrap">
                <div class="text-xs font-semibold text-white">${{protStr}} • ${{fatStr}}</div>
                <div class="text-[11px] text-slate-400">${{carbStr}}</div>
              </td>
              <td class="py-3 px-3">
                <div class="text-xs text-slate-300 truncate max-w-[200px]" title="${{p.fi || ''}}">${{p.fi || 'N/D'}}</div>
                <div class="flex flex-wrap gap-1 mt-1">${{gfBadge}}${{cgBadge}}${{colBadge}}</div>
              </td>
              <td class="py-3 px-3 whitespace-nowrap">
                <div class="font-bold text-white">${{priceKgStr}}</div>
                <div class="text-[11px] text-slate-400">${{priceStr}}</div>
              </td>
              <td class="py-3 px-3 whitespace-nowrap">
                <span class="font-black text-emerald-400 text-sm">${{p.vr ? p.vr.toFixed(1) : '-'}}</span>
              </td>
              <td class="py-3 px-3 text-right whitespace-nowrap">
                <a href="${{pdpUrl}}" target="_blank" class="px-3 py-1.5 rounded-lg bg-sky-950 text-sky-300 border border-sky-800 text-xs font-semibold hover:bg-sky-900 transition inline-block">
                  Ver ↗
                </a>
              </td>
            </tr>
          `;
        }}
      }}
      tbody.innerHTML = rowsHtml;
    }}

    // Init
    document.getElementById('wetCountPill').innerText = WET_DATA.length;
    document.getElementById('dryCountPill').innerText = DRY_DATA.length;
    document.getElementById('searchInput').addEventListener('input', applyFilters);
    document.getElementById('sortSelect').addEventListener('change', applyFilters);

    // Initial render
    switchCategory('wet');
  </script>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[Builder] Successfully generated dashboard at {output_path}")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, 'data')
    output_path = os.path.join(base_dir, 'index.html')
    
    wet, dry = load_data(data_dir)
    print(f"[Builder] Loaded {len(wet)} wet products and {len(dry)} dry products.")
    generate_html(wet, dry, output_path)

if __name__ == '__main__':
    main()

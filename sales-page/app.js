const state = {
  route: "#inicio",
  theme: "light",
  plan: "PRO",
  user: { email: "", token: "" },
  date: "",
  resultsByDate: {},
  gamesByDate: {},
  stats: {
    heatmap: [],
    trends: {
      hot: [],
      cold: [],
      delay: [],
    },
    distributions: {
      parity: { even: 0, odd: 0 },
      sum: 0,
      primes: 0,
      border: 0,
    },
    brains: [],
  },
  selected: {
    mode: "select",
    picks: new Set(),
    fixed: new Set(),
    excluded: new Set(),
    savedGames: [],
  },
  ui: {
    topLimit: 10,
    filters: {
      parity: "",
      sumRange: "",
      primes: "",
      repeats: "",
    },
    faqOpen: 0,
    sidebarCollapsed: false,
    modal: null,
    loadingGames: false,
  },
};

const planLimits = {
  ESSENCIAL: 10,
  PRO: 200,
  ELITE: 1000,
};

const formatNumber = (value) => String(value).padStart(2, "0");

const createElement = (tag, attrs = {}, children = []) => {
  const el = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else el.setAttribute(key, value);
  });
  children.forEach((child) => el.appendChild(child));
  return el;
};

const toast = (message) => {
  alert(message);
};

const copyToClipboard = (text) => {
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text);
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  toast("Conteúdo copiado para a área de transferência.");
};

const downloadTxt = (filename, content) => {
  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

const buildHashRoute = () => location.hash || "#inicio";

const generateResults = () => {
  const numbers = new Set();
  while (numbers.size < 15) {
    numbers.add(Math.floor(Math.random() * 25) + 1);
  }
  return Array.from(numbers).sort((a, b) => a - b);
};

const primeNumbers = new Set([2, 3, 5, 7, 11, 13, 17, 19, 23]);

const generateGame = (results) => {
  const numbers = new Set();
  while (numbers.size < 15) {
    numbers.add(Math.floor(Math.random() * 25) + 1);
  }
  const list = Array.from(numbers).sort((a, b) => a - b);
  const evens = list.filter((num) => num % 2 === 0).length;
  const odds = 15 - evens;
  const sum = list.reduce((acc, num) => acc + num, 0);
  const primes = list.filter((num) => primeNumbers.has(num)).length;
  const repeats = list.filter((num) => results.includes(num)).length;
  return {
    rank: 0,
    score: Number((Math.random() * 0.5 + 0.5).toFixed(2)),
    numbers: list,
    tags: {
      parity: `${odds}/${evens}`,
      sumRange: sum,
      primes,
      repeats,
    },
  };
};

const generateMockStats = () => {
  state.stats.heatmap = Array.from({ length: 25 }, (_, index) => ({
    number: index + 1,
    frequency: Math.floor(Math.random() * 180) + 40,
    delay: Math.floor(Math.random() * 12) + 1,
    trend: Math.floor(Math.random() * 30) - 10,
  }));

  const sorted = [...state.stats.heatmap].sort((a, b) => b.frequency - a.frequency);
  state.stats.trends.hot = sorted.slice(0, 5);
  state.stats.trends.cold = sorted.slice(-5);
  state.stats.trends.delay = [...state.stats.heatmap].sort((a, b) => b.delay - a.delay).slice(0, 5);

  state.stats.distributions.parity = {
    even: 7,
    odd: 8,
  };
  state.stats.distributions.sum = 195;
  state.stats.distributions.primes = 6;
  state.stats.distributions.border = 8;

  state.stats.brains = Array.from({ length: 5 }, (_, index) => ({
    name: `Cérebro ${index + 1}`,
    games: Math.floor(Math.random() * 5000) + 1000,
    average: (Math.random() * 2 + 12).toFixed(2),
    hits14: Math.floor(Math.random() * 40),
    hits15: Math.floor(Math.random() * 10),
  }));
};

const seedData = () => {
  const today = new Date();
  const dates = [
    today,
    new Date(today.getTime() - 86400000),
    new Date(today.getTime() - 86400000 * 2),
  ];

  dates.forEach((date, index) => {
    const key = date.toISOString().split("T")[0];
    const results = generateResults();
    state.resultsByDate[key] = {
      date: key,
      contest: 3594 - index,
      numbers: results,
    };

    const games = Array.from({ length: 1000 }, () => generateGame(results));
    games.sort((a, b) => b.score - a.score);
    games.forEach((game, idx) => {
      game.rank = idx + 1;
    });
    state.gamesByDate[key] = games;
  });

  state.date = Object.keys(state.resultsByDate)[0];
  generateMockStats();
};

const getPlanLimit = () => planLimits[state.plan] || 10;

const filterGames = (games) => {
  return games.filter((game) => {
    const { parity, sumRange, primes, repeats } = state.ui.filters;
    if (parity && game.tags.parity !== parity) return false;
    if (sumRange) {
      const [min, max] = sumRange.split("-").map(Number);
      if (game.tags.sumRange < min || game.tags.sumRange > max) return false;
    }
    if (primes && game.tags.primes !== Number(primes)) return false;
    if (repeats && (game.tags.repeats < Number(repeats.split("-")[0]) || game.tags.repeats > Number(repeats.split("-")[1]))) {
      return false;
    }
    return true;
  });
};

const getTopGames = () => {
  const games = state.gamesByDate[state.date] || [];
  const filtered = filterGames(games);
  const limit = Math.min(state.ui.topLimit, getPlanLimit());
  return filtered.slice(0, limit);
};

const renderBalls = (numbers, className = "") => {
  return numbers
    .map((num) => `<span class="ball ${className}">${formatNumber(num)}</span>`)
    .join("");
};

const renderSidebar = () => {
  const links = [
    { route: "#inicio", label: "Início", icon: "🏠" },
    { route: "#gerador", label: "Gerador", icon: "🎯" },
    { route: "#jogos", label: "Jogos do Dia", icon: "📋" },
    { route: "#resultados", label: "Resultados", icon: "🏆" },
    { route: "#estatisticas", label: "Estatísticas", icon: "📊" },
    { route: "#planos", label: "Planos", icon: "💎" },
    { route: "#assinante", label: "Assinante", icon: "👤" },
    { route: "#ajuda", label: "Ajuda", icon: "❓" },
  ];

  return `
    <aside class="sidebar ${state.ui.sidebarCollapsed ? "collapsed" : ""}">
      <div class="sidebar__brand">
        <div class="sidebar__logo" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C9.2 4.2 8 6.5 8 9c0 2.9 1.8 5 4 5s4-2.1 4-5c0-2.5-1.2-4.8-4-7Z" fill="#ECFDF3"/>
            <path d="M12 22c3.5-2.1 6-5.4 6-9.6 0-3.8-2.4-7-6-8.6-3.6 1.6-6 4.8-6 8.6 0 4.2 2.5 7.5 6 9.6Z" fill="#5EEAD4" fill-opacity="0.9"/>
          </svg>
        </div>
        <div class="sidebar__title">Trevo 4 Folhas</div>
      </div>
      <nav class="sidebar__nav">
        ${links
          .map(
            (link) => `
          <button class="sidebar__link ${state.route === link.route ? "active" : ""}" data-route="${link.route}" aria-label="${link.label}">
            <span aria-hidden="true">${link.icon}</span>
            <span>${link.label}</span>
          </button>
        `
          )
          .join("")}
      </nav>
      <div class="sidebar__footer">
        Produto informativo e estatístico.<br />Sem garantia de prêmio.
      </div>
    </aside>
  `;
};

const renderTopbar = () => {
  const dateOptions = Object.keys(state.resultsByDate)
    .map((date) => `<option value="${date}" ${date === state.date ? "selected" : ""}>${date}</option>`)
    .join("");

  return `
    <div class="topbar">
      <div class="topbar__left">
        <button class="button button--ghost" id="toggle-sidebar" aria-label="Alternar menu">☰</button>
        <div class="topbar__breadcrumb">${state.route.replace("#", "").toUpperCase()}</div>
      </div>
      <div class="topbar__actions">
        <label>
          Data
          <select id="date-select" aria-label="Selecionar data">${dateOptions}</select>
        </label>
        <label>
          Plano
          <select id="plan-select" aria-label="Selecionar plano">
            ${["ESSENCIAL", "PRO", "ELITE"]
              .map(
                (plan) => `<option value="${plan}" ${plan === state.plan ? "selected" : ""}>${plan}</option>`
              )
              .join("")}
          </select>
        </label>
        <button class="button button--ghost" id="theme-toggle" aria-label="Alternar modo escuro">🌗</button>
        <button class="button button--secondary" id="share-btn" aria-label="Compartilhar">Compartilhar</button>
      </div>
    </div>
  `;
};

const renderInicio = () => {
  const games = getTopGames().slice(0, 5);
  return `
    <section class="card hero">
      <div>
        <span class="badge">Análise atualizada diariamente</span>
        <h1 class="hero__title">Jogos com Análise Estatística Atualizada Diariamente</h1>
        <p>Organize seus jogos, avalie filtros e acompanhe rankings com transparência. Produto informativo e estatístico, sem garantia de prêmio.</p>
        <div class="grid grid--3">
          <div class="kpi">
            <strong>3.594 concursos analisados</strong>
            <p class="muted">Base histórica organizada para apoiar seu método.</p>
          </div>
          <div class="kpi">
            <strong>4.728.233 simulações registradas</strong>
            <p class="muted">Modelos estatísticos revisados diariamente.</p>
          </div>
          <div class="kpi">
            <strong>51 filtros ativos</strong>
            <p class="muted">Critérios combináveis por perfil de jogo.</p>
          </div>
        </div>
        <div class="tabs">
          <button class="button button--primary" data-route="#planos" aria-label="Ver planos">Ver planos</button>
          <button class="button button--ghost" data-route="#jogos" aria-label="Ver jogos do dia">Ver jogos do dia</button>
        </div>
      </div>
      <div class="card card--flat">
        <h3>TOP 5 jogos do dia</h3>
        <div class="list">
          ${games
            .map(
              (game) => `
            <div class="list-item">
              <div class="badge">#${game.rank} · Score ${game.score}</div>
              <div class="balls">${renderBalls(game.numbers)}</div>
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    </section>
    <section class="grid grid--3">
      ${[
        "Treina com histórico",
        "Gera listas inteligentes",
        "Entrega ranking diário",
      ]
        .map(
          (title, index) => `
        <div class="card">
          <span class="badge">Passo ${index + 1}</span>
          <h3>${title}</h3>
          <p>${
            index === 0
              ? "Modelos estatísticos organizam padrões de dezenas e ciclos." 
              : index === 1
              ? "Filtros e parâmetros guiam a seleção com consistência." 
              : "Ranking TOP facilita decisões com transparência."
          }</p>
        </div>
      `
        )
        .join("")}
    </section>
    <section class="card">
      <h3>Perguntas frequentes</h3>
      <div class="accordion" id="faq">
        ${[
          "Como os jogos são analisados?",
          "Posso exportar as listas?",
          "O sistema garante prêmio?",
          "Como funcionam os filtros?",
          "Posso trocar de plano?",
          "Existe suporte?",
        ]
          .map(
            (question, index) => `
          <div class="accordion-item ${state.ui.faqOpen === index ? "active" : ""}">
            <button data-faq="${index}" aria-label="${question}">${question}</button>
            <div class="accordion-content">
              ${index === 2
                ? "Não. É um produto informativo e estatístico, sem garantia de prêmio."
                : "Conteúdo explicativo (demo)."
              }
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    </section>
  `;
};

const renderGerador = () => {
  const { picks, fixed, excluded } = state.selected;
  const selectedCounts = {
    picks: picks.size,
    fixed: fixed.size,
    excluded: excluded.size,
  };
  const saved = state.selected.savedGames;
  return `
    <section class="grid grid--2">
      <div class="card">
        <h2>Volante Lotofácil</h2>
        <div class="tabs">
          ${["select", "fix", "exclude"]
            .map(
              (mode) => `
            <button class="tab ${state.selected.mode === mode ? "active" : ""}" data-mode="${mode}" aria-label="Modo ${mode}">${
        mode === "select" ? "Selecionar" : mode === "fix" ? "Fixar" : "Excluir"
      }</button>
          `
            )
            .join("")}
        </div>
        <p>Selecionadas: ${selectedCounts.picks} · Fixas: ${selectedCounts.fixed} · Excluídas: ${selectedCounts.excluded}</p>
        <div class="volante" id="volante">
          ${Array.from({ length: 25 }, (_, idx) => {
            const number = idx + 1;
            const classes = [
              picks.has(number) ? "ball--selected" : "",
              fixed.has(number) ? "ball--fixed" : "",
              excluded.has(number) ? "ball--excluded" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return `<button class="ball ${classes}" data-number="${number}" aria-label="Dezena ${number}">${formatNumber(number)}</button>`;
          }).join("")}
        </div>
        <div class="tabs">
          <button class="button button--ghost" id="clear-volante" aria-label="Limpar volante">Limpar</button>
          <button class="button button--ghost" id="copy-volante" aria-label="Copiar seleção">Copiar</button>
          <button class="button button--ghost" id="paste-volante" aria-label="Colar seleção">Colar</button>
          <button class="button button--primary" id="generate-game" aria-label="Gerar jogo">Gerar jogo</button>
        </div>
      </div>
      <div class="card">
        <div class="tabs">
          <h2>Parâmetros do Jogo</h2>
          <button class="button button--ghost" id="toggle-params" aria-label="Ocultar parâmetros">Ocultar Parâmetros</button>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>Parâmetro</th>
              <th>Qtd alvo</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${[
              "Ímpares",
              "Pares",
              "Repetidas",
              "Moldura",
              "Primos",
              "Múltiplos de 3",
              "Fibonacci",
              "Soma",
            ]
              .map(
                (label, index) => `
              <tr>
                <td>${label}</td>
                <td><input class="input" value="${index + 1}" aria-label="Qtd ${label}" /></td>
                <td><span class="badge ${index % 3 === 0 ? "" : index % 3 === 1 ? "badge--warning" : "badge--danger"}">${
                  index % 3 === 0 ? "ok" : index % 3 === 1 ? "aguardando" : "erro"
                }</span></td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
    <section class="card">
      <h3>Jogos Selecionados</h3>
      <div class="list">
        ${Array.from({ length: 10 }, (_, idx) => {
          const game = saved[idx];
          if (!game) {
            return `<div class="list-item">Slot ${idx + 1} disponível</div>`;
          }
          return `
            <div class="list-item">
              <div class="badge">Paridade ${game.tags.parity} · Soma ${game.tags.sumRange}</div>
              <div class="balls">${renderBalls(game.numbers)}</div>
              <div class="tabs">
                <button class="button button--ghost" data-detail="${idx}" aria-label="Detalhes">Detalhes</button>
              </div>
            </div>
          `;
        }).join("")}
      </div>
      <div class="tabs">
        <button class="button button--primary" id="save-games" aria-label="Salvar jogos">Salvar (demo)</button>
        <button class="button button--secondary" id="export-games" aria-label="Exportar TXT">Exportar TXT</button>
        <button class="button button--danger" id="clear-games" aria-label="Limpar lista">Limpar lista</button>
      </div>
    </section>
  `;
};

const renderJogos = () => {
  const topGames = getTopGames();
  const total = Math.min(state.ui.topLimit, getPlanLimit());
  return `
    <section class="card">
      <h2>Melhores Jogos do Dia</h2>
      <p>Selecione o TOP desejado conforme seu plano. Plano atual: <strong>${state.plan}</strong> (TOP máximo ${getPlanLimit()}).</p>
      <div class="tabs">
        ${[1, 10, 50, 200, 1000]
          .map(
            (value) => `
          <button class="tab ${state.ui.topLimit === value ? "active" : ""}" data-top="${value}" aria-label="TOP ${value}">TOP ${value}</button>
        `
          )
          .join("")}
      </div>
      <div class="chips">
        ${["7/8", "8/7", "6/9"].map(
          (value) => `<button class="chip ${state.ui.filters.parity === value ? "active" : ""}" data-parity="${value}">${value}</button>`
        ).join("")}
        ${["170-210", "180-220"].map(
          (value) => `<button class="chip ${state.ui.filters.sumRange === value ? "active" : ""}" data-sum="${value}">${value}</button>`
        ).join("")}
        ${["5", "6", "7"].map(
          (value) => `<button class="chip ${state.ui.filters.primes === value ? "active" : ""}" data-primes="${value}">Primos ${value}</button>`
        ).join("")}
        ${["8-10"].map(
          (value) => `<button class="chip ${state.ui.filters.repeats === value ? "active" : ""}" data-repeats="${value}">Repetidas ${value}</button>`
        ).join("")}
      </div>
      <div class="tabs">
        <button class="button button--primary" id="copy-top" aria-label="Copiar TOP">Copiar TOP</button>
        <button class="button button--secondary" id="download-top" aria-label="Baixar TXT">Baixar TXT</button>
        <button class="button button--ghost" id="share-top" aria-label="Compartilhar">Compartilhar</button>
      </div>
      <p class="notice notice--info">Transparência: produto informativo e estatístico, sem garantia de prêmio.</p>
    </section>
    <section class="card">
      <h3>Lista TOP ${total}</h3>
      <div class="list">
        ${topGames
          .map(
            (game) => `
          <div class="list-item">
            <div class="badge">#${game.rank} · Score ${game.score}</div>
            <div class="balls">${renderBalls(game.numbers)}</div>
            <p>Paridade ${game.tags.parity} · Soma ${game.tags.sumRange} · Primos ${game.tags.primes} · Repetidas ${game.tags.repeats}</p>
            <div class="tabs">
              <button class="button button--ghost" data-copy="${game.rank}" aria-label="Copiar jogo">Copiar</button>
              <button class="button button--ghost" data-detail="${game.rank}" aria-label="Detalhes">Detalhes</button>
              <button class="button button--primary" data-add="${game.rank}" aria-label="Adicionar aos selecionados">Adicionar aos Selecionados</button>
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    </section>
  `;
};

const renderResultados = () => {
  const results = state.resultsByDate[state.date];
  return `
    <section class="grid grid--2">
      <div class="card">
        <h2>Último Resultado</h2>
        <p>Concurso ${results.contest} · ${results.date}</p>
        <div class="balls">${renderBalls(results.numbers, "ball--selected")}</div>
      </div>
      <div class="card">
        <h2>Conferidor de Jogo</h2>
        <p>Cole 15 dezenas para conferir.</p>
        <textarea id="check-input" rows="3" class="input" placeholder="01 02 05 07 09 10 11 12 13 14 15 18 20 22 25"></textarea>
        <button class="button button--primary" id="check-game" aria-label="Conferir">Conferir</button>
        <div id="check-result"></div>
      </div>
    </section>
    <section class="grid grid--2">
      <div class="card">
        <h3>Simular premiações (demo)</h3>
        <div class="grid grid--2">
          <label>Concurso inicial
            <input class="input" value="3580" />
          </label>
          <label>Concurso final
            <input class="input" value="3594" />
          </label>
        </div>
        <table class="table">
          <tbody>
            ${[15, 14, 13, 12, 11]
              .map((points) => `<tr><td>${points} pontos</td><td>${Math.floor(Math.random() * 20)}</td></tr>`)
              .join("")}
          </tbody>
        </table>
        <button class="button button--ghost" id="open-prize" aria-label="Mostrar detalhamento">Mostrar detalhamento</button>
      </div>
      <div class="card">
        <h3>Aviso</h3>
        <p class="notice">Produto informativo e estatístico. Loterias envolvem aleatoriedade. Não existe garantia de prêmio.</p>
      </div>
    </section>
  `;
};

const renderEstatisticas = () => {
  const heatmap = state.stats.heatmap;
  const highest = Math.max(...heatmap.map((item) => item.frequency));
  return `
    <section class="card">
      <h2>Mapa / Heatmap 25 dezenas</h2>
      <div class="tabs">
        <button class="tab active">Histórico total</button>
        <button class="tab">Últimos 120</button>
      </div>
      <div class="heatmap">
        ${heatmap
          .map((item) => {
            const opacity = item.frequency / highest;
            return `<div class="ball" style="background: rgba(16, 185, 129, ${opacity});" title="Freq ${item.frequency} · Atraso ${item.delay} · Tendência ${item.trend}">${formatNumber(item.number)}</div>`;
          })
          .join("")}
      </div>
    </section>
    <section class="grid grid--3">
      <div class="card">
        <h3>Dezenas quentes</h3>
        ${state.stats.trends.hot.map((item) => `<p>${formatNumber(item.number)} · ${item.frequency}</p>`).join("")}
      </div>
      <div class="card">
        <h3>Dezenas frias</h3>
        ${state.stats.trends.cold.map((item) => `<p>${formatNumber(item.number)} · ${item.frequency}</p>`).join("")}
      </div>
      <div class="card">
        <h3>Atraso</h3>
        ${state.stats.trends.delay.map((item) => `<p>${formatNumber(item.number)} · ${item.delay} concursos</p>`).join("")}
      </div>
    </section>
    <section class="grid grid--2">
      <div class="card">
        <h3>Distribuições</h3>
        <p>Par / Ímpar</p>
        <div class="bar"><span style="width: ${(state.stats.distributions.parity.even / 15) * 100}%"></span></div>
        <p>Soma média: ${state.stats.distributions.sum}</p>
        <p>Primos: ${state.stats.distributions.primes}</p>
        <p>Moldura: ${state.stats.distributions.border}</p>
      </div>
      <div class="card">
        <h3>Cérebros (demo)</h3>
        ${state.stats.brains
          .map(
            (brain) => `
          <div class="list-item">
            <strong>${brain.name}</strong>
            <p>${brain.games} jogos · média ${brain.average} · 14+ ${brain.hits14} · 15 ${brain.hits15}</p>
          </div>
        `
          )
          .join("")}
        <p>Combinação de filtros avançados (demo).</p>
      </div>
    </section>
  `;
};

const renderPlanos = () => {
  return `
    <section class="grid grid--3">
      ${[
        { name: "Essencial", price: "R$ 29/mês", limit: 10, highlight: false },
        { name: "Pro", price: "R$ 59/mês", limit: 200, highlight: true },
        { name: "Elite", price: "R$ 99/mês", limit: 1000, highlight: false },
      ]
        .map(
          (plan) => `
        <div class="card ${plan.highlight ? "card--flat" : ""}">
          <span class="badge">TOP ${plan.limit}</span>
          <h3>${plan.name}</h3>
          <p><strong>${plan.price}</strong></p>
          <ul>
            <li>Rankings diários</li>
            <li>Filtros avançados</li>
            <li>Exportações premium</li>
          </ul>
          <button class="button button--primary" data-plan="${plan.name}" aria-label="Assinar ${plan.name}">Assinar</button>
        </div>
      `
        )
        .join("")}
    </section>
    <section class="card">
      <h3>Comparativo</h3>
      <table class="table">
        <thead>
          <tr>
            <th>Recursos</th>
            <th>Essencial</th>
            <th>Pro</th>
            <th>Elite</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>TOP liberado</td>
            <td>10</td>
            <td>200</td>
            <td>1000</td>
          </tr>
          <tr>
            <td>Filtros avançados</td>
            <td>Básico</td>
            <td>Completo</td>
            <td>Completo +</td>
          </tr>
          <tr>
            <td>Exportações</td>
            <td>TXT</td>
            <td>TXT + Compartilhar</td>
            <td>Completo</td>
          </tr>
        </tbody>
      </table>
      <p class="notice">Produto informativo e estatístico. Loterias envolvem aleatoriedade. Não existe garantia de prêmio.</p>
    </section>
  `;
};

const renderAssinante = () => {
  return `
    <section class="grid grid--2">
      <div class="card">
        <h2>Área do Assinante (demo)</h2>
        ${state.user.token
          ? `
          <p>Bem-vindo, ${state.user.email}. Plano atual: <strong>${state.plan}</strong>.</p>
          <p>Limite TOP: ${getPlanLimit()} · Consultas/dia: 100</p>
          <button class="button button--ghost" id="invite" aria-label="Gerar link de convite">Gerar link de convite</button>
          <button class="button button--danger" id="logout" aria-label="Sair">Sair</button>
        `
          : `
          <label>Email
            <input class="input" id="login-email" placeholder="voce@email.com" />
          </label>
          <label>Senha
            <input class="input" id="login-password" type="password" placeholder="••••••" />
          </label>
          <button class="button button--primary" id="login" aria-label="Entrar">Entrar</button>
        `}
      </div>
      <div class="card">
        <h3>Jogos por data</h3>
        <p>Selecione a data para visualizar o ranking daquele dia.</p>
        <div class="tabs">
          ${Object.keys(state.resultsByDate)
            .map(
              (date) => `
            <button class="tab ${state.date === date ? "active" : ""}" data-date="${date}">${date}</button>
          `
            )
            .join("")}
        </div>
        <p>Jogos disponíveis: ${(state.gamesByDate[state.date] || []).length}</p>
      </div>
    </section>
  `;
};

const renderAjuda = () => {
  return `
    <section class="grid grid--2">
      <div class="card">
        <h2>Ajuda & Termos</h2>
        <p>Produto informativo e estatístico. Loterias envolvem aleatoriedade. Não existe garantia de prêmio.</p>
        <p>Use o painel para organizar jogos e acompanhar estatísticas.</p>
        <p><strong>FAQ técnico</strong></p>
        <ul>
          <li>Como usar: navegue por abas e ajuste filtros.</li>
          <li>Como conferir: cole dezenas e pressione Conferir.</li>
          <li>Como exportar: use “Baixar TXT”.</li>
        </ul>
      </div>
      <div class="card">
        <h3>Status do Sistema</h3>
        <p>Modo: demo/mock</p>
        <p>Versão: v0.1</p>
        <p>Último lote: ${state.date}</p>
      </div>
    </section>
  `;
};

const renderFooter = () => `
  <footer class="footer">
    <p>Produto informativo e estatístico. Loterias envolvem aleatoriedade. Não existe garantia de prêmio.</p>
  </footer>
`;

const renderModal = () => {
  if (!state.ui.modal) return "";
  if (state.ui.modal === "checkout") {
    return `
      <div class="modal active" id="modal">
        <div class="modal__content">
          <h3>Checkout (demo)</h3>
          <p>Assinatura selecionada: <strong>${state.ui.modalPlan || "Pro"}</strong></p>
          <label>Cupom
            <input class="input" placeholder="TREVO10" />
          </label>
          <a class="button button--primary" href="#" aria-label="Assinar na Hotmart">Assinar na Hotmart</a>
          <p class="notice">Produto informativo e estatístico. Loterias envolvem aleatoriedade. Não existe garantia de prêmio.</p>
          <button class="button button--ghost" id="close-modal" aria-label="Fechar">Fechar</button>
        </div>
      </div>
    `;
  }
  if (state.ui.modal === "details") {
    const game = state.ui.modalGame;
    return `
      <div class="modal active" id="modal">
        <div class="modal__content">
          <h3>Detalhes do Jogo</h3>
          <div class="balls">${renderBalls(game.numbers, "ball--selected")}</div>
          <p>Paridade ${game.tags.parity} · Soma ${game.tags.sumRange}</p>
          <button class="button button--ghost" id="copy-modal" aria-label="Copiar jogo">Copiar jogo</button>
          <button class="button button--primary" id="close-modal" aria-label="Fechar">Fechar</button>
        </div>
      </div>
    `;
  }
  if (state.ui.modal === "prize") {
    return `
      <div class="modal active" id="modal">
        <div class="modal__content">
          <h3>Detalhamento (demo)</h3>
          <div class="bar"><span style="width: 80%"></span></div>
          <div class="bar"><span style="width: 60%"></span></div>
          <div class="bar"><span style="width: 40%"></span></div>
          <button class="button button--primary" id="close-modal" aria-label="Fechar">Fechar</button>
        </div>
      </div>
    `;
  }
  return "";
};

const renderContent = () => {
  switch (state.route) {
    case "#gerador":
      return renderGerador();
    case "#jogos":
      return renderJogos();
    case "#resultados":
      return renderResultados();
    case "#estatisticas":
      return renderEstatisticas();
    case "#planos":
      return renderPlanos();
    case "#assinante":
      return renderAssinante();
    case "#ajuda":
      return renderAjuda();
    default:
      return renderInicio();
  }
};

const renderApp = () => {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="app-shell">
      ${renderSidebar()}
      <div class="main">
        ${renderTopbar()}
        <div class="container">
          ${renderContent()}
        </div>
        ${renderFooter()}
      </div>
    </div>
    ${renderModal()}
  `;
  bindEvents();
};

const bindEvents = () => {
  document.querySelectorAll(".sidebar__link").forEach((button) => {
    button.addEventListener("click", () => {
      location.hash = button.dataset.route;
    });
  });

  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => {
      location.hash = button.dataset.route;
    });
  });

  const toggleSidebar = document.getElementById("toggle-sidebar");
  if (toggleSidebar) {
    toggleSidebar.addEventListener("click", () => {
      state.ui.sidebarCollapsed = !state.ui.sidebarCollapsed;
      renderApp();
    });
  }

  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      document.body.classList.toggle("dark");
      state.theme = document.body.classList.contains("dark") ? "dark" : "light";
      localStorage.setItem("trevo-theme", state.theme);
    });
  }

  const shareBtn = document.getElementById("share-btn");
  if (shareBtn) {
    shareBtn.addEventListener("click", () => {
      copyToClipboard(`Trevo 4 Folhas - Jogos do dia ${state.date}`);
    });
  }

  const dateSelect = document.getElementById("date-select");
  if (dateSelect) {
    dateSelect.addEventListener("change", (event) => {
      state.date = event.target.value;
      renderApp();
    });
  }

  const planSelect = document.getElementById("plan-select");
  if (planSelect) {
    planSelect.addEventListener("change", (event) => {
      state.plan = event.target.value;
      if (state.ui.topLimit > getPlanLimit()) {
        state.ui.topLimit = getPlanLimit();
        toast(`Seu plano libera até TOP ${getPlanLimit()}.`);
      }
      renderApp();
    });
  }

  document.querySelectorAll("[data-faq]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.faq);
      state.ui.faqOpen = state.ui.faqOpen === index ? -1 : index;
      renderApp();
    });
  });

  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selected.mode = button.dataset.mode;
      renderApp();
    });
  });

  document.querySelectorAll("#volante .ball").forEach((ball) => {
    ball.addEventListener("click", () => {
      const number = Number(ball.dataset.number);
      if (state.selected.mode === "select") {
        toggleSet(state.selected.picks, number);
      } else if (state.selected.mode === "fix") {
        toggleSet(state.selected.fixed, number);
      } else {
        toggleSet(state.selected.excluded, number);
      }
      renderApp();
    });
  });

  const clearVolante = document.getElementById("clear-volante");
  if (clearVolante) {
    clearVolante.addEventListener("click", () => {
      state.selected.picks.clear();
      state.selected.fixed.clear();
      state.selected.excluded.clear();
      renderApp();
    });
  }

  const copyVolante = document.getElementById("copy-volante");
  if (copyVolante) {
    copyVolante.addEventListener("click", () => {
      copyToClipboard(Array.from(state.selected.picks).map(formatNumber).join(" "));
    });
  }

  const pasteVolante = document.getElementById("paste-volante");
  if (pasteVolante) {
    pasteVolante.addEventListener("click", () => {
      const input = prompt("Cole as dezenas separadas por espaço");
      if (!input) return;
      const numbers = input
        .split(/\s+/)
        .map((num) => Number(num))
        .filter((num) => num >= 1 && num <= 25);
      state.selected.picks = new Set(numbers);
      renderApp();
    });
  }

  const generateGameButton = document.getElementById("generate-game");
  if (generateGameButton) {
    generateGameButton.addEventListener("click", () => {
      const fixed = Array.from(state.selected.fixed);
      const excluded = new Set(state.selected.excluded);
      const game = new Set(fixed);
      while (game.size < 15) {
        const num = Math.floor(Math.random() * 25) + 1;
        if (!excluded.has(num)) {
          game.add(num);
        }
      }
      const numbers = Array.from(game).sort((a, b) => a - b);
      const evens = numbers.filter((num) => num % 2 === 0).length;
      const odds = 15 - evens;
      const sumRange = numbers.reduce((acc, num) => acc + num, 0);
      const saved = {
        numbers,
        tags: {
          parity: `${odds}/${evens}`,
          sumRange,
        },
      };
      state.selected.savedGames.unshift(saved);
      state.selected.savedGames = state.selected.savedGames.slice(0, 10);
      renderApp();
    });
  }

  const saveGames = document.getElementById("save-games");
  if (saveGames) {
    saveGames.addEventListener("click", () => {
      toast("Jogos salvos (demo).\nProduto informativo e estatístico.");
    });
  }

  const exportGames = document.getElementById("export-games");
  if (exportGames) {
    exportGames.addEventListener("click", () => {
      const content = state.selected.savedGames.map((game) => game.numbers.map(formatNumber).join("-")).join("\n");
      downloadTxt("trevo4folhas-selecionados.txt", content);
    });
  }

  const clearGames = document.getElementById("clear-games");
  if (clearGames) {
    clearGames.addEventListener("click", () => {
      state.selected.savedGames = [];
      renderApp();
    });
  }

  document.querySelectorAll("[data-top]").forEach((button) => {
    button.addEventListener("click", () => {
      const top = Number(button.dataset.top);
      if (top > getPlanLimit()) {
        toast(`Seu plano libera até TOP ${getPlanLimit()}. Veja planos.`);
        state.ui.topLimit = getPlanLimit();
      } else {
        state.ui.topLimit = top;
      }
      renderApp();
    });
  });

  document.querySelectorAll("[data-parity]").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.ui.filters.parity = chip.dataset.parity;
      renderApp();
    });
  });

  document.querySelectorAll("[data-sum]").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.ui.filters.sumRange = chip.dataset.sum;
      renderApp();
    });
  });

  document.querySelectorAll("[data-primes]").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.ui.filters.primes = chip.dataset.primes;
      renderApp();
    });
  });

  document.querySelectorAll("[data-repeats]").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.ui.filters.repeats = chip.dataset.repeats;
      renderApp();
    });
  });

  const copyTop = document.getElementById("copy-top");
  if (copyTop) {
    copyTop.addEventListener("click", () => {
      const content = getTopGames().map((game) => game.numbers.map(formatNumber).join("-")).join("\n");
      copyToClipboard(content);
    });
  }

  const downloadTop = document.getElementById("download-top");
  if (downloadTop) {
    downloadTop.addEventListener("click", () => {
      const content = getTopGames().map((game) => game.numbers.map(formatNumber).join("-")).join("\n");
      downloadTxt(`trevo4folhas-top-${state.date}.txt`, content);
    });
  }

  const shareTop = document.getElementById("share-top");
  if (shareTop) {
    shareTop.addEventListener("click", () => {
      copyToClipboard(`Trevo 4 Folhas - TOP ${state.ui.topLimit} em ${state.date}`);
    });
  }

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => {
      const game = getTopGames().find((item) => item.rank === Number(button.dataset.copy));
      copyToClipboard(game.numbers.map(formatNumber).join("-"));
    });
  });

  document.querySelectorAll("[data-detail]").forEach((button) => {
    button.addEventListener("click", () => {
      const rank = Number(button.dataset.detail);
      const game = getTopGames().find((item) => item.rank === rank) || state.selected.savedGames[rank];
      if (!game) return;
      state.ui.modal = "details";
      state.ui.modalGame = game;
      renderApp();
    });
  });

  document.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", () => {
      const game = getTopGames().find((item) => item.rank === Number(button.dataset.add));
      if (game) {
        state.selected.savedGames.unshift(game);
        state.selected.savedGames = state.selected.savedGames.slice(0, 10);
        toast("Adicionado à lista selecionada (demo)." );
      }
    });
  });

  const checkGame = document.getElementById("check-game");
  if (checkGame) {
    checkGame.addEventListener("click", () => {
      const input = document.getElementById("check-input").value;
      const numbers = input
        .split(/\s+/)
        .map((num) => Number(num))
        .filter((num) => num >= 1 && num <= 25);
      const results = state.resultsByDate[state.date].numbers;
      const hits = numbers.filter((num) => results.includes(num));
      const resultContainer = document.getElementById("check-result");
      resultContainer.innerHTML = `
        <p><strong>${hits.length}</strong> acertos encontrados (demo).</p>
        <div class="balls">
          ${numbers
            .map(
              (num) => `<span class="ball ${hits.includes(num) ? "ball--hit" : "ball--miss"}">${formatNumber(num)}</span>`
            )
            .join("")}
        </div>
      `;
    });
  }

  const openPrize = document.getElementById("open-prize");
  if (openPrize) {
    openPrize.addEventListener("click", () => {
      state.ui.modal = "prize";
      renderApp();
    });
  }

  document.querySelectorAll("[data-plan]").forEach((button) => {
    button.addEventListener("click", () => {
      state.ui.modal = "checkout";
      state.ui.modalPlan = button.dataset.plan;
      renderApp();
    });
  });

  const loginButton = document.getElementById("login");
  if (loginButton) {
    loginButton.addEventListener("click", () => {
      state.user.email = document.getElementById("login-email").value || "assinante@demo.com";
      state.user.token = "demo-token";
      renderApp();
    });
  }

  const logoutButton = document.getElementById("logout");
  if (logoutButton) {
    logoutButton.addEventListener("click", () => {
      state.user = { email: "", token: "" };
      renderApp();
    });
  }

  const inviteButton = document.getElementById("invite");
  if (inviteButton) {
    inviteButton.addEventListener("click", () => {
      const code = Math.random().toString(36).slice(2, 8).toUpperCase();
      copyToClipboard(`https://trevo4folhas.com/convite/${code}`);
    });
  }

  document.querySelectorAll("[data-date]").forEach((button) => {
    button.addEventListener("click", () => {
      state.date = button.dataset.date;
      renderApp();
    });
  });

  const closeModal = document.getElementById("close-modal");
  if (closeModal) {
    closeModal.addEventListener("click", () => {
      state.ui.modal = null;
      renderApp();
    });
  }

  const copyModal = document.getElementById("copy-modal");
  if (copyModal) {
    copyModal.addEventListener("click", () => {
      const game = state.ui.modalGame;
      copyToClipboard(game.numbers.map(formatNumber).join("-"));
    });
  }
};

const toggleSet = (set, number) => {
  if (set.has(number)) {
    set.delete(number);
  } else {
    set.add(number);
  }
};

const initTheme = () => {
  const saved = localStorage.getItem("trevo-theme");
  if (saved === "dark") {
    document.body.classList.add("dark");
    state.theme = "dark";
  }
};

const init = () => {
  seedData();
  state.route = buildHashRoute();
  initTheme();
  renderApp();
};

window.addEventListener("hashchange", () => {
  state.route = buildHashRoute();
  renderApp();
});

init();

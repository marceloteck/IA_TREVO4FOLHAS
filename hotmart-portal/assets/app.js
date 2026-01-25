const App = (() => {
  const session = () => TrevoAuth.getSession();

  const formatCurrency = (value) =>
    Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const fillProfile = () => {
    const profileName = document.querySelector("[data-profile-name]");
    const profileEmail = document.querySelector("[data-profile-email]");
    const current = session();

    if (profileName) profileName.textContent = current?.name || "";
    if (profileEmail) profileEmail.textContent = current?.email || "";
  };

  const setActiveNav = () => {
    const page = document.body.dataset.page;
    document.querySelectorAll("[data-nav]").forEach((link) => {
      if (link.dataset.nav === page) {
        link.classList.add("active");
      }
    });
  };

  const handleAuthForms = () => {
    const loginForm = document.querySelector("[data-login-form]");
    if (loginForm) {
      loginForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const email = loginForm.querySelector("#login-email").value.trim();
        const password = loginForm.querySelector("#login-password").value.trim();
        const response = TrevoAuth.login({ email, password });
        const message = loginForm.querySelector("[data-message]");
        if (!response.ok) {
          message.textContent = response.message;
          message.className = "notice danger";
          return;
        }
        window.location.href = "dashboard.html";
      });
    }

    const registerForm = document.querySelector("[data-register-form]");
    if (registerForm) {
      registerForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const name = registerForm.querySelector("#register-name").value.trim();
        const email = registerForm.querySelector("#register-email").value.trim();
        const password = registerForm.querySelector("#register-password").value.trim();
        const response = TrevoAuth.register({ name, email, password });
        const message = registerForm.querySelector("[data-message]");
        if (!response.ok) {
          message.textContent = response.message;
          message.className = "notice danger";
          return;
        }
        window.location.href = "dashboard.html";
      });
    }

    const logoutBtn = document.querySelector("[data-logout]");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        TrevoAuth.logout();
        window.location.href = "index.html";
      });
    }
  };

  const renderDashboard = () => {
    const current = session();
    const payload = TrevoData.getPayload(current.email);
    const stats = TrevoData.computeStats(payload);

    document.querySelector("[data-stat-games]").textContent = stats.totalGames;
    document.querySelector("[data-stat-best-hit]").textContent = `${stats.bestHit} pontos`;
    document.querySelector("[data-stat-avg-hit]").textContent = `${stats.avgHit} pontos`;
    document.querySelector("[data-stat-balance]").textContent = formatCurrency(stats.balance);

    const list = document.querySelector("[data-recent-games]");
    list.innerHTML = "";

    if (payload.games.length === 0) {
      list.innerHTML = "<p class=\"helper\">Cadastre seu primeiro jogo para acompanhar os resultados.</p>";
      return;
    }

    payload.games.slice(0, 3).forEach((game) => {
      const item = document.createElement("div");
      item.className = "card";
      item.innerHTML = `
        <div class="flex" style="justify-content: space-between;">
          <div>
            <strong>${game.title}</strong>
            <p class="helper">${game.date} • ${game.contest}</p>
          </div>
          <span class="chip">${game.hits} acertos</span>
        </div>
        <p class="helper" style="margin-top: 12px;">Números jogados: ${game.numbers}</p>
        <p class="helper">Faltaram: ${game.missed}</p>
      `;
      list.appendChild(item);
    });
  };

  const handleGamesPage = () => {
    const current = session();
    const form = document.querySelector("[data-game-form]");
    const tableBody = document.querySelector("[data-games-table]");

    const renderTable = () => {
      const payload = TrevoData.getPayload(current.email);
      tableBody.innerHTML = "";

      payload.games.forEach((game) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${game.date}</td>
          <td>${game.title}</td>
          <td>${game.contest}</td>
          <td>${game.hits}</td>
          <td>${formatCurrency(game.prize)}</td>
          <td>${game.missed}</td>
        `;
        tableBody.appendChild(row);
      });
    };

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form));
      TrevoData.addGame(current.email, {
        date: data.date,
        title: data.title,
        contest: data.contest,
        numbers: data.numbers,
        hits: data.hits,
        missed: data.missed,
        prize: data.prize,
        notes: data.notes,
      });
      form.reset();
      renderTable();
    });

    renderTable();
  };

  const handleStrategiesPage = () => {
    const current = session();
    const strategyForm = document.querySelector("[data-strategy-form]");
    const planForm = document.querySelector("[data-plan-form]");
    const strategyList = document.querySelector("[data-strategy-list]");
    const planList = document.querySelector("[data-plan-list]");

    const render = () => {
      const payload = TrevoData.getPayload(current.email);
      strategyList.innerHTML = "";
      planList.innerHTML = "";

      payload.strategies.forEach((strategy) => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          <strong>${strategy.name}</strong>
          <p class="helper">Foco: ${strategy.focus}</p>
          <p>${strategy.description}</p>
        `;
        strategyList.appendChild(card);
      });

      payload.monthlyPlans.forEach((plan) => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          <strong>${plan.month}</strong>
          <p class="helper">Meta: ${plan.goal}</p>
          <p>${plan.actions}</p>
        `;
        planList.appendChild(card);
      });
    };

    strategyForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(strategyForm));
      TrevoData.addStrategy(current.email, data);
      strategyForm.reset();
      render();
    });

    planForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(planForm));
      TrevoData.addMonthlyPlan(current.email, data);
      planForm.reset();
      render();
    });

    render();
  };

  const handleReportsPage = () => {
    const current = session();
    const expenseForm = document.querySelector("[data-expense-form]");
    const list = document.querySelector("[data-expense-list]");
    const statsContainer = document.querySelector("[data-report-stats]");

    const render = () => {
      const payload = TrevoData.getPayload(current.email);
      const stats = TrevoData.computeStats(payload);

      statsContainer.innerHTML = `
        <div class="stat"><span>Total investido</span><strong>${formatCurrency(stats.totalSpent)}</strong></div>
        <div class="stat"><span>Total em prêmios</span><strong>${formatCurrency(stats.totalPrize)}</strong></div>
        <div class="stat"><span>Saldo atual</span><strong>${formatCurrency(stats.balance)}</strong></div>
      `;

      list.innerHTML = "";
      payload.expenses.forEach((item) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${item.date}</td>
          <td>${item.category}</td>
          <td>${item.description}</td>
          <td>${formatCurrency(item.amount)}</td>
        `;
        list.appendChild(row);
      });
    };

    expenseForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(expenseForm));
      TrevoData.addExpense(current.email, data);
      expenseForm.reset();
      render();
    });

    render();
  };

  const init = () => {
    fillProfile();
    setActiveNav();
    handleAuthForms();

    const page = document.body.dataset.page;
    if (["dashboard", "games", "strategies", "reports"].includes(page)) {
      TrevoAuth.requireAuth();
    }

    if (["dashboard", "games", "strategies", "reports"].includes(page) && !session()) {
      return;
    }

    if (page === "dashboard") {
      renderDashboard();
    }

    if (page === "games") {
      handleGamesPage();
    }

    if (page === "strategies") {
      handleStrategiesPage();
    }

    if (page === "reports") {
      handleReportsPage();
    }
  };

  return { init };
})();

window.addEventListener("DOMContentLoaded", App.init);

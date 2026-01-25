const TrevoData = (() => {
  const storageKey = (email) => `trevo_data_${email}`;

  const defaultPayload = () => ({
    games: [],
    strategies: [],
    monthlyPlans: [],
    expenses: [],
  });

  const getPayload = (email) => {
    const data = localStorage.getItem(storageKey(email));
    if (!data) {
      const payload = defaultPayload();
      localStorage.setItem(storageKey(email), JSON.stringify(payload));
      return payload;
    }
    return JSON.parse(data);
  };

  const savePayload = (email, payload) => {
    localStorage.setItem(storageKey(email), JSON.stringify(payload));
  };

  const addGame = (email, game) => {
    const payload = getPayload(email);
    payload.games.unshift({ id: crypto.randomUUID(), ...game });
    savePayload(email, payload);
  };

  const addStrategy = (email, strategy) => {
    const payload = getPayload(email);
    payload.strategies.unshift({ id: crypto.randomUUID(), ...strategy });
    savePayload(email, payload);
  };

  const addMonthlyPlan = (email, plan) => {
    const payload = getPayload(email);
    payload.monthlyPlans.unshift({ id: crypto.randomUUID(), ...plan });
    savePayload(email, payload);
  };

  const addExpense = (email, expense) => {
    const payload = getPayload(email);
    payload.expenses.unshift({ id: crypto.randomUUID(), ...expense });
    savePayload(email, payload);
  };

  const computeStats = (payload) => {
    const totalSpent = payload.expenses.reduce((acc, item) => acc + Number(item.amount || 0), 0);
    const totalPrize = payload.games.reduce((acc, item) => acc + Number(item.prize || 0), 0);
    const bestHit = payload.games.reduce((acc, item) => Math.max(acc, Number(item.hits || 0)), 0);
    const avgHit = payload.games.length
      ? (payload.games.reduce((acc, item) => acc + Number(item.hits || 0), 0) / payload.games.length).toFixed(1)
      : "0";

    return {
      totalSpent,
      totalPrize,
      balance: totalPrize - totalSpent,
      bestHit,
      avgHit,
      totalGames: payload.games.length,
    };
  };

  return {
    getPayload,
    addGame,
    addStrategy,
    addMonthlyPlan,
    addExpense,
    computeStats,
  };
})();

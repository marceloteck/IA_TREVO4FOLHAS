const TrevoAuth = (() => {
  const USERS_KEY = "trevo_users";
  const SESSION_KEY = "trevo_session";

  const getUsers = () => JSON.parse(localStorage.getItem(USERS_KEY) || "[]");
  const saveUsers = (users) => localStorage.setItem(USERS_KEY, JSON.stringify(users));

  const getSession = () => {
    const session = localStorage.getItem(SESSION_KEY);
    return session ? JSON.parse(session) : null;
  };

  const setSession = (session) => localStorage.setItem(SESSION_KEY, JSON.stringify(session));

  const register = (payload) => {
    const users = getUsers();
    if (users.some((user) => user.email === payload.email)) {
      return { ok: false, message: "Este e-mail já está cadastrado." };
    }

    const newUser = {
      id: crypto.randomUUID(),
      name: payload.name,
      email: payload.email,
      password: payload.password,
      createdAt: new Date().toISOString(),
    };

    users.push(newUser);
    saveUsers(users);
    setSession({ email: newUser.email, name: newUser.name, id: newUser.id });
    return { ok: true };
  };

  const login = (payload) => {
    const users = getUsers();
    const user = users.find((item) => item.email === payload.email);

    if (!user || user.password !== payload.password) {
      return { ok: false, message: "Login ou senha inválidos." };
    }

    setSession({ email: user.email, name: user.name, id: user.id });
    return { ok: true };
  };

  const logout = () => localStorage.removeItem(SESSION_KEY);

  const requireAuth = () => {
    if (!getSession()) {
      window.location.href = "login.html";
    }
  };

  return { getSession, register, login, logout, requireAuth };
})();

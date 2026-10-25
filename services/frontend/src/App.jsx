import { useCallback, useEffect, useRef, useState } from "react";

// Tous les appels passent par /api : Nginx les renvoie vers le WAF (seule porte d'entree).
const API = "/api";

function parseJwt(token) {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part));
  } catch {
    return null;
  }
}

function explain(status) {
  if (status === 401) return "Session expirée ou invalide : reconnectez-vous";
  if (status === 403) return "Bloquée par la sécurité (WAF ou IP bloquée)";
  if (status === 422) return "Données invalides";
  if (status >= 500) return `Service indisponible (HTTP ${status})`;
  return `Refusée (HTTP ${status})`;
}

// Interroge /health toutes les 3 s : c'est l'indicateur "la plateforme marche-t-elle ?"
function useHealth() {
  const [health, setHealth] = useState({ ok: null, ms: null });
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      const t0 = performance.now();
      try {
        const r = await fetch(`${API}/health`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
        if (!stop) setHealth({ ok: r.ok, ms: Math.round(performance.now() - t0) });
      } catch {
        if (!stop) setHealth({ ok: false, ms: null });
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, []);
  return health;
}

function StatusBadge({ health }) {
  const base = "inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium";
  if (health.ok === null) return <span className={`${base} bg-slate-200 text-slate-600`}>Vérification…</span>;
  if (health.ok)
    return (
      <span className={`${base} bg-emerald-100 text-emerald-800`}>
        <span className="h-2 w-2 rounded-full bg-emerald-500" />
        Plateforme opérationnelle{health.ms !== null && ` · ${health.ms} ms`}
      </span>
    );
  return (
    <span className={`${base} bg-red-100 text-red-800`}>
      <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
      Plateforme indisponible
    </span>
  );
}

export default function App() {
  const health = useHealth();

  // Le jeton reste en memoire (pas de localStorage) : il disparait quand on ferme l'onglet.
  const [token, setToken] = useState(null);
  const tokenRef = useRef(null);
  const [user, setUser] = useState("");
  const [now, setNow] = useState(Date.now());
  const [loginError, setLoginError] = useState("");
  const [loginForm, setLoginForm] = useState({ username: "alice", password: "" });

  const [form, setForm] = useState({ from_account: "FR01", to_account: "FR02", amount: "25.00" });
  const [journal, setJournal] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);

  const exp = token ? parseJwt(token)?.exp : null;
  const secondsLeft = exp ? Math.max(0, Math.round(exp - now / 1000)) : 0;

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const logout = useCallback((message = "") => {
    tokenRef.current = null;
    setToken(null);
    setUser("");
    setDemo(false);
    setLoginError(message);
  }, []);

  useEffect(() => {
    if (token && exp && now / 1000 >= exp) logout("Session expirée (jeton de 15 minutes) : reconnectez-vous");
  }, [now, token, exp, logout]);

  const addJournal = (entry) =>
    setJournal((j) => [{ ...entry, time: new Date().toLocaleTimeString("fr-FR") }, ...j].slice(0, 12));

  async function login(e) {
    e.preventDefault();
    setLoginError("");
    setBusy(true);
    try {
      const r = await fetch(`${API}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(loginForm),
        signal: AbortSignal.timeout(5000),
      });
      if (r.status === 200) {
        const data = await r.json();
        tokenRef.current = data.access_token;
        setToken(data.access_token);
        setUser(loginForm.username);
        setLoginForm((f) => ({ ...f, password: "" }));
      } else if (r.status === 401) {
        setLoginError("Identifiants invalides");
      } else {
        setLoginError(explain(r.status));
      }
    } catch {
      setLoginError("Service injoignable (pas de réponse)");
    } finally {
      setBusy(false);
    }
  }

  const loadTransactions = useCallback(async () => {
    if (!tokenRef.current) return;
    try {
      const r = await fetch(`${API}/transactions?limit=10`, {
        headers: { Authorization: `Bearer ${tokenRef.current}` },
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });
      if (r.ok) setTransactions(await r.json());
    } catch {
      /* la liste reste celle d'avant : l'indicateur de sante montre deja le probleme */
    }
  }, []);

  const sendTransaction = useCallback(
    async (payload, auto = false) => {
      const t0 = performance.now();
      let entry;
      try {
        const r = await fetch(`${API}/transactions`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenRef.current}` },
          body: JSON.stringify(payload),
          signal: AbortSignal.timeout(5000),
        });
        const ms = Math.round(performance.now() - t0);
        const data = await r.json().catch(() => ({}));
        entry = r.status === 201 ? { ok: true, text: `Acceptée n°${data.id}`, ms } : { ok: false, text: explain(r.status), ms };
        if (r.status === 401) logout("Session expirée ou invalide : reconnectez-vous");
      } catch {
        entry = { ok: false, text: "Service injoignable (pas de réponse)", ms: null };
      }
      addJournal({ ...entry, auto });
      if (entry.ok) loadTransactions();
      return entry;
    },
    [loadTransactions, logout]
  );

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    await sendTransaction({ ...form, amount: Number(form.amount) });
    setBusy(false);
  }

  // Mode demo : une petite transaction automatique toutes les 2 s, pour voir
  // en direct "ca passe -> ca echoue -> ca repasse" pendant l'incident.
  useEffect(() => {
    if (!demo || !token) return undefined;
    const id = setInterval(() => sendTransaction({ from_account: "DEMO01", to_account: "DEMO02", amount: 1 }, true), 2000);
    return () => clearInterval(id);
  }, [demo, token, sendTransaction]);

  useEffect(() => {
    if (token) loadTransactions();
  }, [token, loadTransactions]);

  const input = "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200";
  const button = "rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50";

  return (
    <div className="mx-auto max-w-5xl p-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">RESILIENCE-ALPHA</h1>
          <p className="text-sm text-slate-500">Plateforme de paiement fictive · simulation</p>
        </div>
        <StatusBadge health={health} />
      </header>

      {!token ? (
        <form onSubmit={login} className="mx-auto max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow">
          <h2 className="text-lg font-semibold">Connexion</h2>
          <label className="block text-sm">
            Utilisateur
            <input className={input} value={loginForm.username} autoComplete="username"
              onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })} />
          </label>
          <label className="block text-sm">
            Mot de passe
            <input className={input} type="password" value={loginForm.password} autoComplete="current-password"
              onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })} />
          </label>
          {loginError && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{loginError}</p>}
          <button className={`${button} w-full`} disabled={busy || !loginForm.password}>
            Se connecter
          </button>
        </form>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          <section className="space-y-4 rounded-2xl bg-white p-6 shadow">
            <div className="flex items-center justify-between text-sm text-slate-500">
              <span>Connecté : <b className="text-slate-800">{user}</b></span>
              <span>
                Session {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
                <button className="ml-3 text-blue-600 underline" onClick={() => logout("")}>Déconnexion</button>
              </span>
            </div>

            <form onSubmit={submit} className="space-y-3">
              <h2 className="text-lg font-semibold">Nouvelle transaction</h2>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm">Compte source
                  <input className={input} value={form.from_account} maxLength={34}
                    onChange={(e) => setForm({ ...form, from_account: e.target.value })} />
                </label>
                <label className="block text-sm">Compte destinataire
                  <input className={input} value={form.to_account} maxLength={34}
                    onChange={(e) => setForm({ ...form, to_account: e.target.value })} />
                </label>
              </div>
              <label className="block text-sm">Montant (€, 0,01 à 10 000)
                <input className={input} type="number" step="0.01" min="0.01" max="10000" value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })} />
              </label>
              <button className={button} disabled={busy}>Envoyer</button>
            </form>

            <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-slate-50 p-3 text-sm">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} />
              <span><b>Mode démo</b> : 1 transaction automatique toutes les 2 s</span>
            </label>
          </section>

          <section className="space-y-4">
            <div className="rounded-2xl bg-white p-6 shadow">
              <h2 className="mb-3 text-lg font-semibold">Journal des essais</h2>
              {journal.length === 0 ? (
                <p className="text-sm text-slate-400">Aucun essai pour l'instant.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {journal.map((j, i) => (
                    <li key={i} className={`flex items-center justify-between rounded px-2 py-1 ${j.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>
                      <span>{j.ok ? "✓" : "✗"} {j.text}{j.auto && <i className="ml-1 text-xs opacity-70">(auto)</i>}</span>
                      <span className="text-xs opacity-70">{j.time}{j.ms !== null && ` · ${j.ms} ms`}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-2xl bg-white p-6 shadow">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold">Dernières transactions</h2>
                <button className="text-sm text-blue-600 underline" onClick={loadTransactions}>Actualiser</button>
              </div>
              <table className="w-full text-left text-sm">
                <thead className="text-slate-500">
                  <tr><th className="py-1">N°</th><th>De</th><th>Vers</th><th className="text-right">Montant</th></tr>
                </thead>
                <tbody>
                  {transactions.map((t) => (
                    <tr key={t.id} className="border-t border-slate-100">
                      <td className="py-1">{t.id}</td><td>{t.from_account}</td><td>{t.to_account}</td>
                      <td className="text-right">{Number(t.amount).toFixed(2)} €</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

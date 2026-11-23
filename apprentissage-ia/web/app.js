(() => {
  "use strict";

  /* ============================================================
   * Helpers
   * ============================================================ */
  const TOKEN_KEY = "parcours.token";
  const TX_KEY = "parcours.lastTx";
  const BRAND = "Mon parcours";
  const LETTERS = ["A", "B", "C", "D"];

  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  const paragraphs = (text) => esc(text).split(/\n{2,}/).map((p) => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
  const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }) : "");
  const fmtShort = (iso) => (iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "");
  const money = (amount, currency) => `${Number(amount).toLocaleString("fr-FR")} ${currency}`;
  const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;

  const storage = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* private mode */ } },
  };

  const ICONS = {
    home: '<path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    book: '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v15H6.5A2.5 2.5 0 0 0 4 19.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.3L21 8"/><path d="M21 3v5h-5"/>',
    message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    trophy: '<path d="M8 21h8M12 17v4"/><path d="M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    check: '<path d="M5 13l4 4L19 7"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    flame: '<path d="M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 2 1 3 2 3 0-3-1-5 1-9.5z"/>',
    star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  };
  const icon = (name, cls = "") =>
    `<svg class="ico ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

  const ring = (percent, label) => {
    const r = 52, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, percent || 0));
    return `<div class="ring" role="img" aria-label="${esc(label)} : ${p} %">
      <svg viewBox="0 0 120 120"><circle class="ring-track" cx="60" cy="60" r="${r}" fill="none" stroke-width="10"/>
      <circle class="ring-value" cx="60" cy="60" r="${r}" fill="none" stroke-width="10" stroke-linecap="round"
        stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${(c * (1 - p / 100)).toFixed(2)}"/></svg>
      <div class="ring-label"><strong>${p} %</strong><span>${esc(label)}</span></div></div>`;
  };
  const bar = (percent, tone = "") =>
    `<div class="bar ${tone}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent || 0}"><i style="width:${Math.max(0, Math.min(100, percent || 0))}%"></i></div>`;

  /* ============================================================
   * API
   * ============================================================ */
  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  async function api(path, opts = {}) {
    const headers = {};
    const init = { method: opts.method || "GET", headers };
    if (opts.form) {
      init.body = opts.form;
    } else if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    const token = storage.get(TOKEN_KEY);
    if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`;

    let res;
    try {
      res = await fetch(path, init);
    } catch {
      throw new ApiError(0, "Connexion impossible. Vérifiez votre réseau et réessayez.");
    }
    if (res.status === 204) return null;
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      let message = data && data.detail;
      if (Array.isArray(message)) message = message.map((d) => d.msg).join(" ; ");
      throw new ApiError(res.status, message || "Une erreur est survenue. Réessayez.");
    }
    return data;
  }

  /* ============================================================
   * State and feedback
   * ============================================================ */
  const state = { me: null, countries: null, quiz: null, quizResult: null, reviewFeedback: null, explainAnswer: null };

  let toastTimer = null;
  function toast(message, kind = "") {
    const el = $("#toast");
    el.textContent = message;
    el.className = `toast ${kind}`;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 3800);
  }

  function setView(html) {
    $("#view").innerHTML = html;
    $("#view").focus({ preventScroll: true });
  }

  function pageHead(eyebrow, title, actions = "") {
    return `<header class="page-head"><div><p class="eyebrow">${esc(eyebrow)}</p><h1>${esc(title)}</h1></div>${actions ? `<div class="row-actions">${actions}</div>` : ""}</header>`;
  }

  function emptyState(title, text, action = "") {
    return `<section class="card empty"><h2>${esc(title)}</h2><p>${esc(text)}</p>${action ? `<div style="margin-top:14px">${action}</div>` : ""}</section>`;
  }

  function errorState(error) {
    return `<section class="card empty"><h2>Un problème est survenu</h2><p class="error-text">${esc(error.message || error)}</p>
      <div style="margin-top:14px"><button class="btn ghost" data-act="reload">Réessayer</button></div></section>`;
  }

  /* ============================================================
   * Navigation
   * ============================================================ */
  const NAV = [
    { route: "accueil", label: "Accueil", icon: "home" },
    { route: "cours", label: "Mes cours", icon: "book" },
    { route: "revisions", label: "Révisions", icon: "refresh" },
    { route: "explications", label: "Explications", icon: "message" },
    { route: "statistiques", label: "Statistiques", icon: "chart" },
    { route: "recompenses", label: "Récompenses", icon: "trophy" },
    { route: "profil", label: "Profil", icon: "user" },
  ];
  const TABS = ["accueil", "cours", "statistiques", "recompenses", "profil"];

  function go(hash) {
    if (location.hash === `#/${hash}`) route();
    else location.hash = `/${hash}`;
  }

  function renderChrome(current) {
    const sidebar = $("#sidebar");
    const tabbar = $("#tabbar");
    const authed = Boolean(state.me);
    sidebar.hidden = !authed;
    tabbar.hidden = !authed;
    if (!authed) return;
    sidebar.innerHTML = `
      <div class="brand"><span class="brand-mark">${icon("book")}</span>${BRAND}</div>
      ${NAV.map((n) => `<a class="nav-link" href="#/${n.route}" ${current === n.route ? 'aria-current="page"' : ""}>${icon(n.icon)}<span>${n.label}</span></a>`).join("")}
      <div class="sidebar-foot">${esc(state.me.first_name)} ${esc(state.me.last_name)}<br><button class="btn small ghost" style="margin-top:10px;width:100%" data-act="logout">${icon("logout")} Se déconnecter</button></div>`;
    tabbar.innerHTML = NAV.filter((n) => TABS.includes(n.route)).map((n) =>
      `<a class="tab" href="#/${n.route}" ${current === n.route ? 'aria-current="page"' : ""}>${icon(n.icon)}<span>${n.label}</span></a>`).join("");
  }

  const VIEWS = {
    accueil: viewHome,
    cours: viewCourses,
    revisions: viewReviews,
    explications: viewExplain,
    statistiques: viewStats,
    recompenses: viewRewards,
    profil: viewProfile,
    connexion: viewLogin,
    inscription: viewRegister,
  };
  const PUBLIC = ["connexion", "inscription"];

  async function route() {
    const [name = "accueil", ...params] = location.hash.replace(/^#\/?/, "").split("/");
    const authed = Boolean(storage.get(TOKEN_KEY));

    if (!authed && !PUBLIC.includes(name)) return go("connexion");
    if (authed && PUBLIC.includes(name)) return go("accueil");

    if (authed && !state.me) {
      try { state.me = await api("/me"); }
      catch { storage.set(TOKEN_KEY, null); state.me = null; return go("connexion"); }
    }

    const current = name === "quiz" ? "cours" : name === "cours" && params[0] ? "cours" : name;
    renderChrome(current);
    window.scrollTo({ top: 0 });

    try {
      if (name === "cours" && params[0]) await viewSubject(params[0]);
      else if (name === "quiz") await viewQuiz(params[0]);
      else await (VIEWS[name] || VIEWS.accueil)();
    } catch (error) {
      if (error.status === 401) { storage.set(TOKEN_KEY, null); state.me = null; return go("connexion"); }
      setView(pageHead("", "Oups") + errorState(error));
    }
  }

  /* ============================================================
   * Authentication
   * ============================================================ */
  async function viewLogin() {
    setView(`
      <section class="auth-wrap" style="padding:0;min-height:auto;margin-top:8vh">
        <div class="card auth-card">
          <div class="auth-brand"><span class="brand-mark">${icon("book")}</span>${BRAND}</div>
          <h1>Connexion</h1>
          <p class="muted" style="margin:6px 0 20px">Retrouvez votre parcours et vos révisions.</p>
          <form class="form" data-form="login">
            <div class="field"><label for="l-email">Adresse e-mail</label><input id="l-email" name="email" type="email" autocomplete="email" required></div>
            <div class="field"><label for="l-pass">Mot de passe</label><input id="l-pass" name="password" type="password" autocomplete="current-password" required></div>
            <p class="error-text" data-error hidden></p>
            <button class="btn block" type="submit">Se connecter</button>
          </form>
          <p class="small muted" style="margin-top:18px;text-align:center">Pas encore de compte ? <a href="#/inscription">Créer un compte</a></p>
        </div>
      </section>`);
  }

  async function viewRegister() {
    if (!state.countries) state.countries = await api("/countries", { auth: false });
    const countryOptions = state.countries.map((c) => `<option value="${esc(c.code)}">${esc(c.name)}</option>`).join("");
    setView(`
      <section class="auth-wrap" style="padding:0;min-height:auto;margin-top:4vh">
        <div class="card auth-card wide">
          <div class="auth-brand"><span class="brand-mark">${icon("book")}</span>${BRAND}</div>
          <h1>Créer mon compte</h1>
          <p class="muted" style="margin:6px 0 20px">Quelques informations pour adapter le contenu à votre filière.</p>
          <form class="form" data-form="register">
            <div class="form-grid">
              <div class="field"><label for="r-first">Prénom</label><input id="r-first" name="first_name" required maxlength="100"></div>
              <div class="field"><label for="r-last">Nom</label><input id="r-last" name="last_name" required maxlength="100"></div>
              <div class="field"><label for="r-email">Adresse e-mail</label><input id="r-email" name="email" type="email" autocomplete="email" required></div>
              <div class="field"><label for="r-pass">Mot de passe (8 caractères minimum)</label><input id="r-pass" name="password" type="password" minlength="8" autocomplete="new-password" required></div>
              <div class="field"><label for="r-country">Pays</label><select id="r-country" name="country" required>${countryOptions}</select></div>
              <div class="field"><label for="r-lang">Langue</label><select id="r-lang" name="language"><option value="fr">Français</option><option value="en">English</option></select></div>
              <div class="field"><label for="r-etab">Établissement</label><input id="r-etab" name="establishment" maxlength="200"></div>
              <div class="field"><label for="r-level">Niveau</label><input id="r-level" name="level" placeholder="ex. Licence 2" maxlength="100"></div>
              <div class="field"><label for="r-fil">Filière</label><input id="r-fil" name="filiere" maxlength="100"></div>
              <div class="field"><label for="r-spec">Spécialité</label><input id="r-spec" name="specialite" maxlength="100"></div>
            </div>
            <p class="error-text" data-error hidden></p>
            <button class="btn block" type="submit">Créer mon compte</button>
          </form>
          <p class="small muted" style="margin-top:18px;text-align:center">Déjà inscrit ? <a href="#/connexion">Se connecter</a></p>
        </div>
      </section>`);
  }

  /* ============================================================
   * Home
   * ============================================================ */
  async function viewHome() {
    const [dash, sub] = await Promise.all([api("/dashboard"), api("/billing/subscription")]);
    const subjects = dash.subjects;
    const covered = subjects.length ? Math.round(subjects.reduce((a, s) => a + s.covered_percent, 0) / subjects.length) : 0;
    const t = dash.totals;

    setView(`
      ${pageHead("Accueil", `Bonjour, ${state.me.first_name}`)}
      <section class="card hero-card">
        <div class="hero">
          ${ring(covered, "du programme couvert")}
          <div class="stack">
            <div class="hero-row">
              <div class="metric"><span class="section-title">${icon("flame")} Série</span><strong>${dash.streak_days} ${dash.streak_days > 1 ? "jours" : "jour"}</strong></div>
              <div class="metric"><span class="section-title">${icon("star")} Points</span><strong>${dash.xp.toLocaleString("fr-FR")} XP</strong></div>
            </div>
            <div class="stack" style="gap:10px">
              <p><strong>${dash.due_reviews}</strong> ${dash.due_reviews > 1 ? "questions à réviser" : "question à réviser"} aujourd'hui.</p>
              <p class="muted small">${esc(dash.recommendation)}</p>
              <div><a class="btn small" href="#/revisions">Ouvrir les révisions ${icon("arrow")}</a></div>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div class="row-between" style="margin-bottom:10px"><h2>Accès rapide</h2></div>
        <div class="grid-4">
          <a class="tile" href="#/cours"><span class="tile-icon">${icon("book")}</span>Mes cours<small>${subjects.length} ${subjects.length > 1 ? "matières" : "matière"}</small></a>
          <a class="tile t-sage" href="#/revisions"><span class="tile-icon">${icon("refresh")}</span>Révisions<small>${dash.due_reviews} à faire</small></a>
          <a class="tile t-plum" href="#/explications"><span class="tile-icon">${icon("message")}</span>Explications<small>Poser une question</small></a>
          <a class="tile t-amber" href="#/recompenses"><span class="tile-icon">${icon("trophy")}</span>Récompenses<small>Niveau ${dash.gamification_level}</small></a>
        </div>
      </section>

      <section class="grid-4">
        <div class="card metric"><span>Réponses données</span><strong>${t.attempts}</strong></div>
        <div class="card metric"><span>Taux de réussite</span><strong>${t.correct_percent == null ? "–" : t.correct_percent + " %"}</strong></div>
        <div class="card metric"><span>Quiz terminés</span><strong>${t.sessions}</strong></div>
        <div class="card metric"><span>Formule</span><strong>${planLabel(sub.plan)}</strong></div>
      </section>

      <section class="card">
        <div class="card-head"><h2 class="section-title">Activité récente</h2><a class="small" href="#/statistiques">Voir les statistiques</a></div>
        ${dash.recent_sessions.length ? `<ul class="list">${dash.recent_sessions.map(sessionRow).join("")}</ul>`
          : `<p class="muted">Vos quiz terminés apparaîtront ici.</p>`}
      </section>`);
  }

  function planLabel(plan) {
    return { free: "Gratuite", etudiant: "Étudiant", premium: "Premium" }[plan] || plan;
  }

  function sessionRow(s) {
    const tone = s.score_percent >= 70 ? "success" : s.score_percent >= 50 ? "" : "danger";
    return `<li class="row">
      <div class="row-main"><strong>${esc(s.title || "Quiz")}</strong>
        <p class="muted small">${s.kind === "evaluation" ? "Évaluation" : "Quiz"} · ${esc(fmtDate(s.submitted_at))}</p></div>
      <span class="badge ${tone}">${s.score_percent} %</span></li>`;
  }

  /* ============================================================
   * Courses
   * ============================================================ */
  async function viewCourses() {
    const subjects = await api("/subjects");
    const limitReached = state.me.plan === "free" && subjects.length >= 3;
    setView(`
      ${pageHead("Bibliothèque", "Mes cours", `<span class="badge">${subjects.length} ${subjects.length > 1 ? "matières" : "matière"}</span>`)}
      ${subjects.length ? `<section class="grid-2" style="grid-template-columns:1fr">
          ${subjects.map((s) => `<a class="card" href="#/cours/${s.id}" style="display:grid;gap:6px;color:inherit">
            <div class="row-between"><h2>${esc(s.name)}</h2>${s.semester ? `<span class="badge">S${s.semester}</span>` : ""}</div>
            <p class="muted small">${s.chapter_count} ${s.chapter_count > 1 ? "chapitres" : "chapitre"}</p></a>`).join("")}
        </section>` : emptyState("Aucune matière", "Créez votre première matière pour y ajouter vos chapitres et vos cours.")}
      <section class="card">
        <h2 class="section-title">${icon("plus")} Ajouter une matière</h2>
        ${limitReached ? `<p class="muted small" style="margin-top:8px">Votre formule gratuite permet 3 matières. Passez à l'abonnement Étudiant pour en ajouter davantage.</p>`
          : `<form class="inline-form" data-form="add-subject">
              <input name="name" type="text" required maxlength="200" placeholder="Nom de la matière, ex. Analyse 2">
              <select name="semester" style="max-width:150px"><option value="">Semestre</option>${[1, 2, 3, 4, 5, 6].map((n) => `<option value="${n}">Semestre ${n}</option>`).join("")}</select>
              <button class="btn" type="submit">Ajouter</button></form>`}
      </section>`);
  }

  async function viewSubject(id) {
    const [subject, docs, sub] = await Promise.all([
      api(`/subjects/${id}`), api(`/documents?subject_id=${id}`), api("/billing/subscription"),
    ]);
    const evalLimit = sub.limits.evaluations_per_week;
    const evalLeft = Math.max(0, evalLimit - sub.evaluations_this_week);
    setView(`
      ${pageHead(subject.semester ? `Semestre ${subject.semester}` : "Matière", subject.name,
        `<a class="btn ghost small" href="#/cours">Mes cours</a>`)}

      <section class="card">
        <div class="card-head">
          <h2 class="section-title">Chapitres</h2>
          <label class="small muted" style="display:flex;gap:8px;align-items:center">Difficulté
            <select id="difficulty" style="width:auto;min-height:36px"><option value="facile">Facile</option><option value="moyen" selected>Moyen</option><option value="difficile">Difficile</option></select></label>
        </div>
        ${subject.chapters.length ? `<ul class="list">${subject.chapters.map((c) => `
          <li class="row">
            <div class="row-main"><strong>${esc(c.title)}</strong>${c.notions ? `<p class="muted small">${esc(c.notions)}</p>` : ""}</div>
            <div class="row-actions">
              <button class="btn small" data-act="quiz-chapter" data-id="${c.id}">Quiz</button>
              <button class="btn small ghost" data-act="generate" data-id="${c.id}">Générer des questions</button>
              <button class="btn small danger" data-act="del-chapter" data-id="${c.id}" aria-label="Supprimer ${esc(c.title)}">${icon("x")}</button>
            </div></li>`).join("")}</ul>`
          : `<p class="muted">Ajoutez d'abord un chapitre. Vous pourrez ensuite générer des questions à partir de votre cours.</p>`}
        <form class="inline-form" data-form="add-chapter" data-subject="${subject.id}">
          <input name="title" type="text" required maxlength="200" placeholder="Titre du chapitre">
          <button class="btn ghost" type="submit">Ajouter le chapitre</button>
        </form>
      </section>

      <section class="grid-2">
        <div class="card">
          <h2 class="section-title">Quiz et évaluations</h2>
          <p class="muted small" style="margin:6px 0 16px">Un quiz porte sur 10 questions de la matière. Une évaluation compte dans votre limite hebdomadaire.</p>
          <div class="row-actions wrap">
            <button class="btn" data-act="quiz-subject" data-id="${subject.id}">Lancer un quiz</button>
            <button class="btn ghost" data-act="evaluation" data-id="${subject.id}" ${evalLeft === 0 ? "disabled" : ""}>Évaluation</button>
          </div>
          <p class="hint" style="margin-top:12px">Évaluations cette semaine : ${sub.evaluations_this_week} sur ${evalLimit}</p>
        </div>

        <div class="card">
          <h2 class="section-title">Documents du cours</h2>
          <form class="form" data-form="upload" data-subject="${subject.id}" style="margin:12px 0">
            <input name="file" type="file" accept=".pdf,.docx,.txt,.md" required>
            <select name="chapter_id"><option value="">Pas de chapitre précis</option>${subject.chapters.map((c) => `<option value="${c.id}">${esc(c.title)}</option>`).join("")}</select>
            <button class="btn" type="submit">${icon("upload")} Importer</button>
            <p class="hint">PDF, DOCX, TXT ou Markdown, 15 Mo maximum. Le contenu sert à personnaliser les questions et les explications.</p>
          </form>
          ${docs.length ? `<ul class="list">${docs.map((d) => `<li class="row">
              <div class="row-main">${icon("file", "")} <strong>${esc(d.filename)}</strong><p class="muted small">${d.char_count.toLocaleString("fr-FR")} caractères</p></div>
              <div class="row-actions">
                ${sub.limits.document_analysis ? `<button class="btn small ghost" data-act="analyze" data-id="${d.id}">Analyser</button>` : ""}
                <button class="btn small danger" data-act="del-doc" data-id="${d.id}" aria-label="Supprimer ${esc(d.filename)}">${icon("x")}</button>
              </div></li>`).join("")}</ul>` : `<p class="muted small">Aucun document importé.</p>`}
          <div id="analysis"></div>
        </div>
      </section>

      <section class="row-between" style="justify-content:flex-end">
        <button class="btn small danger" data-act="del-subject" data-id="${subject.id}">Supprimer cette matière</button>
      </section>`);
  }

  /* ============================================================
   * Quiz
   * ============================================================ */
  async function startQuiz(body) {
    const data = await api("/quizzes", { method: "POST", body });
    state.quiz = { id: String(data.session_id), kind: data.kind, questions: data.questions, index: 0, answers: {} };
    state.quizResult = null;
    go(`quiz/${data.session_id}`);
  }

  async function viewQuiz(id) {
    if (state.quizResult && String(state.quizResult.session_id) === String(id)) return showQuizResult(state.quizResult);
    if (!state.quiz || state.quiz.id !== String(id)) {
      return setView(pageHead("Quiz", "Session terminée") + emptyState(
        "Cette session n'est plus disponible",
        "Les quiz sont conservés le temps de la session. Relancez-en un depuis votre matière.",
        `<a class="btn" href="#/cours">Mes cours</a>`));
    }
    const q = state.quiz;
    const question = q.questions[q.index];
    const chosen = q.answers[question.id];
    const last = q.index === q.questions.length - 1;
    const answered = Object.keys(q.answers).length;

    setView(`
      ${pageHead(q.kind === "evaluation" ? "Évaluation" : "Quiz", `Question ${q.index + 1} sur ${q.questions.length}`,
        `<button class="btn ghost small" data-act="quit-quiz">Quitter</button>`)}
      <section class="card">
        <p class="hint">${esc(question.difficulty)}</p>
        <h2 class="question">${esc(question.question)}</h2>
        <div class="choices" role="group" aria-label="Réponses possibles">
          ${question.choices.map((choice, i) => `
            <button class="choice" data-act="pick" data-question="${question.id}" data-choice="${i}" aria-pressed="${chosen === i}">
              <span class="letter">${LETTERS[i]}</span><span>${esc(choice)}</span></button>`).join("")}
        </div>
        <div class="progress-steps" aria-hidden="true">${q.questions.map((_, i) => `<i class="${q.answers[q.questions[i].id] !== undefined ? "done" : ""}"></i>`).join("")}</div>
        <div class="actions-bar">
          <button class="btn ghost" data-act="quiz-prev" ${q.index === 0 ? "disabled" : ""}>Précédente</button>
          ${last
            ? `<button class="btn success" data-act="quiz-submit">Terminer et corriger</button>`
            : `<button class="btn" data-act="quiz-next">Suivante ${icon("arrow")}</button>`}
        </div>
        <p class="hint" style="margin-top:12px;text-align:right">${answered} réponse(s) sur ${q.questions.length}</p>
      </section>`);
  }

  function showQuizResult(r) {
    const tone = r.score_percent >= 70 ? "success" : r.score_percent >= 50 ? "" : "danger";
    setView(`
      ${pageHead(r.kind === "evaluation" ? "Évaluation terminée" : "Quiz terminé", `${r.score_percent} % de réussite`)}
      <section class="card hero">
        ${ring(r.score_percent, "réussite")}
        <div class="stack">
          <p><strong>${r.correct}</strong> bonne(s) réponse(s) sur ${r.total}.</p>
          <p class="muted">+${r.xp_gained} XP gagnés. Les questions manquées reviendront dans vos révisions.</p>
          <div class="row-actions"><a class="btn" href="#/cours">Retour à mes cours</a><a class="btn ghost" href="#/revisions">Réviser</a></div>
        </div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Corrections</h2><span class="badge ${tone}">${r.correct} / ${r.total}</span></div>
        <ol class="stack" style="padding-left:0;list-style:none">
          ${r.results.map((x, i) => `<li class="card" style="box-shadow:none;background:var(--bg-elev)">
            <div class="row-between"><strong>${i + 1}. ${esc(x.question)}</strong>
              <span class="badge ${x.is_correct ? "success" : "danger"}">${x.is_correct ? "Juste" : "À revoir"}</span></div>
            <div class="stack" style="margin-top:10px;gap:6px">${x.choices.map((c, j) => `
              <div class="small ${j === x.correct_index ? "" : "muted"}" style="${j === x.correct_index ? "color:var(--success)" : ""}">
                ${LETTERS[j]}. ${esc(c)}${j === x.correct_index ? " ✓" : ""}${x.chosen_index === j && !x.is_correct ? " (votre réponse)" : ""}</div>`).join("")}</div>
            <div class="explain text-block">${esc(x.explanation)}</div></li>`).join("")}
        </ol>
      </section>`);
  }

  /* ============================================================
   * Reviews
   * ============================================================ */
  async function viewReviews() {
    const data = await api("/reviews/due");
    const feedback = state.reviewFeedback;
    state.reviewFeedback = null;
    let body;
    if (feedback) {
      body = `<section class="card">
        <div class="row-between"><span class="badge ${feedback.result.is_correct ? "success" : "danger"}">${feedback.result.is_correct ? "Bonne réponse" : "Réponse incorrecte"}</span>
          <span class="muted small">Prochaine révision dans ${feedback.result.interval_days} ${feedback.result.interval_days > 1 ? "jours" : "jour"}</span></div>
        <h2 class="question" style="margin-top:12px">${esc(feedback.question)}</h2>
        <div class="explain text-block">${esc(feedback.result.explanation)}</div>
        <div class="actions-bar"><span></span><button class="btn" data-act="reload">Question suivante ${icon("arrow")}</button></div></section>`;
    } else if (!data.questions.length) {
      body = emptyState("Rien à réviser", "Vos révisions se remplissent après vos quiz : les questions manquées reviennent ici au bon moment.",
        `<a class="btn" href="#/cours">Lancer un quiz</a>`);
    } else {
      const q = data.questions[0];
      body = `<section class="card">
        <div class="row-between"><span class="badge accent">${data.due_count} à réviser</span></div>
        <h2 class="question" style="margin-top:12px">${esc(q.question)}</h2>
        <div class="choices">${q.choices.map((c, i) => `
          <button class="choice" data-act="review-answer" data-exercise="${q.id}" data-choice="${i}">
            <span class="letter">${LETTERS[i]}</span><span>${esc(c)}</span></button>`).join("")}</div></section>`;
    }
    setView(`${pageHead("Révisions", "À revoir aujourd'hui")}${body}`);
  }

  /* ============================================================
   * Explanations (tutor)
   * ============================================================ */
  async function viewExplain() {
    const subjects = await api("/subjects");
    const answer = state.explainAnswer;
    state.explainAnswer = null;
    setView(`
      ${pageHead("Explications", "Poser une question")}
      <section class="card">
        <p class="muted small" style="margin-bottom:14px">Posez une question sur un point du cours. Si vous avez importé vos documents, la réponse s'appuie sur eux.</p>
        <form class="form" data-form="explain">
          <div class="field"><label for="ex-subject">Matière (facultatif)</label>
            <select id="ex-subject" name="subject_id"><option value="">Toutes mes matières</option>${subjects.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select></div>
          <div class="field"><label for="ex-q">Votre question</label>
            <textarea id="ex-q" name="question" required minlength="3" maxlength="1000" placeholder="Ex. Pourquoi la dérivée d'un produit ne se calcule-t-elle pas comme un produit des dérivées ?"></textarea></div>
          <p class="error-text" data-error hidden></p>
          <div><button class="btn" type="submit">Obtenir une explication</button></div>
        </form>
      </section>
      ${answer ? `<section class="card"><div class="card-head"><h2>Réponse</h2>
          <span class="badge ${answer.source_chunk_ids.length ? "success" : ""}">${answer.source_chunk_ids.length ? "Appuyée sur vos documents" : "Réponse générale"}</span></div>
          <div class="text-block" style="line-height:1.65">${paragraphs(answer.answer)}</div></section>` : ""}`);
  }

  /* ============================================================
   * Statistics and rewards
   * ============================================================ */
  async function viewStats() {
    const [dash, history] = await Promise.all([api("/dashboard"), api("/quizzes")]);
    const t = dash.totals;
    setView(`
      ${pageHead("Statistiques", "Votre progression")}
      <section class="grid-4">
        <div class="card metric"><span>Réponses données</span><strong>${t.attempts}</strong></div>
        <div class="card metric"><span>Taux de réussite</span><strong>${t.correct_percent == null ? "–" : t.correct_percent + " %"}</strong></div>
        <div class="card metric"><span>Quiz terminés</span><strong>${t.sessions}</strong></div>
        <div class="card metric"><span>Révisions en attente</span><strong>${dash.due_reviews}</strong></div>
      </section>
      <section class="card">
        <h2 class="section-title">Par matière</h2>
        ${dash.subjects.length ? `<ul class="list" style="margin-top:12px">${dash.subjects.map((s) => `
          <li class="row" style="display:grid;gap:10px">
            <div class="row-between" style="width:100%"><strong>${esc(s.name)}</strong><span class="muted small">${s.questions} questions</span></div>
            <div class="stack" style="width:100%;gap:6px">
              <div class="small muted">Couverture ${s.covered_percent} %</div>${bar(s.covered_percent)}
              <div class="small muted" style="margin-top:6px">Précision ${s.accuracy_percent == null ? "–" : s.accuracy_percent + " %"}</div>
              ${s.accuracy_percent == null ? "" : bar(s.accuracy_percent, s.accuracy_percent >= 70 ? "success" : s.accuracy_percent < 50 ? "warning" : "")}
            </div></li>`).join("")}</ul>` : `<p class="muted">Vos statistiques apparaîtront après vos premiers quiz.</p>`}
      </section>
      <section class="grid-2">
        <div class="card">
          <h2 class="section-title">Chapitres à travailler</h2>
          ${dash.weakest_chapters.length ? `<ul class="list" style="margin-top:12px">${dash.weakest_chapters.map((c) => `
            <li class="row"><div class="row-main"><strong>${esc(c.title)}</strong><p class="muted small">${c.attempts} réponses</p></div>
            <span class="badge danger">${c.accuracy_percent} %</span></li>`).join("")}</ul>`
            : `<p class="muted" style="margin-top:10px">Il faut au moins 3 réponses dans un chapitre pour le classer.</p>`}
        </div>
        <div class="card">
          <h2 class="section-title">Historique</h2>
          ${history.length ? `<ul class="list" style="margin-top:12px">${history.map(sessionRow).join("")}</ul>`
            : `<p class="muted" style="margin-top:10px">Aucun quiz terminé pour le moment.</p>`}
        </div>
      </section>`);
  }

  async function viewRewards() {
    const dash = await api("/dashboard");
    const into = dash.xp % 100;
    setView(`
      ${pageHead("Récompenses", "Votre niveau")}
      <section class="card hero">
        <div class="ring" role="img" aria-label="Niveau ${dash.gamification_level}">
          <svg viewBox="0 0 120 120"><circle class="ring-track" cx="60" cy="60" r="52" fill="none" stroke-width="10"/>
          <circle class="ring-value" cx="60" cy="60" r="52" fill="none" stroke-width="10" stroke-linecap="round"
            stroke-dasharray="326.73" stroke-dashoffset="${(326.73 * (1 - into / 100)).toFixed(2)}"/></svg>
          <div class="ring-label"><strong>${dash.gamification_level}</strong><span>niveau</span></div></div>
        <div class="stack">
          <p><strong>${dash.xp.toLocaleString("fr-FR")} XP</strong> au total.</p>
          <p class="muted">Encore ${dash.xp_to_next_level} XP pour passer au niveau ${dash.gamification_level + 1}.</p>
          <p class="muted small">Une bonne réponse rapporte 10 XP, une évaluation réussie 15 XP. Chaque jour où vous répondez à au moins une question prolonge votre série.</p>
        </div>
      </section>
      <section class="grid-4">
        <div class="card metric"><span class="section-title">${icon("flame")} Série</span><strong>${dash.streak_days} ${dash.streak_days > 1 ? "jours" : "jour"}</strong></div>
        <div class="card metric"><span class="section-title">${icon("star")} Points XP</span><strong>${dash.xp.toLocaleString("fr-FR")}</strong></div>
        <div class="card metric"><span class="section-title">${icon("target")} Niveau</span><strong>${dash.gamification_level}</strong></div>
        <div class="card metric"><span class="section-title">${icon("clock")} À réviser</span><strong>${dash.due_reviews}</strong></div>
      </section>`);
  }

  /* ============================================================
   * Profile and subscription
   * ============================================================ */
  async function viewProfile() {
    const [me, catalog, sub, countries] = await Promise.all([
      api("/me"), api("/billing/catalog"), api("/billing/subscription"),
      state.countries ? Promise.resolve(state.countries) : api("/countries", { auth: false }),
    ]);
    state.me = me;
    state.countries = countries;
    const pending = storage.get(TX_KEY);
    const countryOptions = countries.map((c) => `<option value="${esc(c.code)}" ${c.code === me.country ? "selected" : ""}>${esc(c.name)}</option>`).join("");
    const products = catalog.products.filter((p) => p.kind === "plan");
    const packs = catalog.products.filter((p) => p.kind === "credits");
    const plan = sub.plan;

    setView(`
      ${pageHead("Profil", `${me.first_name} ${me.last_name}`)}

      <section class="card">
        <div class="card-head"><h2>Abonnement</h2><span class="badge ${plan === "free" ? "" : "success"}">${planLabel(plan)}</span></div>
        <div class="grid-4" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr))">
          <div class="metric"><span>Expire le</span><strong style="font-size:17px">${sub.expires_at ? esc(fmtDate(sub.expires_at)) : "–"}</strong></div>
          <div class="metric"><span>Crédits disponibles</span><strong>${sub.ai_credits}</strong></div>
          <div class="metric"><span>Actions d'apprentissage par jour</span><strong>${sub.limits.ai_ops_per_day}</strong></div>
        </div>
        ${pending ? `<div class="row" style="margin-top:14px"><span class="small">Un paiement est en cours de vérification.</span>
          <button class="btn small ghost" data-act="check-payment">Vérifier mon paiement</button></div>` : ""}
      </section>

      <section>
        <h2 style="margin:4px 0 10px">Formules</h2>
        <div class="grid-4" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
          ${[
            { code: "free", name: "Gratuite", price: 0, items: ["3 matières", "5 explications ou générations par jour", "1 évaluation par semaine"] },
            { code: "etudiant", name: "Étudiant", items: ["Matières illimitées", "30 explications ou générations par jour", "5 évaluations par semaine"] },
            { code: "premium", name: "Premium", items: ["100 explications ou générations par jour", "Analyse de documents", "5 évaluations par semaine"] },
          ].map((p) => {
            const offer = products.find((x) => x.plan === p.code && x.days === 30);
            const price = p.code === "free" ? 0 : offer ? offer.price : null;
            const current = plan === p.code;
            return `<div class="card plan ${current ? "current" : ""}">
              <div class="row-between"><h3>${p.name}</h3>${current ? '<span class="badge success">Actuelle</span>' : ""}</div>
              <div class="price">${price == null ? "–" : price === 0 ? "Gratuit" : money(price, catalog.currency) + " / mois"}</div>
              <ul>${p.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>
              ${p.code === "etudiant" && products.find((x) => x.code === "etudiant_annual")
                ? `<button class="btn small ghost" data-act="buy" data-product="etudiant_annual">Annuel : ${money(products.find((x) => x.code === "etudiant_annual").price, catalog.currency)}</button>` : ""}
              ${offer && !current ? `<button class="btn" data-act="buy" data-product="${offer.code}">Choisir</button>` : ""}
            </div>`;
          }).join("")}
        </div>
        <div class="card" style="margin-top:16px">
          <div class="row-between"><h3>Crédits IA</h3><span class="hint">Utilisés une fois le quota quotidien atteint</span></div>
          <div class="row-actions wrap" style="margin-top:12px">
            ${packs.map((p) => `<button class="btn ghost" data-act="buy" data-product="${p.code}">${p.credits} crédits : ${money(p.price, catalog.currency)}</button>`).join("")}
          </div>
        </div>
        <form class="inline-form" data-form="promo" style="margin-top:12px">
          <input name="code" type="text" placeholder="Code promo" maxlength="40" aria-label="Code promo">
          <span class="hint" style="align-self:center">Saisissez le code avant de choisir une formule.</span>
        </form>
      </section>

      <section class="card">
        <h2>Mes informations</h2>
        <form class="form" data-form="profile" style="margin-top:14px">
          <div class="form-grid">
            <div class="field"><label for="p-first">Prénom</label><input id="p-first" name="first_name" value="${esc(me.first_name)}" required maxlength="100"></div>
            <div class="field"><label for="p-last">Nom</label><input id="p-last" name="last_name" value="${esc(me.last_name)}" required maxlength="100"></div>
            <div class="field"><label for="p-country">Pays</label><select id="p-country" name="country">${countryOptions}</select></div>
            <div class="field"><label for="p-lang">Langue</label><select id="p-lang" name="language"><option value="fr" ${me.language === "fr" ? "selected" : ""}>Français</option><option value="en" ${me.language === "en" ? "selected" : ""}>English</option></select></div>
            <div class="field"><label for="p-etab">Établissement</label><input id="p-etab" name="establishment" value="${esc(me.establishment || "")}" maxlength="200"></div>
            <div class="field"><label for="p-level">Niveau</label><input id="p-level" name="level" value="${esc(me.level || "")}" maxlength="100"></div>
            <div class="field"><label for="p-fil">Filière</label><input id="p-fil" name="filiere" value="${esc(me.filiere || "")}" maxlength="100"></div>
            <div class="field"><label for="p-spec">Spécialité</label><input id="p-spec" name="specialite" value="${esc(me.specialite || "")}" maxlength="100"></div>
            <div class="field"><label for="p-year">Année académique</label><input id="p-year" name="academic_year" value="${esc(me.academic_year || "")}" placeholder="ex. 2026-2027" maxlength="20"></div>
          </div>
          <div><button class="btn" type="submit">Enregistrer</button></div>
        </form>
      </section>

      <section class="card">
        <h2>Compte</h2>
        <div class="row" style="border:0;padding-top:12px">
          <span class="small muted">Vos données restent liées à votre compte sur tous vos appareils.</span>
          <button class="btn ghost small" data-act="logout">${icon("logout")} Se déconnecter</button>
        </div>
        <details style="margin-top:14px">
          <summary class="small" style="cursor:pointer;color:var(--danger)">Supprimer mon compte</summary>
          <form class="inline-form" data-form="delete-account" style="margin-top:12px">
            <input name="password" type="password" required placeholder="Mot de passe pour confirmer" autocomplete="current-password">
            <button class="btn danger" type="submit">Supprimer définitivement</button>
          </form>
          <p class="hint" style="margin-top:8px">Toutes vos matières, documents, résultats et abonnements seront effacés.</p>
        </details>
      </section>`);
  }

  /* ============================================================
   * Actions (delegated clicks)
   * ============================================================ */
  const ACTIONS = {
    reload: () => route(),
    logout: () => { storage.set(TOKEN_KEY, null); state.me = null; state.quiz = null; state.quizResult = null; go("connexion"); },

    "quiz-chapter": (el) => startQuiz({ chapter_id: Number(el.dataset.id), count: 10 }),
    "quiz-subject": (el) => startQuiz({ subject_id: Number(el.dataset.id), count: 10 }),
    evaluation: (el) => startQuiz({ kind: "evaluation", subject_id: Number(el.dataset.id), count: 10 }).then(() => toast("Évaluation lancée")),

    generate: async (el) => {
      const difficulty = ($("#difficulty") || {}).value || "moyen";
      el.disabled = true;
      toast("Génération des questions en cours…");
      try {
        const data = await api(`/chapters/${el.dataset.id}/exercises/generate`, { method: "POST", body: { count: 5, difficulty } });
        toast(`${plural(data.created, "question ajoutée", "questions ajoutées")}. Lancez un quiz pour vous entraîner.`, "success");
      } finally { el.disabled = false; }
      route();
    },

    "del-chapter": async (el) => {
      if (!confirm("Supprimer ce chapitre et ses questions ?")) return;
      await api(`/chapters/${el.dataset.id}`, { method: "DELETE" });
      route();
    },
    "del-subject": async (el) => {
      if (!confirm("Supprimer cette matière, ses chapitres et ses documents ?")) return;
      await api(`/subjects/${el.dataset.id}`, { method: "DELETE" });
      go("cours");
    },
    "del-doc": async (el) => {
      if (!confirm("Supprimer ce document ?")) return;
      await api(`/documents/${el.dataset.id}`, { method: "DELETE" });
      route();
    },
    analyze: async (el) => {
      el.disabled = true;
      try {
        const data = await api(`/documents/${el.dataset.id}/analyze`, { method: "POST" });
        $("#analysis").innerHTML = `<div class="explain text-block" style="margin-top:14px;line-height:1.6">${paragraphs(data.analysis)}</div>`;
      } catch (error) {
        toast(error.message, "error");
      } finally { el.disabled = false; }
    },

    pick: (el) => {
      const q = state.quiz;
      if (!q) return;
      q.answers[el.dataset.question] = Number(el.dataset.choice);
      route();
    },
    "quiz-prev": () => { state.quiz.index = Math.max(0, state.quiz.index - 1); route(); },
    "quiz-next": () => { state.quiz.index = Math.min(state.quiz.questions.length - 1, state.quiz.index + 1); route(); },
    "quiz-submit": async () => {
      const q = state.quiz;
      const missing = q.questions.length - Object.keys(q.answers).length;
      if (missing > 0 && !confirm(`${plural(missing, "question n'a pas de réponse", "questions n'ont pas de réponse")}. Elles seront comptées comme fausses. Corriger maintenant ?`)) return;
      const result = await api(`/quizzes/${q.id}/submit`, {
        method: "POST",
        body: { answers: Object.entries(q.answers).map(([exercise_id, choice]) => ({ exercise_id: Number(exercise_id), choice })) },
      });
      state.quizResult = result;
      state.quiz = null;
      route();
    },
    "quit-quiz": () => { if (confirm("Quitter ce quiz ? Vos réponses ne seront pas enregistrées.")) { state.quiz = null; go("cours"); } },

    "review-answer": async (el) => {
      const result = await api(`/reviews/${el.dataset.exercise}/answer`, { method: "POST", body: { choice: Number(el.dataset.choice) } });
      const question = $(".question") ? $(".question").textContent : "";
      state.reviewFeedback = { result, question };
      route();
    },

    buy: async (el) => {
      const promo = ($('form[data-form="promo"] input[name="code"]') || {}).value || "";
      el.disabled = true;
      try {
        const checkout = await api("/billing/checkout", {
          method: "POST",
          body: { product: el.dataset.product, promo_code: promo.trim() || null },
        });
        storage.set(TX_KEY, checkout.tx_ref);
        toast("Redirection vers le paiement sécurisé…");
        window.location.href = checkout.payment_link;
      } catch (error) {
        toast(error.message, "error");
        el.disabled = false;
      }
    },
    "check-payment": async () => {
      const tx = storage.get(TX_KEY);
      if (!tx) return;
      const data = await api(`/billing/payments/${encodeURIComponent(tx)}`);
      if (data.status === "succeeded") { storage.set(TX_KEY, null); toast("Paiement confirmé. Votre formule est activée.", "success"); }
      else if (data.status === "failed") { storage.set(TX_KEY, null); toast("Le paiement n'a pas abouti.", "error"); }
      else toast("Paiement toujours en attente de confirmation.");
      route();
    },
  };

  /* ============================================================
   * Forms (delegated submits)
   * ============================================================ */
  const FORMS = {
    async login(form) {
      const data = Object.fromEntries(new FormData(form));
      const res = await api("/auth/login", { method: "POST", body: data, auth: false });
      storage.set(TOKEN_KEY, res.access_token);
      state.me = res.user;
      go("accueil");
    },

    async register(form) {
      const data = Object.fromEntries(new FormData(form));
      for (const key of Object.keys(data)) if (data[key] === "") delete data[key];
      const res = await api("/auth/register", { method: "POST", body: data, auth: false });
      storage.set(TOKEN_KEY, res.access_token);
      state.me = res.user;
      toast("Bienvenue ! Ajoutez votre première matière.", "success");
      go("cours");
    },

    async "add-subject"(form) {
      const data = Object.fromEntries(new FormData(form));
      await api("/subjects", { method: "POST", body: { name: data.name.trim(), semester: data.semester ? Number(data.semester) : null } });
      toast("Matière ajoutée", "success");
      route();
    },

    async "add-chapter"(form) {
      const title = new FormData(form).get("title").trim();
      await api(`/subjects/${form.dataset.subject}/chapters`, { method: "POST", body: { title } });
      route();
    },

    async upload(form) {
      const fd = new FormData(form);
      const file = fd.get("file");
      if (!file || !file.name) throw new Error("Choisissez un fichier.");
      const body = new FormData();
      body.append("file", file);
      body.append("subject_id", form.dataset.subject);
      if (fd.get("chapter_id")) body.append("chapter_id", fd.get("chapter_id"));
      toast("Import en cours…");
      await api("/documents", { method: "POST", form: body });
      toast("Document importé", "success");
      route();
    },

    async explain(form) {
      const fd = new FormData(form);
      const body = { question: fd.get("question").trim() };
      if (fd.get("subject_id")) body.subject_id = Number(fd.get("subject_id"));
      const res = await api("/ai/explain", { method: "POST", body });
      state.explainAnswer = res;
      route();
    },

    async profile(form) {
      const data = Object.fromEntries(new FormData(form));
      for (const key of Object.keys(data)) if (data[key] === "") data[key] = null;
      state.me = await api("/me", { method: "PATCH", body: data });
      toast("Informations enregistrées", "success");
      route();
    },

    async promo(form) {
      toast("Le code sera appliqué au moment du choix de la formule.");
    },

    async "delete-account"(form) {
      const password = new FormData(form).get("password");
      if (!confirm("Supprimer définitivement votre compte et toutes vos données ?")) return;
      await api("/me", { method: "DELETE", body: { password } });
      storage.set(TOKEN_KEY, null);
      storage.set(TX_KEY, null);
      state.me = null;
      toast("Votre compte a été supprimé.", "success");
      go("connexion");
    },
  };

  /* ============================================================
   * Wiring
   * ============================================================ */
  document.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-act]");
    if (!el || el.disabled) return;
    const action = ACTIONS[el.dataset.act];
    if (!action) return;
    event.preventDefault();
    try {
      await action(el);
    } catch (error) {
      if (error.status === 401) { storage.set(TOKEN_KEY, null); state.me = null; return go("connexion"); }
      toast(error.message, "error");
    }
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-form]");
    if (!form) return;
    event.preventDefault();
    const handler = FORMS[form.dataset.form];
    if (!handler) return;
    const submit = form.querySelector('[type="submit"]');
    const errorBox = form.querySelector("[data-error]");
    if (errorBox) errorBox.hidden = true;
    if (submit) submit.disabled = true;
    try {
      await handler(form);
    } catch (error) {
      if (errorBox) { errorBox.textContent = error.message; errorBox.hidden = false; }
      else toast(error.message, "error");
    } finally {
      if (submit) submit.disabled = false;
    }
  });

  window.addEventListener("hashchange", route);
  route();
})();

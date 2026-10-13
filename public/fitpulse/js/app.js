/* =============================================================
   FitPulse — core app layer
   - Store: thin data layer over localStorage (swap for an API later)
   - UI: navbar, tabbar, footer, theme, toasts, modals, rings, charts
   Every page loads this file first.
   ============================================================= */

/* ---------------- Configuration ----------------
   Replace these placeholders when connecting real services.
------------------------------------------------- */
const isHttp = typeof window !== "undefined" && window.location.protocol.startsWith("http");
const FP_CONFIG = {
  API_BASE_URL: isHttp ? window.location.origin + "/api" : "", // auto-connects to backend when served over HTTP
  AI_API_URL: isHttp ? window.location.origin + "/api/ai/coach" : "",
  AI_API_KEY: "", // never ship a real key in frontend code — proxy through your backend
  PAYMENT_PROVIDER: "razorpay", // "razorpay" | "stripe"
  PAYMENT_KEY_ID: "", // public key id, set when connecting a real gateway
  DATA_PATH: "data/",
};
window.FP_CONFIG = FP_CONFIG;

/* ---------------- Storage layer ---------------- */
const KEY = "fitpulse:v1";

const defaultState = () => ({
  users: [],
  session: null, // { email, role }
  profiles: {}, // email -> profile
  logs: {}, // email -> { nutrition:{}, workouts:[], water:{}, sleep:{}, habits:{}, weights:[], steps:{} }
  tickets: [],
  customFoods: [],
  customWorkouts: [],
  settings: { theme: "light", units: "metric", notifications: true, publicProfile: false },
});

function readState() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return defaultState();
    return Object.assign(defaultState(), JSON.parse(raw));
  } catch (e) {
    console.warn("FitPulse: corrupt storage, resetting", e);
    return defaultState();
  }
}
function writeState(s) {
  localStorage.setItem(KEY, JSON.stringify(s));
  return s;
}

const Store = {
  get: readState,
  set: writeState,
  update(fn) {
    const s = readState();
    fn(s);
    return writeState(s);
  },
  reset() {
    localStorage.removeItem(KEY);
  },
};

/* ---------------- Helpers ---------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const todayKey = (d = new Date()) => d.toISOString().slice(0, 10);
const clamp = (n, a, b) => Math.min(b, Math.max(a, n));
const uid = () => Math.random().toString(36).slice(2, 10);
const fmtDate = (iso) =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const escapeHtml = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function lastNDays(n) {
  const out = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    out.push(todayKey(d));
  }
  return out;
}

/* ---------------- Session & profile API ---------------- */
function currentUser() {
  const s = readState();
  if (!s.session) return null;
  return s.users.find((u) => u.email === s.session.email) || null;
}

function isDemo() {
  const s = readState();
  return s.session?.email === "demo@fitpulse.app";
}

function getUserProfile(email) {
  const s = readState();
  email = email || s.session?.email;
  if (!email) return null;
  return s.profiles[email] || { email, name: s.users.find((u) => u.email === email)?.name || "Athlete" };
}

function saveUserProfile(patch) {
  if (isDemo()) { toast("Demo mode is read-only. Create an account to save changes.", "info"); return null; }
  const s = readState();
  const email = s.session?.email;
  if (!email) return null;
  s.profiles[email] = Object.assign({}, s.profiles[email], patch);
  writeState(s);
  return s.profiles[email];
}

function userLogs(email) {
  const s = readState();
  email = email || s.session?.email;
  if (!email) return null;
  if (!s.logs[email]) {
    s.logs[email] = { nutrition: {}, workouts: [], water: {}, sleep: {}, habits: {}, weights: [], steps: {} };
    writeState(s);
  }
  return s.logs[email];
}

function saveLogs(mutator) {
  if (isDemo()) { toast("Demo mode is read-only. Create an account to log data.", "info"); return null; }
  const s = readState();
  const email = s.session?.email;
  if (!email) return null;
  if (!s.logs[email])
    s.logs[email] = { nutrition: {}, workouts: [], water: {}, sleep: {}, habits: {}, weights: [], steps: {} };
  mutator(s.logs[email]);
  writeState(s);
  return s.logs[email];
}

/* Targets derived from the onboarding profile (Mifflin-St Jeor). */
function getTargets(profile) {
  const p = profile || getUserProfile() || {};
  const w = Number(p.weight) || 70;
  const h = Number(p.height) || 170;
  const age = Number(p.age) || 28;
  const male = (p.gender || "male") === "male";
  const bmr = 10 * w + 6.25 * h - 5 * age + (male ? 5 : -161);
  const factors = { sedentary: 1.2, light: 1.375, moderate: 1.55, active: 1.725, athlete: 1.9 };
  let cal = bmr * (factors[p.activity] || 1.375);
  if (p.goal === "lose") cal -= 400;
  if (p.goal === "gain") cal += 350;
  cal = Math.round(cal / 10) * 10;
  return {
    calories: cal,
    protein: Math.round(w * (p.goal === "gain" ? 2 : 1.6)),
    carbs: Math.round((cal * 0.42) / 4),
    fat: Math.round((cal * 0.27) / 9),
    fiber: 30,
    water: 3000,
    steps: 10000,
    sleep: 8,
  };
}

function bmi(weightKg, heightCm) {
  if (!weightKg || !heightCm) return 0;
  return +(weightKg / Math.pow(heightCm / 100, 2)).toFixed(1);
}
function bmiLabel(v) {
  if (v < 18.5) return "Underweight";
  if (v < 25) return "Healthy";
  if (v < 30) return "Overweight";
  return "Obese";
}

/* Daily nutrition totals */
function getNutrition(date = todayKey()) {
  const logs = userLogs();
  const day = logs?.nutrition?.[date] || { breakfast: [], lunch: [], dinner: [], snacks: [] };
  const totals = { calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 };
  Object.values(day).forEach((items) =>
    (items || []).forEach((f) => {
      const q = f.qty || 1;
      totals.calories += (f.calories || 0) * q;
      totals.protein += (f.protein || 0) * q;
      totals.carbs += (f.carbs || 0) * q;
      totals.fat += (f.fat || 0) * q;
      totals.fiber += (f.fiber || 0) * q;
    })
  );
  Object.keys(totals).forEach((k) => (totals[k] = Math.round(totals[k])));
  return { meals: day, totals };
}

function addFood(meal, food, date = todayKey()) {
  saveLogs((l) => {
    l.nutrition[date] = l.nutrition[date] || { breakfast: [], lunch: [], dinner: [], snacks: [] };
    l.nutrition[date][meal] = l.nutrition[date][meal] || [];
    l.nutrition[date][meal].push(Object.assign({ logId: uid(), qty: 1 }, food));
  });
  return getNutrition(date);
}
function removeFood(meal, logId, date = todayKey()) {
  saveLogs((l) => {
    const day = l.nutrition[date];
    if (day && day[meal]) day[meal] = day[meal].filter((f) => f.logId !== logId);
  });
  return getNutrition(date);
}

/* Water */
function getWater(date = todayKey()) {
  const l = userLogs();
  return l?.water?.[date] || { total: 0, entries: [] };
}
function saveWater(ml, date = todayKey()) {
  saveLogs((l) => {
    const d = (l.water[date] = l.water[date] || { total: 0, entries: [] });
    d.total = Math.max(0, d.total + ml);
    d.entries.push({ id: uid(), ml, at: new Date().toISOString() });
  });
  return getWater(date);
}

/* Sleep */
function getSleep(date = todayKey()) {
  const l = userLogs();
  return l?.sleep?.[date] || null;
}
function saveSleep(entry, date = todayKey()) {
  saveLogs((l) => {
    l.sleep[date] = entry;
  });
  return entry;
}

/* Steps */
function getSteps(date = todayKey()) {
  const l = userLogs();
  return l?.steps?.[date] || 0;
}
function saveSteps(count, date = todayKey()) {
  saveLogs((l) => {
    l.steps[date] = Math.max(0, count);
  });
  return count;
}

/* Habits */
const HABITS = [
  { id: "water", name: "Drink Water", icon: "💧" },
  { id: "workout", name: "Workout", icon: "🏋️" },
  { id: "steps", name: "10k Steps", icon: "👟" },
  { id: "meal", name: "Healthy Meal", icon: "🥗" },
  { id: "sleep", name: "Sleep 7+ Hours", icon: "😴" },
  { id: "meditate", name: "Meditation", icon: "🧘" },
];
function getHabits(date = todayKey()) {
  const l = userLogs();
  return l?.habits?.[date] || {};
}
function toggleHabit(id, date = todayKey()) {
  let res;
  saveLogs((l) => {
    l.habits[date] = l.habits[date] || {};
    l.habits[date][id] = !l.habits[date][id];
    res = l.habits[date];
  });
  return res;
}
function habitStreak() {
  const l = userLogs();
  if (!l) return 0;
  let streak = 0;
  for (let i = 0; i < 400; i++) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const day = l.habits[todayKey(d)] || {};
    const done = Object.values(day).filter(Boolean).length;
    if (done >= 3) streak++;
    else if (i > 0) break;
  }
  return streak;
}

/* Workouts */
function addWorkout(w) {
  saveLogs((l) => l.workouts.push(Object.assign({ id: uid(), date: todayKey() }, w)));
  return userLogs().workouts;
}
function completeWorkout(w) {
  return addWorkout(Object.assign({ completed: true }, w));
}
function getWorkoutHistory() {
  return (userLogs()?.workouts || []).slice().reverse();
}

/* Progress / weight */
function getProgress() {
  const p = getUserProfile() || {};
  const l = userLogs() || { weights: [] };
  const weights = (l.weights || []).slice().sort((a, b) => a.date.localeCompare(b.date));
  const start = Number(p.startWeight) || weights[0]?.kg || Number(p.weight) || 0;
  const current = weights.length ? weights[weights.length - 1].kg : Number(p.weight) || start;
  const target = Number(p.targetWeight) || current;
  const totalDelta = Math.abs(start - target) || 1;
  const doneDelta = Math.abs(start - current);
  return {
    weights,
    start,
    current,
    target,
    lost: +(start - current).toFixed(1),
    bmi: bmi(current, Number(p.height)),
    percent: Math.round(clamp((doneDelta / totalDelta) * 100, 0, 100)),
  };
}
function saveWeight(kg, date = todayKey()) {
  saveLogs((l) => {
    l.weights = (l.weights || []).filter((w) => w.date !== date);
    l.weights.push({ date, kg: Number(kg) });
  });
  saveUserProfile({ weight: Number(kg) });
  return getProgress();
}

/* Health score 0-100 */
function healthScore() {
  const t = getTargets();
  const n = getNutrition().totals;
  const w = getWater().total;
  const s = getSteps();
  const sl = getSleep();
  const wk = (userLogs()?.workouts || []).filter((x) => x.date === todayKey()).length;
  const parts = [
    clamp(n.calories / t.calories, 0, 1) * 25,
    clamp(n.protein / t.protein, 0, 1) * 20,
    clamp(w / t.water, 0, 1) * 20,
    clamp(s / t.steps, 0, 1) * 15,
    clamp((sl?.hours || 0) / t.sleep, 0, 1) * 10,
    wk ? 10 : 0,
  ];
  return Math.round(parts.reduce((a, b) => a + b, 0));
}

/* Static data loaders (JSON files; swap for API endpoints later) */
const _cache = {};
async function loadJSON(file) {
  if (_cache[file]) return _cache[file];
  const res = await fetch(FP_CONFIG.DATA_PATH + file, { cache: "no-cache" });
  if (!res.ok) throw new Error("Could not load " + file);
  _cache[file] = await res.json();
  return _cache[file];
}
async function getFoods() {
  const base = await loadJSON("foods.json");
  return base.concat(readState().customFoods || []);
}
async function getWorkouts() {
  const base = await loadJSON("workouts.json");
  return base.concat(readState().customWorkouts || []);
}
const getMealPlans = () => loadJSON("meal-plans.json");

/* ---------------- Theme ---------------- */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const s = readState();
  s.settings.theme = theme;
  writeState(s);
  $$(".js-theme-icon").forEach((el) => (el.textContent = theme === "dark" ? "☀️" : "🌙"));
}
function toggleTheme() {
  applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
}
(function initTheme() {
  let t = "light";
  try {
    t = readState().settings.theme || "light";
  } catch (e) {}
  document.documentElement.setAttribute("data-theme", t);
})();

/* ---------------- Icons ---------------- */
const ICONS = {
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>',
  nutrition:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8c0-3 2-5 5-5 0 3-2 5-5 5Z"/><path d="M7 21c-3 0-4-4-4-7s2-6 5-6c1.5 0 2 .7 4 .7S14.5 8 16 8c3 0 5 3 5 6s-1 7-4 7c-2 0-2.5-1-5-1s-3 1-5 1Z"/></svg>',
  workout:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8v8M18 8v8M3 10v4M21 10v4M6 12h12"/></svg>',
  progress:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5"/><path d="M4 19h16"/><path d="m7 15 4-5 3 3 5-7"/></svg>',
  profile:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/></svg>',
  ai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="7" width="16" height="12" rx="4"/><path d="M12 3v4M9 13h.01M15 13h.01M9.5 16.5h5"/></svg>',
  bolt: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2Z"/></svg>',
  check:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7"/></svg>',
  plus: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  close:
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18"/></svg>',
  burger:
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
  water:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3s6 6.5 6 10.5A6 6 0 0 1 6 13.5C6 9.5 12 3 12 3Z"/></svg>',
  sleep:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"/></svg>',
  habit:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l2 2 4-4"/><rect x="3" y="4" width="18" height="17" rx="4"/><path d="M8 2v4M16 2v4"/></svg>',
  shield:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3Z"/></svg>',
};

/* ---------------- Chrome: navbar / tabbar / footer ---------------- */
const APP_LINKS = [
  ["index.html", "Home"],
  ["dashboard.html", "Dashboard"],
  ["nutrition.html", "Nutrition"],
  ["workouts.html", "Workouts"],
  ["progress.html", "Progress"],
  ["ai-coach.html", "AI Coach"],
];
const MORE_LINKS = [
  ["meal-plan.html", "Meal Planner"],
  ["food-detail.html", "Food Details"],
  ["workout-detail.html", "Workout Player"],
  ["habits.html", "Habits"],
  ["water.html", "Water"],
  ["sleep.html", "Sleep"],
  ["profile.html", "Profile"],
  ["subscription.html", "Subscription"],
  ["settings.html", "Settings"],
  ["support.html", "Support"],
  ["about.html", "About"],
  ["contact.html", "Contact"],
];
const ADMIN_LINKS = [
  ["admin.html", "Overview"],
  ["manage-users.html", "Users"],
  ["manage-foods.html", "Foods"],
  ["manage-workouts.html", "Workouts"],
  ["manage-subscriptions.html", "Subscriptions"],
  ["support.html", "Support"],
];

function currentPage() {
  const f = location.pathname.split("/").pop();
  return f && f.length ? f : "index.html";
}

function renderChrome() {
  const page = currentPage();
  const isAdmin = document.body.dataset.area === "admin";
  const links = isAdmin ? ADMIN_LINKS : APP_LINKS;
  const user = currentUser();
  const profile = getUserProfile();
  const initials = (profile?.name || user?.name || "FP")
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const navLinks = links
    .map(([href, label]) => `<a href="${href}" class="${page === href ? "active" : ""}">${label}</a>`)
    .join("");

  const accountBtn = user
    ? `<a href="${isAdmin ? "admin.html" : "profile.html"}" class="avatar" title="${escapeHtml(profile?.name || user.name)}">${initials}</a>`
    : `<a href="login.html" class="btn btn-sm">Get started</a>`;

  const nav = document.createElement("header");
  nav.className = "nav";
  nav.innerHTML = `
    <div class="container">
      <a href="${isAdmin ? "admin.html" : "index.html"}" class="brand">
        <span class="brand-mark">${ICONS.bolt}</span>
        <span>FitPulse${isAdmin ? ' <span class="badge" style="vertical-align:middle">Admin</span>' : ""}</span>
      </a>
      <nav class="nav-links">${navLinks}</nav>
      <div class="nav-actions">
        <button class="icon-btn js-theme" aria-label="Toggle theme"><span class="js-theme-icon">🌙</span></button>
        ${!isAdmin && user ? '<a href="subscription.html" class="btn btn-sm btn-soft">Premium</a>' : ""}
        ${accountBtn}
        <button class="icon-btn nav-burger js-burger" aria-label="Open menu">${ICONS.burger}</button>
      </div>
    </div>`;
  document.body.prepend(nav);

  // drawer
  const drawer = document.createElement("div");
  drawer.className = "drawer js-drawer";
  const drawerLinks = (isAdmin ? ADMIN_LINKS : APP_LINKS.concat(MORE_LINKS))
    .map(([href, label]) => `<a href="${href}" class="${page === href ? "active" : ""}">${label}</a>`)
    .join("");
  drawer.innerHTML = `
    <div class="drawer-panel">
      <div class="row-between" style="margin-bottom:10px">
        <strong style="font-family:var(--font-display)">Menu</strong>
        <button class="icon-btn js-drawer-close" aria-label="Close menu">${ICONS.close}</button>
      </div>
      ${drawerLinks}
      <hr class="divider"/>
      ${
        user
          ? `<button class="btn btn-ghost btn-block js-logout">Log out</button>`
          : `<a href="login.html" class="btn btn-block">Log in</a>`
      }
      ${isAdmin ? '<a href="index.html" class="small muted" style="padding:10px 14px">← Back to app</a>' : '<a href="admin.html" class="small muted" style="padding:10px 14px">Admin panel</a>'}
    </div>`;
  document.body.appendChild(drawer);

  // tab bar (customer area only)
  if (!isAdmin && document.body.dataset.tabbar !== "off") {
    const tabs = [
      ["index.html", "Home", ICONS.home],
      ["nutrition.html", "Nutrition", ICONS.nutrition],
      ["workouts.html", "Workout", ICONS.workout],
      ["progress.html", "Progress", ICONS.progress],
      ["profile.html", "Profile", ICONS.profile],
    ];
    const bar = document.createElement("nav");
    bar.className = "tabbar";
    bar.innerHTML = `<div class="tabbar-inner">${tabs
      .map(([h, l, i]) => `<a href="${h}" class="${page === h ? "active" : ""}">${i}<span>${l}</span></a>`)
      .join("")}</div>`;
    document.body.appendChild(bar);
    document.body.classList.add("has-tabbar");
  }

  // footer
  if (document.body.dataset.footer === "on") {
    const f = document.createElement("footer");
    f.className = "footer";
    f.innerHTML = `
      <div class="container">
        <div class="footer-grid">
          <div>
            <a href="index.html" class="brand"><span class="brand-mark">${ICONS.bolt}</span><span>FitPulse</span></a>
            <p class="lead small" style="margin-top:12px;max-width:34ch">Nutrition, training, recovery and an AI coach — one calm, precise health companion.</p>
          </div>
          <div><h4>Product</h4><div class="footer-links">
            <a href="dashboard.html">Dashboard</a><a href="nutrition.html">Nutrition</a>
            <a href="workouts.html">Workouts</a><a href="ai-coach.html">AI Coach</a>
            <a href="subscription.html">Pricing</a></div></div>
          <div><h4>Track</h4><div class="footer-links">
            <a href="progress.html">Progress</a><a href="habits.html">Habits</a>
            <a href="water.html">Water</a><a href="sleep.html">Sleep</a>
            <a href="meal-plan.html">Meal planner</a></div></div>
          <div><h4>Company</h4><div class="footer-links">
            <a href="about.html">About</a><a href="contact.html">Contact</a>
            <a href="support.html">Support</a><a href="privacy.html">Privacy</a>
            <a href="terms.html">Terms</a><a href="cancellation-refund.html">Refund Policy</a>
            <a href="admin.html">Admin</a></div></div>
        </div>
        <div class="footer-bottom">
          <span>© ${new Date().getFullYear()} FitPulse Pro. Evidence-based fitness companion — not medical advice.</span>
          <span>Made for people who like their health data clean.</span>
        </div>
      </div>`;
    document.body.appendChild(f);
  }

  // toast host
  if (!$(".toast-wrap")) {
    const t = document.createElement("div");
    t.className = "toast-wrap";
    document.body.appendChild(t);
  }

  // wiring
  $(".js-theme")?.addEventListener("click", toggleTheme);
  $(".js-burger")?.addEventListener("click", () => $(".js-drawer").classList.add("open"));
  $(".js-drawer-close")?.addEventListener("click", () => $(".js-drawer").classList.remove("open"));
  $(".js-drawer")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove("open");
  });
  $(".js-logout")?.addEventListener("click", () => logoutUser());
  $$(".js-theme-icon").forEach(
    (el) => (el.textContent = document.documentElement.getAttribute("data-theme") === "dark" ? "☀️" : "🌙")
  );
}

/* ---------------- Toast / modal / confirm ---------------- */
function toast(message, kind = "ok") {
  const host = $(".toast-wrap") || document.body;
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.innerHTML = `<span>${kind === "err" ? "⚠️" : kind === "info" ? "ℹ️" : "✅"}</span><span>${escapeHtml(message)}</span>`;
  host.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateX(20px)";
    el.style.transition = "all .3s";
    setTimeout(() => el.remove(), 320);
  }, 2600);
}

function openModal(id) {
  const m = typeof id === "string" ? $(id) : id;
  m?.classList.add("open");
}
function closeModal(id) {
  const m = typeof id === "string" ? $(id) : id;
  m?.classList.remove("open");
}
function wireModals(root = document) {
  $$(".modal", root).forEach((m) => {
    if (m.dataset.wired) return;
    m.dataset.wired = "1";
    m.addEventListener("click", (e) => {
      if (e.target === m || e.target.closest("[data-close]")) m.classList.remove("open");
    });
  });
}

function confirmDialog(title, message, confirmLabel = "Confirm") {
  return new Promise((resolve) => {
    const m = document.createElement("div");
    m.className = "modal open";
    m.innerHTML = `
      <div class="modal-panel" style="max-width:420px">
        <div class="modal-head"><h3>${escapeHtml(title)}</h3></div>
        <p class="lead small">${escapeHtml(message)}</p>
        <div class="modal-foot">
          <button class="btn btn-ghost js-no">Cancel</button>
          <button class="btn btn-danger js-yes">${escapeHtml(confirmLabel)}</button>
        </div>
      </div>`;
    document.body.appendChild(m);
    const done = (v) => {
      m.remove();
      resolve(v);
    };
    m.querySelector(".js-no").onclick = () => done(false);
    m.querySelector(".js-yes").onclick = () => done(true);
    m.addEventListener("click", (e) => e.target === m && done(false));
  });
}

/* ---------------- Rings, bars, counters, reveal ---------------- */
function ringHTML({ value = 0, max = 100, size = 120, stroke = 11, label = "", sub = "", display = null }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = clamp(max ? value / max : 0, 0, 1);
  return `
    <div class="ring" style="width:${size}px;height:${size}px">
      <svg width="${size}" height="${size}">
        <defs><linearGradient id="fpGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#12b5a0"/><stop offset="60%" stop-color="#3ddc97"/><stop offset="100%" stop-color="#a7e83c"/>
        </linearGradient></defs>
        <circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}"></circle>
        <circle class="ring-bar" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}"
          stroke-dasharray="${c}" stroke-dashoffset="${c}" data-offset="${c * (1 - pct)}"></circle>
      </svg>
      <div class="ring-label">
        <span class="rv">${display ?? Math.round(pct * 100) + "%"}</span>
        ${label ? `<span class="rl">${escapeHtml(label)}</span>` : ""}
        ${sub ? `<span class="tiny muted">${escapeHtml(sub)}</span>` : ""}
      </div>
    </div>`;
}

function animateRings(root = document) {
  requestAnimationFrame(() => {
    $$(".ring-bar", root).forEach((c) => {
      c.style.strokeDashoffset = c.dataset.offset;
    });
  });
}
function animateBars(root = document) {
  requestAnimationFrame(() => {
    $$(".bar > i", root).forEach((b) => {
      b.style.width = clamp(Number(b.dataset.pct || 0), 0, 100) + "%";
    });
  });
}
function countUp(el, to, { duration = 1100, decimals = 0, suffix = "", prefix = "" } = {}) {
  const start = performance.now();
  const from = 0;
  const step = (t) => {
    const p = clamp((t - start) / duration, 0, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = prefix + (from + (to - from) * eased).toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ",") + suffix;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function animateCounters(root = document) {
  $$("[data-count]", root).forEach((el) =>
    countUp(el, Number(el.dataset.count), {
      decimals: Number(el.dataset.decimals || 0),
      suffix: el.dataset.suffix || "",
      prefix: el.dataset.prefix || "",
    })
  );
}
function initReveal(root = document) {
  const els = $$(".reveal", root);
  if (!els.length) return;
  const io = new IntersectionObserver(
    (entries) =>
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add("in");
          io.unobserve(e.target);
        }
      }),
    { threshold: 0.12 }
  );
  els.forEach((e) => io.observe(e));
}

/* Chart.js defaults (loaded per-page from CDN) */
function chartTheme() {
  const tokens = getComputedStyle(document.documentElement);
  return {
    text: tokens.getPropertyValue("--text-soft").trim(),
    grid: tokens.getPropertyValue("--border").trim(),
    accent: tokens.getPropertyValue("--color-blue").trim(),
    accent2: tokens.getPropertyValue("--color-mint").trim(),
  };
}
function lineChart(ctx, labels, datasets, opts = {}) {
  if (typeof Chart === "undefined") return null;
  const t = chartTheme();
  return new Chart(ctx, {
    type: opts.type || "line",
    data: {
      labels,
      datasets: datasets.map((d, i) => {
        const color = d.color || (i === 0 ? t.accent : t.accent2);
        return Object.assign(
          {
            borderColor: color,
            backgroundColor: opts.type === "bar" || d.type === "bar" ? color : color + "22",
            borderWidth: 2.5,
            tension: 0.38,
            fill: opts.type === "bar" ? false : true,
            pointRadius: 0,
            pointHoverRadius: 5,
            borderRadius: 8,
          },
          d
        );
      }),
    },
    options: Object.assign(
      {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: { legend: { display: datasets.length > 1, labels: { color: t.text, usePointStyle: true, boxWidth: 8 } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: t.text, maxRotation: 0, autoSkipPadding: 16 } },
          y: { grid: { color: t.grid }, ticks: { color: t.text }, border: { display: false } },
        },
      },
      opts.options || {}
    ),
  });
}

/* Route guard: send signed-out visitors to login */
function requireAuth(role) {
  const s = readState();
  if (!s.session) {
    sessionStorage.setItem("fp:returnTo", currentPage());
    location.replace("login.html");
    return false;
  }
  if (role && s.session.role !== role) {
    toast("You need " + role + " access for that page.", "err");
    location.replace(role === "admin" ? "dashboard.html" : "index.html");
    return false;
  }
  return true;
}

/* ---------------- Boot ---------------- */
function initDemoLimits() {
  if (!isDemo()) return;
  const KEY = "fp:demo_start";
  let start = sessionStorage.getItem(KEY);
  if (!start) { start = Date.now(); sessionStorage.setItem(KEY, start); }
  const check = () => {
    if (Date.now() - parseInt(start) > 10 * 60 * 1000) {
      sessionStorage.removeItem(KEY);
      confirmDialog("Demo Expired", "Your 10-minute demo session has ended. Sign up for a free account to continue!", "Sign Up")
        .then(() => logoutUser("register.html"));
    } else setTimeout(check, 5000);
  };
  check();
}

document.addEventListener("DOMContentLoaded", () => {
  initDemoLimits();
  if (document.body.dataset.chrome !== "off") renderChrome();
  wireModals();
  initReveal();
  animateRings();
  animateBars();
  animateCounters();
  // FAQ accordions
  $$(".faq-q").forEach((b) => b.addEventListener("click", () => b.closest(".faq-item").classList.toggle("open")));
});

/* expose */
Object.assign(window, {
  FP_CONFIG, Store, $, $$, todayKey, clamp, uid, fmtDate, escapeHtml, lastNDays,
  currentUser, getUserProfile, saveUserProfile, userLogs, saveLogs, getTargets, bmi, bmiLabel,
  getNutrition, addFood, removeFood, getWater, saveWater, getSleep, saveSleep, getSteps, saveSteps,
  HABITS, getHabits, toggleHabit, habitStreak, addWorkout, completeWorkout, getWorkoutHistory,
  getProgress, saveWeight, healthScore, loadJSON, getFoods, getWorkouts, getMealPlans,
  applyTheme, toggleTheme, ICONS, toast, openModal, closeModal, wireModals, confirmDialog,
  ringHTML, animateRings, animateBars, countUp, animateCounters, initReveal, chartTheme, lineChart,
  requireAuth, currentPage,
});

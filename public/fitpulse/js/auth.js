/* =============================================================
   FitPulse — authentication layer (demo)
   All functions are async and return { ok, data?, error? } so they can be
   swapped for real API calls without touching any UI code.
   To connect a backend: set FP_CONFIG.API_BASE_URL in js/app.js and replace
   the bodies marked "LOCAL DEMO" with fetch() calls to your endpoints.
   ============================================================= */

const AUTH_ENDPOINTS = {
  login: "/auth/login",
  register: "/auth/register",
  logout: "/auth/logout",
  me: "/auth/me",
};

async function api(path, body = null, method = "POST") {
  if (!FP_CONFIG.API_BASE_URL) return null; // demo mode
  const token = localStorage.getItem("fitpulse:token");
  const headers = {};
  if (body !== null && method !== "GET" && method !== "HEAD") {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = "Bearer " + token;

  try {
    const fetchOptions = {
      method,
      headers,
      credentials: "include",
    };
    if (body !== null && method !== "GET" && method !== "HEAD") {
      fetchOptions.body = JSON.stringify(body);
    }
    const res = await fetch(FP_CONFIG.API_BASE_URL + path, fetchOptions);
    const data = await res.json().catch(() => ({}));
    if (data.token) {
      localStorage.setItem("fitpulse:token", data.token);
    }
    return {
      ok: res.ok,
      status: res.status,
      data: data.data !== undefined ? data.data : data,
      error: res.ok ? null : (data.error || data.message || "Request failed"),
      ...data
    };
  } catch (err) {
    console.warn("Backend API unreachable:", err);
    if (isHttp) {
      return { ok: false, error: "Could not reach the FitPulse server. Try again." };
    }
    return null;
  }
}
window.api = api;

async function requestPasswordReset(email) {
  return await api("/auth/forgot-password", { email });
}

async function performPasswordReset(token, password) {
  return await api("/auth/reset-password", { token, password });
}

/* Demo-only password hashing (NOT secure — a real backend must hash server-side). */
function weakHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return "h" + Math.abs(h);
}

async function registerUser({ name, email, password }) {
  email = (email || "").trim().toLowerCase();
  const remote = await api(AUTH_ENDPOINTS.register, { name, email, password });
  if (remote) {
    if (remote.ok) {
      const s = Store.get();
      const user = remote.data;
      if (!s.users.some((u) => u.email === email)) s.users.push(user);
      s.session = { email, role: user.role || "user" };
      s.profiles[email] = { name: user.name, email };
      Store.set(s);
    }
    return remote;
  }

  if (isHttp) return { ok: false, error: "Registration is unavailable because the server did not respond." };

  // LOCAL DEMO FALLBACK (file:// only)
  const s = Store.get();
  if (s.users.some((u) => u.email === email)) return { ok: false, error: "An account with that email already exists." };
  const user = { id: uid(), name: name.trim(), email, pass: weakHash(password), role: "user", plan: "free", status: "active", created: new Date().toISOString() };
  s.users.push(user);
  s.session = { email, role: "user" };
  s.profiles[email] = { name: user.name, email };
  Store.set(s);
  return { ok: true, data: user };
}

async function loginUser({ email, password, remember }) {
  email = (email || "").trim().toLowerCase();
  const remote = await api(AUTH_ENDPOINTS.login, { email, password, remember });
  if (remote) {
    if (remote.ok) {
      const s = Store.get();
      const user = remote.data;
      const existing = s.users.find((u) => u.email === email);
      if (!existing) s.users.push(user);
      else Object.assign(existing, user);
      s.session = { email, role: user.role || "user" };
      Store.set(s);
      if (remember) localStorage.setItem("fitpulse:remember", email);
      else localStorage.removeItem("fitpulse:remember");
    }
    return remote;
  }

  if (isHttp) return { ok: false, error: "Login is unavailable because the server did not respond." };

  // LOCAL DEMO FALLBACK (file:// only)
  const s = Store.get();
  const user = s.users.find((u) => u.email === email);
  if (!user) return { ok: false, error: "No account found for that email." };
  if (user.pass !== weakHash(password) && weakHash(password) !== user.pass) return { ok: false, error: "Incorrect password." };
  if (user.status === "suspended") return { ok: false, error: "This account is suspended. Contact support." };
  s.session = { email, role: user.role };
  Store.set(s);
  if (remember) localStorage.setItem("fitpulse:remember", email);
  else localStorage.removeItem("fitpulse:remember");
  return { ok: true, data: user };
}

async function logoutUser(redirect = "login.html") {
  await api(AUTH_ENDPOINTS.logout, {});
  localStorage.removeItem("fitpulse:token");
  Store.update((s) => (s.session = null));
  location.href = redirect;
}

async function socialLogin(provider) {
  toast(`${provider} sign-in is not connected. Use email login or Google if an administrator configured GOOGLE_CLIENT_ID.`, "info");
  return { ok: false, error: `${provider} sign-in is not configured.` };
}

async function loadPublicConfig() {
  const cfg = await api("/config", null, "GET");
  if (cfg && cfg.ok) {
    window.FP_PUBLIC = cfg;
    if (cfg.razorpayKeyId) FP_CONFIG.PAYMENT_KEY_ID = cfg.razorpayKeyId;
    return cfg;
  }
  return null;
}

async function initGoogleButton() {
  const cfg = window.FP_PUBLIC || await loadPublicConfig();
  const clientId = cfg && cfg.googleClientId;
  const host = document.getElementById("g_id_onload");
  const btn = document.querySelector(".g_id_signin");
  if (!clientId) {
    if (host) host.remove();
    if (btn) btn.remove();
    return;
  }
  if (host) host.setAttribute("data-client_id", clientId);
}

async function handleGoogleCallback(response) {
  const credential = response.credential;
  const remote = await api("/auth/google", { token: credential });
  if (remote) {
    if (remote.ok) {
      const s = Store.get();
      const user = remote.data;
      const existing = s.users.find((u) => u.email === user.email);
      if (!existing) s.users.push(user);
      else Object.assign(existing, user);
      s.session = { email: user.email, role: user.role || "user" };
      
      if (!s.profiles[user.email]) s.profiles[user.email] = { name: user.name, email: user.email };
      Store.set(s);
      
      const p = s.profiles[user.email];
      const back = sessionStorage.getItem("fp:returnTo");
      sessionStorage.removeItem("fp:returnTo");
      
      if (isAdmin()) return location.replace("admin.html");
      location.replace(p?.onboarded ? (back || "dashboard.html") : "onboarding.html");
    } else {
      toast(remote.error || "Google login failed.", "error");
    }
  } else {
    toast("Backend unreachable for Google auth.", "error");
  }
}

function isLoggedIn() {
  return !!Store.get().session;
}
function isAdmin() {
  return Store.get().session?.role === "admin";
}

function saveOnboarding(profile) {
  const s = Store.get();
  const email = s.session?.email;
  if (!email) return { ok: false, error: "Not signed in." };
  s.profiles[email] = Object.assign({}, s.profiles[email], profile, {
    startWeight: Number(profile.weight),
    onboarded: true,
  });
  const u = s.users.find((x) => x.email === email);
  if (u && profile.name) u.name = profile.name;
  s.logs[email] = s.logs[email] || { nutrition: {}, workouts: [], water: {}, sleep: {}, habits: {}, weights: [], steps: {} };
  s.logs[email].weights = [{ date: todayKey(), kg: Number(profile.weight) }];
  Store.set(s);
  return { ok: true, data: s.profiles[email] };
}

/* ---------------- Demo seed ----------------
   Creates demo@fitpulse.app / demo1234 and admin@fitpulse.app / admin1234
   with two weeks of believable activity, so every screen has real data. */
function seedDemo(force = false) {
  const s = Store.get();
  if (!force && s.users.length) return;

  const demoEmail = "demo@fitpulse.app";
  const adminEmail = "admin@fitpulse.app";
  s.users = [
    { id: uid(), name: "Aarav Sharma", email: demoEmail, pass: weakHash("demo1234"), role: "user", plan: "premium", status: "active", created: "2026-06-11T09:00:00.000Z" },
    { id: uid(), name: "FitPulse Admin", email: adminEmail, pass: weakHash("admin1234"), role: "admin", plan: "premium", status: "active", created: "2026-01-04T09:00:00.000Z" },
  ];
  const names = ["Ishita Rao", "Kabir Menon", "Nisha Patel", "Rohan Gupta", "Meera Iyer", "Dev Khanna", "Sara Ali", "Vikram Bose", "Ananya Das", "Tanvi Shah"];
  names.forEach((n, i) => {
    const email = n.toLowerCase().replace(/[^a-z]/g, ".") + "@mail.com";
    const d = new Date(2026, 2 + (i % 6), 3 + i);
    s.users.push({
      id: uid(), name: n, email, pass: weakHash("demo1234"), role: "user",
      plan: i % 3 === 0 ? "premium" : "free",
      status: i === 7 ? "suspended" : "active",
      created: d.toISOString(),
      planStart: d.toISOString().slice(0, 10),
      planExpiry: new Date(d.getFullYear(), d.getMonth() + (i % 2 ? 12 : 1), d.getDate()).toISOString().slice(0, 10),
      payment: i % 4 === 0 ? "pending" : "paid",
    });
    s.profiles[email] = { name: n, email, weight: 62 + i, height: 160 + i, goal: "lose" };
  });

  s.profiles[demoEmail] = {
    name: "Aarav Sharma", email: demoEmail, age: 28, gender: "male", height: 176,
    weight: 78.4, startWeight: 84, targetWeight: 72, goal: "lose", activity: "moderate",
    diet: "vegetarian", experience: "intermediate", onboarded: true, plan: "premium",
  };
  s.profiles[adminEmail] = { name: "FitPulse Admin", email: adminEmail, onboarded: true };

  const logs = { nutrition: {}, workouts: [], water: {}, sleep: {}, habits: {}, weights: [], steps: {} };
  const foods = {
    breakfast: [{ name: "Poha", calories: 180, protein: 4, carbs: 32, fat: 4, fiber: 2, serving: "1 bowl" }, { name: "Milk", calories: 103, protein: 8, carbs: 12, fat: 2.4, fiber: 0, serving: "250 ml" }],
    lunch: [{ name: "Roti", calories: 120, protein: 4, carbs: 22, fat: 2, fiber: 3, serving: "1 piece" }, { name: "Dal", calories: 150, protein: 9, carbs: 20, fat: 3, fiber: 6, serving: "1 bowl" }, { name: "Curd", calories: 98, protein: 11, carbs: 4, fat: 4, fiber: 0, serving: "150 g" }],
    dinner: [{ name: "Paneer", calories: 265, protein: 18, carbs: 6, fat: 20, fiber: 0, serving: "100 g" }, { name: "Rice", calories: 205, protein: 4, carbs: 45, fat: 0.4, fiber: 1, serving: "1 cup" }],
    snacks: [{ name: "Banana", calories: 105, protein: 1.3, carbs: 27, fat: 0.3, fiber: 3, serving: "1 medium" }],
  };
  lastNDays(30).forEach((date, i, arr) => {
    const last = i === arr.length - 1;
    logs.nutrition[date] = {
      breakfast: foods.breakfast.map((f) => Object.assign({ logId: uid(), qty: 1 }, f)),
      lunch: foods.lunch.map((f) => Object.assign({ logId: uid(), qty: 1 }, f)),
      dinner: last ? [] : foods.dinner.map((f) => Object.assign({ logId: uid(), qty: 1 }, f)),
      snacks: foods.snacks.map((f) => Object.assign({ logId: uid(), qty: 1 }, f)),
    };
    const wl = 1600 + Math.round(Math.sin(i) * 300) + (last ? 200 : 700);
    logs.water[date] = { total: last ? 1800 : wl, entries: [{ id: uid(), ml: last ? 1800 : wl, at: date + "T09:00:00.000Z" }] };
    logs.steps[date] = last ? 8200 : 7000 + Math.round(Math.random() * 5000);
    logs.sleep[date] = { bedtime: "23:1" + (i % 6), wake: "06:4" + (i % 6), hours: +(6.6 + Math.random() * 1.6).toFixed(1) };
    logs.habits[date] = { water: i % 5 !== 0, workout: i % 3 !== 0, steps: i % 4 !== 0, meal: true, sleep: i % 2 === 0, meditate: i % 3 === 0 };
    logs.weights.push({ date, kg: +(84 - (i * 5.6) / 30 + (Math.random() - 0.5) * 0.3).toFixed(1) });
    if (i % 3 === 0)
      logs.workouts.push({ id: uid(), date, name: ["Full Body Strength", "HIIT Burn 20", "Morning Run", "Upper Body Push"][i % 4], minutes: 30 + (i % 3) * 10, calories: 220 + (i % 4) * 60, completed: true, category: ["Strength", "HIIT", "Cardio", "Gym"][i % 4] });
  });
  logs.weights[logs.weights.length - 1].kg = 78.4;
  s.logs[demoEmail] = logs;

  s.tickets = [
    { id: "TK-1042", email: demoEmail, name: "Aarav Sharma", subject: "AI Coach stopped replying", category: "Technical", status: "open", priority: "high", created: new Date(Date.now() - 864e5).toISOString(), messages: [{ from: "user", text: "The AI coach shows a typing dot and nothing happens.", at: new Date(Date.now() - 864e5).toISOString() }] },
    { id: "TK-1041", email: "nisha.patel@mail.com", name: "Nisha Patel", subject: "Refund for yearly plan", category: "Billing", status: "pending", priority: "medium", created: new Date(Date.now() - 3 * 864e5).toISOString(), messages: [{ from: "user", text: "I was charged twice for the yearly plan.", at: new Date(Date.now() - 3 * 864e5).toISOString() }, { from: "admin", text: "Checking with our payments team — refund in 3-5 days.", at: new Date(Date.now() - 2 * 864e5).toISOString() }] },
    { id: "TK-1038", email: "rohan.gupta@mail.com", name: "Rohan Gupta", subject: "Add Ragi Dosa to food database", category: "Feedback", status: "closed", priority: "low", created: new Date(Date.now() - 9 * 864e5).toISOString(), messages: [{ from: "user", text: "Please add more South Indian millet dishes.", at: new Date(Date.now() - 9 * 864e5).toISOString() }, { from: "admin", text: "Added. Thanks for the nudge!", at: new Date(Date.now() - 8 * 864e5).toISOString() }] },
  ];
  Store.set(s);
}
seedDemo();

Object.assign(window, {
  registerUser, loginUser, logoutUser, socialLogin, isLoggedIn, isAdmin,
  saveOnboarding, seedDemo, weakHash, handleGoogleCallback,
  requestPasswordReset, performPasswordReset, api
});

document.addEventListener("DOMContentLoaded", async () => {
  // Dynamically load public server config if hosted on backend
  if (typeof FP_CONFIG !== "undefined" && FP_CONFIG.API_BASE_URL) {
    try {
      const cfg = await api("/config", null, "GET");
      if (cfg && cfg.ok) {
        if (cfg.googleClientId) {
          const gDiv = document.getElementById("g_id_onload");
          if (gDiv) gDiv.setAttribute("data-client_id", cfg.googleClientId);
        }
        if (cfg.razorpayKeyId) {
          FP_CONFIG.PAYMENT_KEY_ID = cfg.razorpayKeyId;
        }
      }
    } catch (_) {}
  }

  const gDiv = document.getElementById("g_id_onload");
  if (gDiv && (!gDiv.getAttribute("data-client_id") || gDiv.getAttribute("data-client_id") === "YOUR_GOOGLE_CLIENT_ID")) {
    setTimeout(() => {
      const container = document.querySelector(".g_id_signin");
      if (container) {
        container.style.display = "none";
        const dummy = document.createElement("button");
        dummy.className = "btn btn-block btn-ghost";
        dummy.style.marginTop = "20px";
        dummy.style.justifyContent = "center";
        dummy.innerHTML = `<img src="https://www.svgrepo.com/show/475656/google-color.svg" width="18" height="18" style="margin-right:10px">Continue with Google`;
        dummy.onclick = (e) => {
          e.preventDefault();
          confirmDialog(
            "Google Setup Required", 
            "Google Login requires a real Client ID in your .env file (GOOGLE_CLIENT_ID). Would you like to use the demo account instead?", 
            "Use Demo Account"
          ).then(res => {
            if(res) {
              loginUser({email: "demo@fitpulse.app", password: "demo1234", remember: false}).then(r => r.ok && location.replace("dashboard.html"));
            }
          });
        };
        container.parentNode.insertBefore(dummy, container);
      }
    }, 100);
  }
});

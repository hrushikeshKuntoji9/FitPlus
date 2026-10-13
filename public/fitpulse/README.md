# FitPulse

Plain HTML/CSS/JS health & fitness site. No build step.

## Run
Serve this folder with any static server (`npx serve .` or VS Code Live Server) and open `index.html`.
Demo logins: `demo@fitpulse.app / demo1234`, admin `admin@fitpulse.app / admin1234`.

## Structure
- `*.html` — one file per page (home, auth, onboarding, dashboard, trackers, coach, profile, settings, pricing, checkout, admin pages)
- `css/style.css` — the whole design system (light/dark)
- `js/app.js` — storage layer, helpers, navbar/footer, charts, config (`FP_CONFIG`)
- `js/auth.js` — register/login/logout + demo data seed
- `data/foods.json`, `data/workouts.json`, `data/meal-plans.json`

## Authentication
Demo mode stores users in localStorage (not secure). Set `FP_CONFIG.API_BASE_URL` in `js/app.js` and `auth.js` will call `/auth/login`, `/auth/register`, `/auth/logout` on your backend instead.

## Add foods / workouts
Edit `data/foods.json` or `data/workouts.json`, or use Admin → Foods / Workouts (saved as custom items).

## AI API key
Set `FP_CONFIG.AI_API_URL` to your own backend endpoint that calls the AI provider. Never put a secret key in frontend code. The endpoint receives `{ messages, profile }` and returns `{ reply }`.

## Real database
Replace the `Store` object in `js/app.js` (and the "LOCAL DEMO" blocks in `auth.js`) with fetch calls to your API (Supabase, Firebase, your own server).

## Razorpay / Stripe
In `checkout.html`, replace the demo `setTimeout` with the Razorpay Checkout or Stripe Checkout call using `FP_CONFIG.PAYMENT_KEY_ID`, and verify payments on your server.

## Deploy
Upload the folder to Netlify, Vercel, GitHub Pages or any static host.

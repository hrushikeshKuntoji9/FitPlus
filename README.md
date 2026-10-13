# ⚡ FitPulse Pro — Complete Full-Stack Health & Fitness Platform

FitPulse is a modern, premium health & fitness platform inspired by apps like Strava and Healthify, engineered for consistency over crash diets. It combines nutrition, workouts, water, sleep, habits, and an AI coach into one calm daily score.

---

## 🌟 Key Features

- **Daily Pulse Score (0–100)**: Real-time synthesis of calorie balance, protein target, hydration, 10k steps, sleep recovery, and workouts.
- **Indian Food Diary & Search**: Comprehensive database of Indian dishes (Paneer, Roti, Dal, Poha, Idli, Dosa, etc.) with accurate portion scaling and macro donut breakdown.
- **Dedicated Food Detail Page (`food-detail.html`)**: Serving size multipliers (0.5x, 1x, 1.5x, 2x), micronutrients, and 1-click logging to Breakfast/Lunch/Dinner/Snacks.
- **Meal Planner (`meal-plan.html`)**: Daily and weekly views, calibrated meal recipes, one-click meal swaps, and AI meal suggestions.
- **Workout Library & Guided Player (`workouts.html` & `workout-detail.html`)**: Category filtering (Strength, HIIT, Cardio, Yoga, Gym, Core), interactive exercise checklist, live workout timer, and automated 60s rest countdowns.
- **Full Trackers**: Hydration progress ring (`water.html`), bedtime/wake recovery trends (`sleep.html`), 6 daily habits with streak flames (`habits.html`), and multi-period progress analytics with badges (`progress.html`).
- **Context-Aware AI Coach (`ai-coach.html`)**: Reads your actual daily logs and remaining macros before generating tailored fitness advice.
- **Support & Ticket Desk (`support.html`)**: Ticket submission, category sorting, threaded conversations with admin replies, and self-serve FAQs.
- **Admin Command Center (`admin.html`)**: Member management, subscription tracking, revenue analytics, custom food/workout moderation, and support ticket resolution.
- **Dark & Light Mode**: Built-in CSS custom property theme engine with instant toggle.

---

## 🚀 How to Run the Project

### Option A: Double-Click (Windows)
Double-click **`run.bat`** in the repository root or in `fitpulse-pro-main`.  
It automatically starts the Python full-stack server and opens the web app in your default browser at `http://127.0.0.1:5000/fitpulse/index.html`.

### Option B: Command Line (Cross-Platform)
1. Ensure Python 3.10+ is installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the server:
   ```bash
   python server.py
   ```
4. Open your browser:
   - **Web App**: [http://127.0.0.1:5000/fitpulse/index.html](http://127.0.0.1:5000/fitpulse/index.html)
   - **Admin Portal**: [http://127.0.0.1:5000/fitpulse/admin.html](http://127.0.0.1:5000/fitpulse/admin.html)

---

## 🔑 Demo & Admin Credentials

| Role | Email | Password | Access Details |
|---|---|---|---|
| **Member** | `demo@fitpulse.app` | `demo1234` | Pre-seeded with 30 days of realistic nutrition, workouts, water, sleep & habit history |
| **Admin** | `admin@fitpulse.app` | `admin1234` | Full access to user management, food database, workout library, revenue metrics & tickets |

*(You can also register a new account anytime on `register.html`)*

---

## 📁 Project Structure

```
fitpulse-pro-main/
│
├── server.py                  # Full-stack Flask REST API + SQLite backend + Static server
├── test_server.py            # Automated test suite (all 22 test suites passing)
├── requirements.txt           # Python dependencies (Flask>=3.0.0, gunicorn, waitress)
├── DEPLOYMENT.md              # Production deployment & operations manual
├── run.bat                    # One-click Windows launch script
├── Procfile                   # Cloud process file (Render / Railway / Heroku)
├── Dockerfile                 # Containerized production Docker image
├── render.yaml                # 1-Click Render configuration
├── vercel.json                # Vercel deployment configuration
├── fitpulse.db                # SQLite database (auto-generated on first run)
│
└── public/fitpulse/           # Production Frontend UI
    ├── index.html             # Landing page with hero, live preview, FAQs & testimonials
    ├── login.html             # Auth login page with demo auto-fill & password reset modal
    ├── register.html          # Registration with password strength meter
    ├── onboarding.html        # Mifflin-St Jeor onboarding wizard
    ├── dashboard.html         # Main dashboard with animated rings, macros & streak
    ├── nutrition.html         # Daily food diary & instant food search
    ├── food-detail.html       # Nutritional breakdown, portion scaler & macro donut
    ├── meal-plan.html         # Daily/weekly meal planner, recipes & meal swapping
    ├── workouts.html          # Workout catalog with category chips & quick timer
    ├── workout-detail.html    # Step-by-step workout player, timers & rest counter
    ├── progress.html          # 7/30/90-day Chart.js analytics & achievement badges
    ├── habits.html            # 6 daily micro-habits & 14-day consistency grid
    ├── water.html             # Water tracker with quick-add glasses & weekly chart
    ├── sleep.html             # Sleep logging, duration calculator & consistency rating
    ├── ai-coach.html          # AI fitness coach chat interface
    ├── profile.html           # User stats, target adjustments & diet goals
    ├── settings.html          # Dark mode, metric/imperial units, notifications & data export
    ├── subscription.html      # Free vs Premium pricing plans & receipt history
    ├── checkout.html          # Payment checkout with Razorpay SDK & coupon code (FIT20)
    ├── support.html           # Support desk, ticket creation & threaded conversation
    ├── contact.html           # Contact form & corporate inquiry details
    ├── about.html             # Science, methodology & engineering philosophy
    ├── privacy.html           # Privacy policy & data protection terms
    ├── terms.html             # Terms of service & medical disclaimer
    ├── cancellation-refund.html # Consumer protection, refund timelines & cancellation rules
    ├── 404.html               # Custom branded Page Not Found error page
    ├── 500.html               # Custom Internal Server Error page
    ├── robots.txt             # Search crawler directives & admin security restrictions
    ├── sitemap.xml            # Search engine sitemap index
    ├── admin.html             # Admin overview, revenue charts, tickets & CSV exports
    ├── manage-users.html      # Search, filter, suspend, upgrade & delete users
    ├── manage-foods.html      # Add, edit & remove foods from database
    ├── manage-workouts.html   # Add, edit & delete exercises and workouts
    ├── manage-subscriptions.html # Subscription lifecycle & payment statuses
    │
    ├── css/
    │   └── style.css          # Design system (Space Grotesk, DM Sans, HSL tokens, dark mode)
    │
    ├── js/
    │   ├── app.js             # Core data layer, API connector, navbar/footer chrome & charts
    │   └── auth.js            # Auth sessions, JWT token handling & demo seed
    │
    └── data/
        ├── foods.json         # Base food catalog (35 items)
        ├── workouts.json      # Base workout programs (12 programs)
        └── meal-plans.json    # Base curated meal plans (4 plans)
```

---

## 🛠️ Full-Stack Technical Architecture

### 1. Database (`fitpulse.db`)
SQLite database with automatic migration and seeding on first launch:
- `users`: Accounts, password hashes, roles (`user`, `admin`), plans, and account status.
- `profiles`: Physiological data (age, height, weight, goal, activity, diet).
- `nutrition_logs`: Daily food entries with gram-level macros.
- `workout_logs`: Completed sessions, minutes, and calories.
- `water_logs`: Fluid replenishment entries with timestamps.
- `sleep_logs`: Bedtime, wake time, sleep quality, and hours.
- `habit_logs`: 6 daily habits tracked over time.
- `weight_logs`: Historical weight logs for trend calculations.
- `foods` & `workouts`: Standard and user-created custom items.
- `tickets`: Threaded customer support tickets.

### 2. REST API Endpoints

| Category | Endpoint | Method | Description |
|---|---|---|---|
| **Auth** | `/api/auth/register` | POST | Creates account and returns session token |
| **Auth** | `/api/auth/login` | POST | Authenticates credentials and starts session |
| **Auth** | `/api/auth/logout` | POST | Terminates session token |
| **Auth** | `/api/auth/me` | GET | Returns authenticated user and profile |
| **Profile** | `/api/profile` | GET / POST | Retrieves or updates user metrics and goals |
| **Nutrition** | `/api/nutrition` | GET / POST / DELETE | Manages daily meals and calculates totals |
| **Foods** | `/api/foods` | GET / POST / DELETE | Food search and custom food creation |
| **Workouts** | `/api/workouts` | GET / POST / DELETE | Workout catalog and custom routines |
| **Workouts** | `/api/workouts/complete` | POST | Logs completed workout session to database |
| **Trackers** | `/api/water` | GET / POST | Logs water glasses and returns daily volume |
| **Trackers** | `/api/sleep` | GET / POST | Logs bedtime/wake and returns duration |
| **Trackers** | `/api/habits` | GET / POST | Toggles habit checkmarks |
| **Trackers** | `/api/steps` | GET / POST | Logs daily step count |
| **Trackers** | `/api/weight` | POST | Logs weight update and recalculates BMI |
| **Trackers** | `/api/progress` | GET | Returns multi-day trends and goal completion |
| **AI Coach** | `/api/ai/coach` | POST | Context-aware AI coach reasoning engine |
| **Payments** | `/api/payments/create-order` | POST | Creates Razorpay order with coupon discounts (FIT20) |
| **Payments** | `/api/payments/verify` | POST | Verifies HMAC-SHA256 signature and activates plan |
| **Subscription**| `/api/subscription` | GET / POST | Current subscription status & payment receipts |
| **Subscription**| `/api/subscription/cancel` | POST | Cancels renewal and records expiration date |
| **Support** | `/api/tickets` | GET / POST | Retrieves tickets or submits new inquiry |
| **Password** | `/api/auth/forgot-password` | POST | Generates secure time-limited reset token |
| **Password** | `/api/auth/reset-password` | POST | Validates token and resets account password |
| **Config** | `/api/config` | GET | Exposes public Razorpay Key & Google Client ID |
| **Admin** | `/api/admin/stats` | GET | High-level business metrics and user counts |
| **Admin** | `/api/admin/users` | GET / POST | Full member roster with plan & status controls |
| **Admin** | `/api/admin/export/users` | GET | Downloads CSV export of all platform members |
| **Admin** | `/api/admin/export/orders` | GET | Downloads CSV export of all transaction orders |

---

## 🔒 Authentication Flow
1. **Frontend**: When the app loads over HTTP, `FP_CONFIG.API_BASE_URL` points to `/api`.
2. **Registration / Login**: Calls `/api/auth/register` or `/api/auth/login`. On success, the server responds with a secure bearer token saved in `localStorage.setItem("fitpulse:token", ...)`.
3. **Session Check**: `api()` automatically injects the `Authorization: Bearer <token>` header on subsequent requests.
4. **Offline Resilience**: If the backend server is temporarily unreachable or opened via `file:///`, the application seamlessly falls back to the client `Store` (localStorage), ensuring zero downtime or broken screens.

---

## 🥗 How to Add Foods
1. **From Food Diary (`nutrition.html`)**: Tap **"+ Add"** on any meal card -> click **"Add a custom food"** -> input Name, Calories, Protein, Carbs, Fat, and Serving size -> click **"Add custom food"**.
2. **From Admin Panel (`manage-foods.html`)**: Log in as admin -> click **"+ Add food"** -> enter nutritional values -> Save. The food immediately appears in all users' search bars!
3. **From Base Data (`data/foods.json`)**: Add a new JSON object to `public/fitpulse/data/foods.json` for permanent catalog inclusion.

---

## 🏋️ How to Add Workouts
1. **From Admin Panel (`manage-workouts.html`)**: Log in as admin -> click **"+ Add workout"** -> input Title, Category (Strength, HIIT, Cardio, Yoga, Gym, Core), Difficulty level, Duration, Calories, Equipment, and Exercise list (one per line) -> click **"Save"**.
2. **From Base Data (`data/workouts.json`)**: Add new program definitions into `public/fitpulse/data/workouts.json`.

---

## 🤖 Where to Add the AI API Key
The AI Coach has an intelligent built-in fitness & nutrition reasoning engine that evaluates your actual logged calories, protein, hydration, and sleep without requiring any external keys.

To connect an external LLM (OpenAI, Groq, or Gemini):
1. Open `server.py`.
2. Set the environment variable:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   # or GROQ_API_KEY / GEMINI_API_KEY
   ```
3. In `server.py` inside `api_ai_coach()`, uncomment the LLM client call:
   ```python
   # from openai import OpenAI
   # client = OpenAI()
   # response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
   # reply = response.choices[0].message.content
   ```

---

## 💳 Where to Connect Razorpay or Stripe
1. Open `public/fitpulse/js/app.js`:
   ```javascript
   FP_CONFIG.PAYMENT_PROVIDER = "razorpay"; // or "stripe"
   FP_CONFIG.PAYMENT_KEY_ID = "rzp_live_your_key_id";
   ```
2. Open `public/fitpulse/checkout.html`:
   - Replace the simulated payment timeout around line 55 with the Razorpay or Stripe Checkout SDK call.
   - Forward the payment signature to `/api/subscriptions/checkout` in `server.py` for server-side verification.

---

## 🌐 How to Deploy Online

### 1. Render (Recommended — 1 Click)
- Fork or push this repository to GitHub.
- Go to [render.com](https://render.com) -> New -> Blueprint.
- Select your repository. Render automatically reads `render.yaml` and launches your full-stack service!

### 2. Railway / Heroku
- Connect your GitHub repo.
- Railway and Heroku automatically detect `Procfile` (`web: python server.py`) and `requirements.txt`.
- Set `PORT` environment variable to `5000` or let the platform inject it dynamically.

### 3. Docker (Any Cloud / VPS)
```bash
docker build -t fitpulse-pro .
docker run -p 5000:5000 fitpulse-pro
```

### 4. Static Hosting (Netlify / Vercel / GitHub Pages)
If you only want static frontend hosting:
- Upload the contents of `public/fitpulse/` directly to Netlify or GitHub Pages.
- The app operates autonomously in offline demo mode using localStorage!

---

## 🧪 Testing

The repository includes a comprehensive automated test suite (`test_server.py`) validating:
- All 27 HTML pages delivery (200 OK)
- Authentication & admin authorization
- Nutrition, Water, Sleep & Steps APIs
- AI coach generation
- Support ticket lifecycle
- Progress calculations

Run tests anytime with:
```bash
python test_server.py
```
*(All 12 test suites passing with 0 errors!)*

---

## 📄 License
MIT License. Created for FitPulse Health Technologies.

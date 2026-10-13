#!/usr/bin/env python3
"""
FitPulse Automated Backend & Full-Stack Test Suite
Validates all API endpoints, database operations, and static file deliveries.
"""

import unittest
import json
from server import app, get_db

class FitPulseFullStackTestCase(unittest.TestCase):
    def setUp(self):
        app.testing = True
        app.config["TESTING"] = True
        self.app = app.test_client()
        login_res = self.app.post("/api/auth/login", json={"email": "demo@fitpulse.app", "password": "demo1234"})
        if login_res.status_code == 200:
            token = login_res.get_json().get("token")
            self.auth_headers = {"Authorization": f"Bearer {token}"}
        else:
            self.auth_headers = {}

    def test_01_static_pages(self):
        pages = [
            "/fitpulse/index.html",
            "/fitpulse/login.html",
            "/fitpulse/register.html",
            "/fitpulse/onboarding.html",
            "/fitpulse/dashboard.html",
            "/fitpulse/nutrition.html",
            "/fitpulse/food-detail.html",
            "/fitpulse/meal-plan.html",
            "/fitpulse/workouts.html",
            "/fitpulse/workout-detail.html",
            "/fitpulse/progress.html",
            "/fitpulse/habits.html",
            "/fitpulse/water.html",
            "/fitpulse/sleep.html",
            "/fitpulse/ai-coach.html",
            "/fitpulse/profile.html",
            "/fitpulse/settings.html",
            "/fitpulse/subscription.html",
            "/fitpulse/checkout.html",
            "/fitpulse/support.html",
            "/fitpulse/about.html",
            "/fitpulse/contact.html",
            "/fitpulse/admin.html",
            "/fitpulse/manage-users.html",
            "/fitpulse/manage-foods.html",
            "/fitpulse/manage-workouts.html",
            "/fitpulse/manage-subscriptions.html",
            "/fitpulse/privacy.html",
            "/fitpulse/terms.html",
            "/fitpulse/cancellation-refund.html",
            "/fitpulse/404.html",
            "/fitpulse/500.html",
            "/robots.txt",
            "/sitemap.xml"
        ]
        for page in pages:
            res = self.app.get(page)
            self.assertEqual(res.status_code, 200, f"Page {page} returned status {res.status_code}")

    def test_02_auth_login(self):
        res = self.app.post("/api/auth/login", json={
            "email": "demo@fitpulse.app",
            "password": "demo1234"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("token", data)
        self.assertEqual(data["data"]["email"], "demo@fitpulse.app")

    def test_03_auth_admin(self):
        res = self.app.post("/api/auth/login", json={
            "email": "admin@fitpulse.app",
            "password": "admin1234"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["data"]["role"], "admin")

    def test_04_nutrition_api(self):
        # 0. Unauthorized access without cookies or bearer token should be rejected
        unauth_client = app.test_client()
        unauth_res = unauth_client.get("/api/nutrition?date=2026-10-10")
        self.assertEqual(unauth_res.status_code, 401)

        # 1. Fetch today's nutrition with auth
        res = self.app.get("/api/nutrition?date=2026-10-10", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("meals", data)
        self.assertIn("totals", data)

        # 2. Add food item
        res = self.app.post("/api/nutrition?date=2026-10-10", json={
            "meal": "breakfast",
            "food": {
                "name": "Test Paneer Paratha",
                "calories": 280,
                "protein": 12,
                "carbs": 35,
                "fat": 10,
                "fiber": 3,
                "serving": "1 paratha"
            }
        }, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("logId", data)

    def test_05_water_and_sleep_api(self):
        # Water
        res = self.app.post("/api/water?date=2026-10-10", json={"ml": 500}, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertGreaterEqual(data.get("total", 0), 500)

        # Sleep
        res = self.app.post("/api/sleep?date=2026-10-10", json={
            "bedtime": "23:00",
            "wake": "07:00",
            "hours": 8.0,
            "quality": "Rested"
        }, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)

    def test_06_ai_coach_api(self):
        res = self.app.post("/api/ai/coach", json={
            "messages": [
                {"from": "user", "text": "How much protein should I have today?"}
            ],
            "profile": {"goal": "lose", "weight": 78}
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("protein", data.get("reply", "").lower())

    def test_07_support_tickets_api(self):
        res = self.app.post("/api/tickets", json={
            "subject": "App testing query",
            "category": "Technical",
            "priority": "low",
            "message": "Testing the ticket creation pipeline"
        }, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("id", data)

    def test_08_admin_stats_api(self):
        login_res = self.app.post("/api/auth/login", json={
            "email": "admin@fitpulse.app",
            "password": "admin1234"
        })
        self.assertEqual(login_res.status_code, 200)
        token = login_res.get_json()["token"]

        res = self.app.get("/api/admin/stats", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertGreater(data.get("members", 0), 0)

        # Confirm unauthenticated request without cookie/token is blocked
        clean_client = app.test_client()
        unauth_res = clean_client.get("/api/admin/stats")
        self.assertEqual(unauth_res.status_code, 401)

    def test_09_user_registration(self):
        import secrets
        rnd_email = f"user_{secrets.token_hex(4)}@testfitpulse.com"
        res = self.app.post("/api/auth/register", json={
            "name": "Priya Sharma",
            "email": rnd_email,
            "password": "testpassword123"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("token", data)
        self.assertEqual(data["data"]["email"], rnd_email)

    def test_10_workouts_and_completion(self):
        # 1. List workouts (public)
        res = self.app.get("/api/workouts")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertGreater(len(data.get("data", [])), 0)

        # 2. Complete workout (authenticated member)
        res = self.app.post("/api/workouts/complete", json={
            "name": "HIIT Burn 20",
            "minutes": 20,
            "calories": 280,
            "category": "HIIT"
        }, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))

    def test_11_weight_and_progress(self):
        # 1. Log weight
        res = self.app.post("/api/weight", json={"kg": 77.8}, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)

        # 2. Progress summary
        res = self.app.get("/api/progress?days=30", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("current", data)
        self.assertIn("bmi", data)

    def test_12_habits_and_steps(self):
        # 1. Toggle habit
        res = self.app.post("/api/habits", json={"habit_id": "water"}, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))

        # 2. Log steps
        res = self.app.post("/api/steps", json={"steps": 10500}, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("steps"), 10500)

    def test_13_subscription_and_orders_api(self):
        # 1. Log in as demo user
        login_res = self.app.post("/api/auth/login", json={"email": "demo@fitpulse.app", "password": "demo1234"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create order with coupon
        order_res = self.app.post("/api/payments/create-order", json={"plan": "monthly", "coupon": "FIT20"}, headers=headers)
        self.assertEqual(order_res.status_code, 200)
        odata = order_res.get_json()
        self.assertTrue(odata.get("ok"))
        self.assertIn("orderId", odata)
        self.assertEqual(odata["discount"], 40) # 20% of 199 rounded

        # 3. Verify payment
        order_id = odata["orderId"]
        v_res = self.app.post("/api/payments/verify", json={"orderId": order_id, "method": "card"}, headers=headers)
        self.assertEqual(v_res.status_code, 200)
        vdata = v_res.get_json()
        self.assertTrue(vdata.get("ok"))
        self.assertEqual(vdata.get("plan"), "premium")

        # 4. Check subscription endpoint
        sub_res = self.app.get("/api/subscription", headers=headers)
        self.assertEqual(sub_res.status_code, 200)
        sub_data = sub_res.get_json()
        self.assertTrue(sub_data.get("ok"))
        self.assertEqual(sub_data.get("plan"), "premium")
        self.assertGreater(len(sub_data.get("orders", [])), 0)

        # 5. Cancel subscription
        c_res = self.app.post("/api/subscription/cancel", headers=headers)
        self.assertEqual(c_res.status_code, 200)
        self.assertTrue(c_res.get_json().get("ok"))

    def test_14_forgot_and_reset_password_api(self):
        # 1. Request forgot password
        res = self.app.post("/api/auth/forgot-password", json={"email": "demo@fitpulse.app"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        dev_token = data.get("_dev_token")
        self.assertIsNotNone(dev_token)

        # 2. Reset password using token
        rst_res = self.app.post("/api/auth/reset-password", json={"token": dev_token, "password": "tempNewPass123"})
        self.assertEqual(rst_res.status_code, 200)
        self.assertTrue(rst_res.get_json().get("ok"))

        # 3. Log in with new password
        login_res = self.app.post("/api/auth/login", json={"email": "demo@fitpulse.app", "password": "tempNewPass123"})
        self.assertEqual(login_res.status_code, 200)

        # 4. Restore demo1234 password
        token = login_res.get_json()["token"]
        chg_res = self.app.post("/api/auth/change-password", json={
            "currentPassword": "tempNewPass123",
            "newPassword": "demo1234"
        }, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(chg_res.status_code, 200)

    def test_15_admin_export_csv_api(self):
        # 1. Admin login
        login_res = self.app.post("/api/auth/login", json={"email": "admin@fitpulse.app", "password": "admin1234"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Export users CSV
        u_res = self.app.get("/api/admin/export/users", headers=headers)
        self.assertEqual(u_res.status_code, 200)
        self.assertIn("text/csv", u_res.headers.get("Content-Type", ""))
        self.assertIn("Email", u_res.get_data(as_text=True))

        # 3. Export orders CSV
        o_res = self.app.get("/api/admin/export/orders", headers=headers)
        self.assertEqual(o_res.status_code, 200)
        self.assertIn("text/csv", o_res.headers.get("Content-Type", ""))

    def test_16_ai_coach_api(self):
        # 1. Unauthenticated / anonymous AI coach call
        res = self.app.post("/api/ai/coach", json={"message": "What should I eat for dinner?", "profile": {"diet": "vegetarian", "goal": "stay fit"}})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("reply", data)
        self.assertIn("provider", data)

        # 2. Authenticated user call (accessing DB metrics)
        login_res = self.app.post("/api/auth/login", json={"email": "demo@fitpulse.app", "password": "demo1234"})
        token = login_res.get_json()["token"]
        auth_res = self.app.post("/api/ai/coach", json={"message": "Am I getting enough protein?"}, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(auth_res.status_code, 200)
        auth_data = auth_res.get_json()
        self.assertTrue(auth_data.get("ok"))
        self.assertIn("protein", auth_data.get("reply", "").lower())

    def test_17_stripe_payment_session(self):
        login_res = self.app.post("/api/auth/login", json={"email": "demo@fitpulse.app", "password": "demo1234"})
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = self.app.post("/api/payments/stripe/create-checkout-session", json={"plan": "yearly", "coupon": "FIT20"}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("checkoutUrl", data)
        self.assertIn("orderId", data)

    def test_18_health_check_and_config(self):
        # Health check
        h_res = self.app.get("/api/health")
        self.assertEqual(h_res.status_code, 200)
        h_data = h_res.get_json()
        self.assertEqual(h_data.get("status"), "healthy")
        self.assertEqual(h_data.get("database"), "connected")

        # Config check
        c_res = self.app.get("/api/config")
        self.assertEqual(c_res.status_code, 200)
        c_data = c_res.get_json()
        self.assertTrue(c_data.get("ok"))
        self.assertIn("aiProvider", c_data)

    def test_19_user_orders_endpoint(self):
        login_res = self.app.post("/api/auth/login", json={"email": "demo@fitpulse.app", "password": "demo1234"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = self.app.get("/api/user/orders", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIsInstance(data.get("data"), list)

    def test_20_contact_enquiry_flow(self):
        # 1. Submit contact inquiry
        res = self.app.post("/api/contact", json={
            "name": "Priya Patel",
            "email": "priya.patel@example.com",
            "subject": "[Partnership] Gym Integration Inquiry",
            "message": "We would like to connect our fitness studio with FitPulse Pro platform."
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("id", data)

        # 2. Verify admin can view enquiries
        login_res = self.app.post("/api/auth/login", json={"email": "admin@fitpulse.app", "password": "admin1234"})
        admin_token = login_res.get_json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        a_res = self.app.get("/api/admin/enquiries", headers=admin_headers)
        self.assertEqual(a_res.status_code, 200)
        a_data = a_res.get_json()
        self.assertTrue(a_data.get("ok"))
        self.assertTrue(any(e["email"] == "priya.patel@example.com" for e in a_data.get("data", [])))

    def test_21_support_ticket_reply_flow(self):
        # 1. Login user
        login_res = self.app.post("/api/auth/login", json={"email": "demo@fitpulse.app", "password": "demo1234"})
        token = login_res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create ticket
        t_res = self.app.post("/api/tickets", json={
            "subject": "Question about macros",
            "category": "Nutrition",
            "priority": "medium",
            "message": "How do I adjust my protein targets?"
        }, headers=headers)
        self.assertEqual(t_res.status_code, 200)
        ticket_id = t_res.get_json()["id"]

        # 3. User replies to their own ticket
        r_res = self.app.put("/api/tickets", json={
            "id": ticket_id,
            "reply": "Follow up: I prefer vegetarian protein sources."
        }, headers=headers)
        self.assertEqual(r_res.status_code, 200)
        self.assertTrue(r_res.get_json().get("ok"))

        # 4. Verify message exists
        list_res = self.app.get("/api/tickets", headers=headers)
        self.assertEqual(list_res.status_code, 200)
        tickets = list_res.get_json().get("data", [])
        my_t = next((t for t in tickets if t["id"] == ticket_id), None)
        self.assertIsNotNone(my_t)
        self.assertGreaterEqual(len(my_t["messages"]), 2)

    def test_22_custom_error_pages(self):
        # 1. Non-existent API route returns JSON 404
        api_res = self.app.get("/api/non-existent-route-999")
        self.assertEqual(api_res.status_code, 404)
        self.assertEqual(api_res.content_type, "application/json")
        self.assertFalse(api_res.get_json().get("ok"))

        # 2. Non-existent HTML route returns 404 HTML page
        page_res = self.app.get("/fitpulse/non-existent-page-xyz.html")
        self.assertEqual(page_res.status_code, 404)
        self.assertIn("Page Not Found", page_res.get_data(as_text=True))

if __name__ == "__main__":
    unittest.main()

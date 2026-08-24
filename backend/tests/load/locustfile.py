"""
Load test with Locust — simulates warehouse operations.

Run: locust -f tests/load/locustfile.py --host http://localhost:8000

Simulates:
- Operators scanning barcodes and confirming picks
- Client portal users checking inventory
- AGV systems polling for tasks
"""

from locust import HttpUser, between, task


class WarehouseOperator(HttpUser):
    """Simulates a warehouse floor operator using RF gun."""

    wait_time = between(1, 3)
    weight = 5  # Most common user type

    def on_start(self):
        # Login and get token
        resp = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "operator@test.com",
                "password": "test123",
            },
        )
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}

    @task(3)
    def list_inventory(self):
        self.client.get("/api/v1/inventory/", headers=self.headers)

    @task(2)
    def list_tasks(self):
        self.client.get("/api/v1/tasks/?status=pending", headers=self.headers)

    @task(2)
    def list_outbound_orders(self):
        self.client.get("/api/v1/orders/outbound?status=picking", headers=self.headers)

    @task(1)
    def list_inbound_orders(self):
        self.client.get("/api/v1/orders/inbound?status=receiving", headers=self.headers)


class ClientPortalUser(HttpUser):
    """Simulates a cargo owner checking their portal."""

    wait_time = between(3, 8)
    weight = 2

    def on_start(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "client@test.com",
                "password": "test123",
            },
        )
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}

    @task(3)
    def portal_dashboard(self):
        self.client.get("/api/v1/portal/dashboard?client_id=test", headers=self.headers)

    @task(2)
    def portal_inventory(self):
        self.client.get("/api/v1/portal/inventory?client_id=test", headers=self.headers)

    @task(1)
    def portal_orders(self):
        self.client.get("/api/v1/portal/orders/outbound?client_id=test", headers=self.headers)

    @task(1)
    def portal_invoices(self):
        self.client.get("/api/v1/portal/invoices?client_id=test", headers=self.headers)


class AGVScheduler(HttpUser):
    """Simulates AGV fleet management system polling for tasks."""

    wait_time = between(2, 5)
    weight = 1

    def on_start(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "agv-service@test.com",
                "password": "test123",
            },
        )
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}

    @task(5)
    def poll_pending_tasks(self):
        self.client.get(
            "/api/v1/agv/tasks/pending?warehouse_id=test-wh",
            headers=self.headers,
        )

    @task(1)
    def get_location_map(self):
        self.client.get(
            "/api/v1/agv/locations/test-wh",
            headers=self.headers,
        )

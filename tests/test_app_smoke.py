import unittest

try:
    from fastapi.testclient import TestClient
except RuntimeError:  # httpx optional in this environment
    TestClient = None

import main


@unittest.skipIf(TestClient is None, "httpx is not installed")
class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def test_healthz_route_is_live(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "ok")

    def test_home_route_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ecuaciones a Word", response.text)

    def test_legacy_route_redirects(self):
        response = self.client.get("/blog-en-1.html", follow_redirects=False)
        self.assertIn(response.status_code, (301, 307))
        self.assertTrue(response.headers["location"].startswith("/en/blog/"))


if __name__ == "__main__":
    unittest.main()

"""Frontend/backend contract tests. They need no database and no browser:

    python -m unittest tests.test_frontend_static -v        (run from the project root)

They check that every API call made by backend/static/js/api.js exists in the real Flask app with the
right HTTP method, that request/response field names match the backend source, that CSRF/session rules
behave as the frontend expects, and that every page, script import, element id and link resolves.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATIC = ROOT / "backend" / "static"
ROUTES = ROOT / "backend" / "routes"

from backend.app import create_app  # noqa: E402


def read(path):
    return Path(path).read_text(encoding="utf-8")


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app({"TESTING": True, "MYSQL_CONFIG": {"user": "unused"}})
        cls.adapter = cls.app.url_map.bind("localhost")

    def test_every_api_url_and_method_exists_in_flask(self):
        checked = 0
        for line in read(STATIC / "js" / "api.js").splitlines():
            for raw in re.findall(r"""['"`](/api/[^'"`]*)['"`]""", line):
                path = re.sub(r"\$\{[^}]*\}", "1", raw).split("?")[0]
                method = "GET"
                if re.search(r"request\('PATCH'", line):
                    method = "PATCH"
                elif re.search(r"request\('POST'|\bpost\(", line):
                    method = "POST"
                with self.subTest(method=method, path=path):
                    self.adapter.match(path, method=method)  # raises NotFound/MethodNotAllowed
                checked += 1
        self.assertGreaterEqual(checked, 25)

    def test_request_fields_are_read_by_the_backend(self):
        expectations = {
            "auth.py": ["name", "email", "password", "phone"],
            "claims.py": ["ownership_evidence", "decision", "remarks", "reason"],
            "items.py": ["title", "description", "category_id", "location_id", "item_date", "item_type", "images"],
        }
        frontend = "".join(read(p) for p in STATIC.rglob("*.js"))
        for filename, keys in expectations.items():
            backend = read(ROUTES / filename)
            for key in keys:
                with self.subTest(file=filename, field=key):
                    self.assertIn(f'"{key}"', backend)
                    self.assertRegex(frontend, rf"\b{key}\b")

    def test_response_fields_used_by_the_frontend_are_produced_by_the_backend(self):
        backend = "".join(read(p) for p in ROUTES.glob("*.py"))
        frontend = "".join(read(p) for p in STATIC.rglob("*.js"))
        for field in ["csrf_token", "user", "items", "images", "claims", "notifications", "unread_count", "claim_id",
                      "is_read", "handover", "handover_date", "items_by_status", "claims_by_status",
                      "claims_awaiting_admin", "claims_awaiting_finder", "item_title", "item_status",
                      "claimant_name", "ownership_evidence", "finder_decision", "admin_decision", "finder_remarks",
                      "admin_remarks", "categories", "locations", "category_name", "location_name", "error"]:
            with self.subTest(field=field):
                self.assertIn(f'"{field}"', backend)
                self.assertIn(field, frontend)

    def test_csrf_and_session_behaviour_matches_api_client(self):
        client = self.app.test_client()
        self.assertEqual(client.get("/api/auth/me").status_code, 401)
        self.assertEqual(client.post("/api/auth/login", json={}).status_code, 403)  # no token yet
        token = client.get("/api/auth/csrf").get_json()["csrf_token"]
        self.assertTrue(token)
        self.assertEqual(client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code, 403)
        self.assertEqual(client.post("/api/auth/logout", headers={"X-CSRF-Token": token}).status_code, 200)
        self.assertIn("X-CSRF-Token", read(STATIC / "js" / "api.js"))

    def test_static_files_are_served_by_flask(self):
        client = self.app.test_client()
        for page in sorted(STATIC.glob("*.html")):
            with self.subTest(page=page.name):
                with client.get(f"/static/{page.name}") as response:
                    self.assertEqual(response.status_code, 200)
        for asset in ("/static/js/api.js", "/static/css/styles.css"):
            with client.get(asset) as response:
                self.assertEqual(response.status_code, 200)


class StaticFrontendTests(unittest.TestCase):
    def setUp(self):
        self.pages = sorted(STATIC.glob("*.html"))
        self.js_files = sorted((STATIC / "js").rglob("*.js"))
        self.all_js = {p: read(p) for p in self.js_files}

    def test_pages_have_layout_slots_scripts_and_styles(self):
        self.assertGreaterEqual(len(self.pages), 12)
        for page in self.pages:
            html = read(page)
            with self.subTest(page=page.name):
                self.assertIn('id="site-header"', html)
                self.assertIn('id="site-footer"', html)
                scripts = re.findall(r'<script type="module" src="([^"]+)"', html)
                self.assertEqual(len(scripts), 1)
                self.assertTrue((STATIC / scripts[0]).exists(), scripts[0])
                for href in re.findall(r'<link rel="stylesheet" href="([^"]+)"', html):
                    self.assertTrue((STATIC / href).exists(), href)

    def test_imports_resolve_and_exports_exist(self):
        pattern = re.compile(r"import\s*\{([^}]*)\}\s*from\s*'(\.[^']+)'")
        for path, source in self.all_js.items():
            for names, target in pattern.findall(source):
                resolved = (path.parent / target).resolve()
                with self.subTest(file=path.name, target=target):
                    self.assertTrue(resolved.exists(), f"{target} not found")
                    exported = read(resolved)
                    for name in [n.strip().split(" as ")[0] for n in names.split(",") if n.strip()]:
                        found = re.search(rf"export\s+(async\s+)?(function|const|class|let)\s+{re.escape(name)}(?![A-Za-z0-9_$])", exported)
                        self.assertTrue(found, f"{name} is not exported by {target}")

    def test_element_ids_used_by_scripts_exist(self):
        everything = "".join(read(p) for p in self.pages) + "".join(self.all_js.values())
        defined = set(re.findall(r"""\bid=\\?["']([A-Za-z0-9_-]+)""", everything))
        for path, source in self.all_js.items():
            for ident in set(re.findall(r"""\$\('#([A-Za-z0-9_-]+)'""", source)):
                with self.subTest(file=path.name, id=ident):
                    self.assertIn(ident, defined)

    def test_page_scripts_only_use_ids_present_in_their_own_page_or_templates(self):
        for page in self.pages:
            html = read(page)
            script = STATIC / re.search(r'src="(js/pages/[^"]+)"', html).group(1)
            source = read(script)
            own_ids = set(re.findall(r"""\bid=\\?["']([A-Za-z0-9_-]+)""", html + source))
            shared = {"site-header", "site-footer", "bell-count", "logout-btn", "menu-btn"}
            for ident in set(re.findall(r"""\$\('#([A-Za-z0-9_-]+)'""", source)):
                with self.subTest(page=page.name, id=ident):
                    self.assertIn(ident, own_ids | shared)

    def test_no_browser_storage_and_evidence_only_in_claim_views(self):
        for path, source in self.all_js.items():
            with self.subTest(file=path.name):
                self.assertNotRegex(source, r"localStorage|sessionStorage|indexedDB|document\.cookie")
        users = {p.name for p, src in self.all_js.items() if "ownership_evidence" in src}
        self.assertEqual(users, {"api.js", "claims-ui.js"})
        for page in self.pages:  # the evidence label is only built by JavaScript from API data, never hard-coded
            self.assertNotIn("ownership_evidence", read(page))

    def test_protected_pages_declare_their_access_rules(self):
        expected = {"dashboard", "claims", "review", "report", "reports", "notifications", "admin", "claim"}
        for name in expected:
            source = read(STATIC / "js" / "pages" / f"{name}.js")
            with self.subTest(page=name):
                self.assertIn("requireAuth: true", source)
        self.assertIn("roles: ['ADMIN']", read(STATIC / "js" / "pages" / "admin.js"))
        for name in ("dashboard", "claims", "review", "report", "reports"):
            self.assertIn("roles: ['STUDENT', 'STAFF']", read(STATIC / "js" / "pages" / f"{name}.js"))

    def test_internal_links_point_to_existing_pages(self):
        sources = [read(p) for p in self.pages] + list(self.all_js.values())
        for source in sources:
            for target in re.findall(r"""(?:href=["']|location\.(?:href|replace)\s*[=(]\s*['"`]|url\(['"])([a-z]+\.html)""", source):
                with self.subTest(target=target):
                    self.assertTrue((STATIC / target).exists(), target)


if __name__ == "__main__":
    unittest.main()

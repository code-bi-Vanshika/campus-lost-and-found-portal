import unittest
from io import BytesIO

from backend.app import create_app
from backend.db import transaction
from backend.routes.items import _read_uploaded_images
from werkzeug.datastructures import FileStorage


class FakeConnection:
    def __init__(self):
        self.started = 0
        self.committed = 0
        self.rolled_back = 0

    def start_transaction(self):
        self.started += 1

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


class BackendSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def test_health_endpoint_is_available(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_mutation_requires_csrf_token(self):
        response = self.client.post(
            "/api/auth/register",
            json={"name": "Student"},
        )
        self.assertEqual(response.status_code, 403)

    def test_registration_validates_before_database_access(self):
        token_response = self.client.get("/api/auth/csrf")
        token = token_response.get_json()["csrf_token"]
        response = self.client.post(
            "/api/auth/register",
            json={"name": "Student", "email": "student@example.edu", "password": "short"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Password", response.get_json()["error"])

    def test_claim_submission_requires_authentication(self):
        token_response = self.client.get("/api/auth/csrf")
        token = token_response.get_json()["csrf_token"]
        response = self.client.post(
            "/api/claims/items/10",
            json={"ownership_evidence": "My description of the item"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 401)

    def test_image_upload_checks_signature_and_size(self):
        png = FileStorage(
            stream=BytesIO(b"\x89PNG\r\n\x1a\nvalid"),
            filename="not-trusted.txt",
        )
        with self.app.app_context():
            images, error = _read_uploaded_images([png])
            self.assertIsNone(error)
            self.assertEqual(images[0][1], "image/png")

            oversized = FileStorage(
                stream=BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024)),
                filename="large.png",
            )
            images, error = _read_uploaded_images([oversized])
            self.assertIsNone(images)
            self.assertIn("2 MB", error)

    def test_transaction_commits_or_rolls_back(self):
        successful = FakeConnection()
        with transaction(successful):
            pass
        self.assertEqual((successful.started, successful.committed, successful.rolled_back), (1, 1, 0))

        failed = FakeConnection()
        with self.assertRaises(RuntimeError):
            with transaction(failed):
                raise RuntimeError("force rollback")
        self.assertEqual((failed.started, failed.committed, failed.rolled_back), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()

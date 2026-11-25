import os
import unittest
import uuid
from io import BytesIO

import mysql.connector

from backend.app import create_app
from test_database import (
    TestDatabaseSafetyError,
    ensure_test_database,
    inspect_test_user_grants,
    verify_connection_database,
)


def test_password():
    password = os.environ.get("TEST_ACCOUNT_PASSWORD")
    if not password:
        raise RuntimeError("TEST_ACCOUNT_PASSWORD must be configured in .env.")
    return password


class CampusLostFoundIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mysql_config = ensure_test_database()
        cls.connection_check = mysql.connector.connect(**cls.mysql_config)
        verify_connection_database(cls.connection_check)
        grant_report = inspect_test_user_grants(cls.connection_check)
        if grant_report["unexpected"]:
            cls.connection_check.close()
            raise TestDatabaseSafetyError(
                "The test user has unexpected privileges outside "
                "campus_lost_found_test."
            )
        cls.connection_check.close()
        cls.app = create_app({
            "TESTING": True,
            "MYSQL_CONFIG": cls.mysql_config,
        })

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.run_tag = "IT_" + uuid.uuid4().hex[:12]
        self.password = test_password()
        self.finder = self._new_account("finder")
        self.claimant = self._new_account("claimant")
        self.other = self._new_account("other")
        self.admin = self._new_account("admin")
        self._set_admin_role(self.admin)

        meta = self.finder["client"].get("/api/items/meta")
        self.assertEqual(meta.status_code, 200)
        metadata = meta.get_json()
        self.category_id = metadata["categories"][0]["category_id"]
        self.location_id = metadata["locations"][0]["location_id"]

    def tearDown(self):
        connection = mysql.connector.connect(**self.mysql_config)
        cursor = connection.cursor()
        try:
            cursor.execute(
                "DELETE h FROM Handover h "
                "JOIN Claims c ON c.claim_id = h.claim_id "
                "JOIN Users u ON u.user_id = c.claimant_id "
                "WHERE u.email LIKE %s",
                (self.run_tag.lower() + "%",),
            )
            cursor.execute(
                "DELETE n FROM Notifications n "
                "JOIN Users u ON u.user_id = n.user_id "
                "WHERE u.email LIKE %s",
                (self.run_tag.lower() + "%",),
            )
            cursor.execute(
                "DELETE c FROM Claims c JOIN Users u ON u.user_id = c.claimant_id "
                "WHERE u.email LIKE %s",
                (self.run_tag.lower() + "%",),
            )
            cursor.execute(
                "DELETE ii FROM Item_Images ii "
                "JOIN Items i ON i.item_id = ii.item_id "
                "JOIN Users u ON u.user_id = i.user_id "
                "WHERE u.email LIKE %s",
                (self.run_tag.lower() + "%",),
            )
            cursor.execute(
                "DELETE i FROM Items i JOIN Users u ON u.user_id = i.user_id "
                "WHERE u.email LIKE %s",
                (self.run_tag.lower() + "%",),
            )
            cursor.execute(
                "DELETE FROM Users WHERE email LIKE %s",
                (self.run_tag.lower() + "%",),
            )
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    def _csrf(self, client):
        response = client.get("/api/auth/csrf")
        self.assertEqual(response.status_code, 200)
        return response.get_json()["csrf_token"]

    def _register(self, client, role_name):
        email = (self.run_tag + "_" + role_name + "@test.local").lower()
        name = self.run_tag + " " + role_name
        response = client.post(
            "/api/auth/register",
            json={"name": name, "email": email, "password": self.password},
            headers={"X-CSRF-Token": self._csrf(client)},
        )
        self.assertEqual(response.status_code, 201)
        return {"email": email, "name": name, "client": client,
                "user_id": response.get_json()["user_id"]}

    def _new_account(self, role_name):
        client = self.app.test_client()
        account = self._register(client, role_name)
        token = self._csrf(client)
        response = client.post(
            "/api/auth/login",
            json={"email": account["email"], "password": self.password},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)
        account["csrf"] = response.get_json()["csrf_token"]
        return account

    def _set_admin_role(self, account):
        connection = mysql.connector.connect(**self.mysql_config)
        cursor = connection.cursor()
        try:
            cursor.execute(
                "UPDATE Users SET role = 'ADMIN' WHERE user_id = %s",
                (account["user_id"],),
            )
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    def _mutation(self, client, method, path, token, **kwargs):
        return client.open(
            path,
            method=method,
            headers={"X-CSRF-Token": token},
            **kwargs,
        )

    def _create_item(self, account, item_type="FOUND", title=None):
        title = title or (self.run_tag + " test item")
        png = b"\x89PNG\r\n\x1a\n" + b"test-image"
        response = account["client"].post(
            "/api/items",
            data={
                "title": title,
                "description": "Integration test item description",
                "category_id": str(self.category_id),
                "location_id": str(self.location_id),
                "item_type": item_type,
                "item_date": "2026-11-21",
                "images": (BytesIO(png), "item.png"),
            },
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": account["csrf"]},
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["item_id"]

    def test_database_is_the_required_test_database(self):
        connection = mysql.connector.connect(**self.mysql_config)
        try:
            verify_connection_database(connection)
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT DATABASE()")
                self.assertEqual(cursor.fetchone()[0], "campus_lost_found_test")
            finally:
                cursor.close()
        finally:
            connection.close()

        with self.assertRaises(TestDatabaseSafetyError):
            from test_database import require_safe_test_database_name
            require_safe_test_database_name("campus_lost_found")

    def test_authentication_csrf_and_role_restrictions(self):
        anonymous = self.app.test_client()
        csrf = self._csrf(anonymous)

        bad_login = anonymous.post(
            "/api/auth/login",
            json={"email": self.finder["email"], "password": "definitely-wrong"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(bad_login.status_code, 401)

        no_csrf = anonymous.post("/api/auth/logout")
        self.assertEqual(no_csrf.status_code, 403)

        me = anonymous.get("/api/auth/me")
        self.assertEqual(me.status_code, 401)

        dashboard = self.claimant["client"].get("/api/admin/dashboard")
        self.assertEqual(dashboard.status_code, 403)

        wrong_role_create = self._mutation(
            self.admin["client"], "POST", "/api/items",
            self.admin["csrf"], data={},
        )
        self.assertEqual(wrong_role_create.status_code, 403)

    def test_item_lifecycle_search_edit_close_and_invalid_requests(self):
        found_id = self._create_item(self.finder)
        lost_id = self._create_item(self.claimant, "LOST")

        search = self.app.test_client().get(
            "/api/items",
            query_string={"q": self.run_tag, "item_type": "FOUND", "status": "ACTIVE"},
        )
        self.assertEqual(search.status_code, 200)
        ids = [item["item_id"] for item in search.get_json()["items"]]
        self.assertIn(found_id, ids)
        self.assertNotIn(lost_id, ids)

        invalid = self.app.test_client().get(
            "/api/items",
            query_string={"category_id": "-1"},
        )
        self.assertEqual(invalid.status_code, 400)

        edit = self._mutation(
            self.finder["client"], "PATCH",
            "/api/items/" + str(found_id),
            self.finder["csrf"], json={"title": self.run_tag + " edited"},
        )
        self.assertEqual(edit.status_code, 200)

        forbidden_edit = self._mutation(
            self.claimant["client"], "PATCH",
            "/api/items/" + str(found_id),
            self.claimant["csrf"], json={"title": "Unauthorized"},
        )
        self.assertEqual(forbidden_edit.status_code, 403)

        close = self._mutation(
            self.finder["client"], "POST",
            "/api/items/" + str(found_id) + "/close",
            self.finder["csrf"], json={},
        )
        self.assertEqual(close.status_code, 200)

        close_again = self._mutation(
            self.finder["client"], "POST",
            "/api/items/" + str(found_id) + "/close",
            self.finder["csrf"], json={},
        )
        self.assertEqual(close_again.status_code, 409)

    def test_claim_finder_admin_handover_and_notifications(self):
        item_id = self._create_item(self.finder)

        submit = self._mutation(
            self.claimant["client"], "POST",
            "/api/claims/items/" + str(item_id),
            self.claimant["csrf"],
            json={"ownership_evidence": "Test-only ownership evidence."},
        )
        self.assertEqual(submit.status_code, 201)
        claim_id = submit.get_json()["claim_id"]

        duplicate = self._mutation(
            self.claimant["client"], "POST",
            "/api/claims/items/" + str(item_id),
            self.claimant["csrf"],
            json={"ownership_evidence": "Duplicate evidence."},
        )
        self.assertEqual(duplicate.status_code, 409)

        unauthorized_detail = self.other["client"].get(
            "/api/claims/" + str(claim_id)
        )
        self.assertEqual(unauthorized_detail.status_code, 403)

        approve_by_finder = self._mutation(
            self.finder["client"], "POST",
            "/api/claims/" + str(claim_id) + "/finder-decision",
            self.finder["csrf"],
            json={"decision": "APPROVED", "remarks": "Identity appears consistent."},
        )
        self.assertEqual(approve_by_finder.status_code, 200)

        queue = self.admin["client"].get("/api/claims/review-queue")
        self.assertEqual(queue.status_code, 200)
        queued_ids = [claim["claim_id"] for claim in queue.get_json()["claims"]]
        self.assertIn(claim_id, queued_ids)

        admin_approve = self._mutation(
            self.admin["client"], "POST",
            "/api/claims/" + str(claim_id) + "/admin-decision",
            self.admin["csrf"],
            json={"decision": "APPROVED", "remarks": "Final review complete."},
        )
        self.assertEqual(admin_approve.status_code, 200)

        handover = self._mutation(
            self.admin["client"], "POST",
            "/api/claims/" + str(claim_id) + "/handover",
            self.admin["csrf"],
            json={"remarks": "Test handover."},
        )
        self.assertEqual(handover.status_code, 201)

        handover_detail = self.claimant["client"].get(
            "/api/claims/" + str(claim_id) + "/handover"
        )
        self.assertEqual(handover_detail.status_code, 200)

        repeat_handover = self._mutation(
            self.admin["client"], "POST",
            "/api/claims/" + str(claim_id) + "/handover",
            self.admin["csrf"], json={},
        )
        self.assertEqual(repeat_handover.status_code, 409)

        notifications = self.claimant["client"].get("/api/notifications")
        self.assertEqual(notifications.status_code, 200)
        rows = notifications.get_json()["notifications"]
        self.assertTrue(rows)
        unread = [row for row in rows if not row["is_read"]]
        self.assertTrue(unread)

        mark_read = self._mutation(
            self.claimant["client"], "POST",
            "/api/notifications/" + str(unread[0]["notification_id"]) + "/read",
            self.claimant["csrf"], json={},
        )
        self.assertEqual(mark_read.status_code, 200)

        item = self.app.test_client().get("/api/items/" + str(item_id))
        self.assertEqual(item.status_code, 200)
        self.assertEqual(item.get_json()["item"]["status"], "RETURNED")

    def test_finder_rejection_and_admin_rejection(self):
        item_id = self._create_item(self.finder)
        submit = self._mutation(
            self.claimant["client"], "POST",
            "/api/claims/items/" + str(item_id),
            self.claimant["csrf"],
            json={"ownership_evidence": "Test-only evidence."},
        )
        claim_id = submit.get_json()["claim_id"]

        missing_reason = self._mutation(
            self.finder["client"], "POST",
            "/api/claims/" + str(claim_id) + "/finder-decision",
            self.finder["csrf"], json={"decision": "REJECTED"},
        )
        self.assertEqual(missing_reason.status_code, 400)

        rejection = self._mutation(
            self.finder["client"], "POST",
            "/api/claims/" + str(claim_id) + "/finder-decision",
            self.finder["csrf"],
            json={"decision": "REJECTED", "remarks": "Test rejection."},
        )
        self.assertEqual(rejection.status_code, 200)

        item_id_2 = self._create_item(self.finder)
        submit_2 = self._mutation(
            self.claimant["client"], "POST",
            "/api/claims/items/" + str(item_id_2),
            self.claimant["csrf"],
            json={"ownership_evidence": "Second test-only evidence."},
        )
        claim_id_2 = submit_2.get_json()["claim_id"]
        finder_approve = self._mutation(
            self.finder["client"], "POST",
            "/api/claims/" + str(claim_id_2) + "/finder-decision",
            self.finder["csrf"], json={"decision": "APPROVED"},
        )
        self.assertEqual(finder_approve.status_code, 200)
        admin_reject = self._mutation(
            self.admin["client"], "POST",
            "/api/claims/" + str(claim_id_2) + "/admin-decision",
            self.admin["csrf"],
            json={"decision": "REJECTED", "remarks": "Test admin rejection."},
        )
        self.assertEqual(admin_reject.status_code, 200)

        mine = self.claimant["client"].get("/api/claims/mine")
        self.assertEqual(mine.status_code, 200)
        statuses = {claim["claim_id"]: claim["status"] for claim in mine.get_json()["claims"]}
        self.assertEqual(statuses[claim_id], "REJECTED")
        self.assertEqual(statuses[claim_id_2], "REJECTED")

    def test_admin_can_cancel_approval_before_handover(self):
        item_id = self._create_item(self.finder)
        submit = self._mutation(
            self.claimant["client"], "POST",
            "/api/claims/items/" + str(item_id),
            self.claimant["csrf"],
            json={"ownership_evidence": "Cancellation test evidence."},
        )
        claim_id = submit.get_json()["claim_id"]

        self._mutation(
            self.finder["client"], "POST",
            "/api/claims/" + str(claim_id) + "/finder-decision",
            self.finder["csrf"], json={"decision": "APPROVED"},
        )
        self._mutation(
            self.admin["client"], "POST",
            "/api/claims/" + str(claim_id) + "/admin-decision",
            self.admin["csrf"], json={"decision": "APPROVED"},
        )
        cancel = self._mutation(
            self.admin["client"], "POST",
            "/api/claims/" + str(claim_id) + "/cancel-approval",
            self.admin["csrf"], json={"reason": "Test cancellation."},
        )
        self.assertEqual(cancel.status_code, 200)

        item = self.app.test_client().get("/api/items/" + str(item_id))
        self.assertEqual(item.status_code, 200)
        self.assertEqual(item.get_json()["item"]["status"], "ACTIVE")


if __name__ == "__main__":
    unittest.main(verbosity=2)

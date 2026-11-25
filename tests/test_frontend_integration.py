"""Integration tests for the call sequences the browser frontend makes (backend/static/js/api.js).

They use the same isolated MySQL test database and safety checks as test_backend_integration.py, and
are run together with it by tests/run_local_integration_tests.py.

Focus: the CSRF/session flow, multipart image upload and retrieval, privacy of ownership evidence,
role/permission rules, and the finder -> admin -> handover workflow including competing claims.
"""
import json
import unittest
import uuid
from io import BytesIO

import mysql.connector

from backend.app import create_app
from test_backend_integration import test_password
from test_database import (
    TestDatabaseSafetyError,
    ensure_test_database,
    inspect_test_user_grants,
    verify_connection_database,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"png-test-data"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-test-data"
SECRET_1 = "SECRET-EVIDENCE-ONE the scratch under the battery cover"
SECRET_2 = "SECRET-EVIDENCE-TWO sticker with a red dragon"


class FrontendIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mysql_config = ensure_test_database()
        check = mysql.connector.connect(**cls.mysql_config)
        verify_connection_database(check)
        report = inspect_test_user_grants(check)
        check.close()
        if report["unexpected"]:
            raise TestDatabaseSafetyError("The test user has unexpected privileges outside campus_lost_found_test.")
        cls.app = create_app({"TESTING": True, "MYSQL_CONFIG": cls.mysql_config})

    def setUp(self):
        self.run_tag = "FE_" + uuid.uuid4().hex[:12]
        self.password = test_password()
        self.finder = self._account("finder")
        self.claimant = self._account("claimant")
        self.claimant2 = self._account("claimant2")
        self.other = self._account("other")
        self.admin = self._account("admin")
        self._run_sql("UPDATE Users SET role = 'ADMIN' WHERE user_id = %s", (self.admin["user_id"],))
        meta = self.finder["client"].get("/api/items/meta").get_json()
        self.category_id = meta["categories"][0]["category_id"]
        self.location_id = meta["locations"][0]["location_id"]

    def tearDown(self):
        like = (self.run_tag.lower() + "%",)
        users = "(SELECT user_id FROM Users WHERE email LIKE %s)"
        for sql in (
            "DELETE FROM Handover WHERE claim_id IN (SELECT claim_id FROM Claims WHERE claimant_id IN " + users + ")",
            "DELETE FROM Notifications WHERE user_id IN " + users,
            "DELETE FROM Claims WHERE claimant_id IN " + users,
            "DELETE FROM Item_Images WHERE item_id IN (SELECT item_id FROM Items WHERE user_id IN " + users + ")",
            "DELETE FROM Items WHERE user_id IN " + users,
            "DELETE FROM Users WHERE email LIKE %s",
        ):
            self._run_sql(sql, like)

    # ---- helpers -------------------------------------------------------
    def _run_sql(self, sql, params=()):
        connection = mysql.connector.connect(**self.mysql_config)
        cursor = connection.cursor()
        try:
            cursor.execute(sql, params)
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    def _csrf(self, client):
        response = client.get("/api/auth/csrf")
        self.assertEqual(response.status_code, 200)
        return response.get_json()["csrf_token"]

    def _account(self, name):
        client = self.app.test_client()
        email = (self.run_tag + "_" + name + "@test.local").lower()
        registered = client.post("/api/auth/register", json={"name": self.run_tag + " " + name, "email": email,
                                 "password": self.password}, headers={"X-CSRF-Token": self._csrf(client)})
        self.assertEqual(registered.status_code, 201)
        login = client.post("/api/auth/login", json={"email": email, "password": self.password},
                            headers={"X-CSRF-Token": self._csrf(client)})
        self.assertEqual(login.status_code, 200)
        return {"client": client, "email": email, "user_id": registered.get_json()["user_id"],
                "csrf": login.get_json()["csrf_token"]}

    def _post(self, account, path, body=None, method="POST"):
        return account["client"].open(path, method=method, json={} if body is None else body,
                                      headers={"X-CSRF-Token": account["csrf"]})

    def _report(self, account, item_type="FOUND", images=None, title=None):
        data = {"title": title or self.run_tag + " item", "description": "Frontend integration item",
                "category_id": str(self.category_id), "location_id": str(self.location_id),
                "item_type": item_type, "item_date": "2026-11-21"}
        if images:
            data["images"] = [(BytesIO(blob), name) for blob, name in images]
        response = account["client"].post("/api/items", data=data, content_type="multipart/form-data",
                                          headers={"X-CSRF-Token": account["csrf"]})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["item_id"]

    def _claim(self, account, item_id, evidence):
        response = self._post(account, f"/api/claims/items/{item_id}", {"ownership_evidence": evidence})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["claim_id"]

    def _item_status(self, item_id):
        return self.app.test_client().get(f"/api/items/{item_id}").get_json()["item"]["status"]

    # ---- tests ---------------------------------------------------------
    def test_session_and_csrf_flow_used_by_the_api_client(self):
        client = self.app.test_client()
        self.assertEqual(client.get("/api/auth/me").status_code, 401)
        self.assertEqual(client.post("/api/auth/login", json={}).status_code, 403)  # no token at all
        token = self._csrf(client)
        bad = client.post("/api/auth/login", json={"email": self.finder["email"], "password": "wrong-password-123"},
                          headers={"X-CSRF-Token": token})
        self.assertEqual(bad.status_code, 401)
        good = client.post("/api/auth/login", json={"email": self.finder["email"], "password": self.password},
                           headers={"X-CSRF-Token": token})
        self.assertEqual(good.status_code, 200)
        rotated = good.get_json()["csrf_token"]
        self.assertNotEqual(rotated, token)  # login rotates the token, so the client must adopt the new one
        self.assertEqual(client.post("/api/auth/logout", headers={"X-CSRF-Token": token}).status_code, 403)
        me = client.get("/api/auth/me").get_json()["user"]
        self.assertEqual(me["email"], self.finder["email"])
        self.assertNotIn("password_hash", json.dumps(me))
        self.assertEqual(client.post("/api/auth/logout", headers={"X-CSRF-Token": rotated}).status_code, 200)
        self.assertEqual(client.get("/api/auth/me").status_code, 401)
        # a stale token fetched earlier is replaced when /csrf is called again
        first = self._csrf(client)
        second = self._csrf(client)
        self.assertNotEqual(first, second)
        self.assertEqual(client.post("/api/auth/logout", headers={"X-CSRF-Token": first}).status_code, 403)

    def test_multipart_upload_and_public_image_retrieval(self):
        item_id = self._report(self.finder, images=[(PNG, "a.png"), (JPEG, "b.jpg")])
        anonymous = self.app.test_client()
        item = anonymous.get(f"/api/items/{item_id}").get_json()["item"]
        self.assertEqual(len(item["images"]), 2)
        for image in item["images"]:
            response = anonymous.get(image["url"])
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.mimetype, ("image/png", "image/jpeg"))
            self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(anonymous.get(f"/api/items/{item_id}/images/999999999").status_code, 404)

        def rejected(blob, name):
            response = self.finder["client"].post(
                "/api/items", content_type="multipart/form-data", headers={"X-CSRF-Token": self.finder["csrf"]},
                data={"title": "x", "description": "x", "category_id": str(self.category_id),
                      "location_id": str(self.location_id), "item_type": "FOUND", "item_date": "2026-11-21",
                      "images": (BytesIO(blob), name)})
            return response.status_code
        self.assertEqual(rejected(b"this is plain text", "notes.png"), 400)          # wrong signature
        self.assertEqual(rejected(PNG + b"0" * (2 * 1024 * 1024), "big.png"), 400)   # larger than 2 MB

    def test_public_endpoints_never_expose_ownership_evidence_or_reporter_details(self):
        item_id = self._report(self.finder, images=[(PNG, "a.png")])
        claim_id = self._claim(self.claimant, item_id, SECRET_1)
        anonymous = self.app.test_client()
        public = [anonymous.get(path) for path in (
            "/api/items", f"/api/items?q={self.run_tag}", f"/api/items/{item_id}", "/api/items/meta")]
        for response in public:
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertNotIn("SECRET-EVIDENCE", body)
            self.assertNotIn("ownership_evidence", body)
            self.assertNotIn(self.finder["email"], body)
        item = public[2].get_json()["item"]
        for private_key in ("user_id", "email", "phone", "password_hash"):
            self.assertNotIn(private_key, item)
        # anonymous: every claim endpoint needs a login
        for path in (f"/api/claims/{claim_id}", f"/api/claims/items/{item_id}", "/api/claims/mine",
                     f"/api/claims/{claim_id}/handover", "/api/notifications"):
            self.assertEqual(anonymous.get(path).status_code, 401, path)
        # logged-in strangers cannot read someone else's claim, claim list or handover
        for path in (f"/api/claims/{claim_id}", f"/api/claims/items/{item_id}", f"/api/claims/{claim_id}/handover"):
            self.assertIn(self.other["client"].get(path).status_code, (403, 404), path)
            self.assertIn(self.claimant2["client"].get(path).status_code, (403, 404), path)
        # authorised parties do see it
        for account in (self.claimant, self.finder, self.admin):
            response = account["client"].get(f"/api/claims/{claim_id}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["claim"]["ownership_evidence"], SECRET_1)
        # another claimant's own list never contains this evidence
        mine = self.claimant2["client"].get("/api/claims/mine").get_data(as_text=True)
        self.assertNotIn("SECRET-EVIDENCE", mine)

    def test_role_and_ownership_rules_the_ui_depends_on(self):
        found_id = self._report(self.finder)
        lost_id = self._report(self.other, "LOST")
        self.assertEqual(self.admin["client"].post("/api/items", data={}, headers={"X-CSRF-Token": self.admin["csrf"]}).status_code, 403)
        self.assertEqual(self.claimant["client"].get("/api/admin/dashboard").status_code, 403)
        self.assertEqual(self.claimant["client"].get("/api/claims/review-queue").status_code, 403)
        self.assertEqual(self._post(self.finder, f"/api/claims/items/{found_id}", {"ownership_evidence": "mine"}).status_code, 403)
        self.assertEqual(self._post(self.claimant, f"/api/claims/items/{lost_id}", {"ownership_evidence": "x"}).status_code, 409)
        self.assertEqual(self._post(self.claimant, f"/api/claims/items/{found_id}", {"ownership_evidence": "  "}).status_code, 400)
        # the owner probe the item page uses: owner and admin get 200, other users 403
        self.assertEqual(self.finder["client"].get(f"/api/claims/items/{found_id}").status_code, 200)
        self.assertEqual(self.admin["client"].get(f"/api/claims/items/{found_id}").status_code, 200)
        self.assertEqual(self.claimant["client"].get(f"/api/claims/items/{found_id}").status_code, 403)
        claim_id = self._claim(self.claimant, found_id, SECRET_1)
        self.assertEqual(self._post(self.claimant, f"/api/claims/items/{found_id}", {"ownership_evidence": "again"}).status_code, 409)
        for account, path in ((self.claimant, "finder-decision"), (self.other, "finder-decision"), (self.finder, "admin-decision")):
            response = self._post(account, f"/api/claims/{claim_id}/{path}", {"decision": "APPROVED"})
            self.assertIn(response.status_code, (403, 409), (path, response.status_code))
        self.assertEqual(self._post(self.finder, f"/api/claims/{claim_id}/finder-decision", {"decision": "REJECTED"}).status_code, 400)  # reason required
        self.assertEqual(self._post(self.admin, f"/api/claims/{claim_id}/admin-decision", {"decision": "APPROVED"}).status_code, 409)  # finder first

    def test_finder_admin_handover_workflow_with_competing_claims(self):
        item_id = self._report(self.finder)
        first = self._claim(self.claimant, item_id, SECRET_1)
        second = self._claim(self.claimant2, item_id, SECRET_2)
        third = self._claim(self.other, item_id, "third claimant evidence")
        self.assertEqual(self._item_status(item_id), "CLAIM_PENDING")
        self.assertEqual(len(self.finder["client"].get(f"/api/claims/items/{item_id}").get_json()["claims"]), 3)

        for claim_id in (first, second):
            self.assertEqual(self._post(self.finder, f"/api/claims/{claim_id}/finder-decision",
                                        {"decision": "APPROVED", "remarks": "matches"}).status_code, 200)
        queue = self.admin["client"].get("/api/claims/review-queue").get_json()["claims"]
        queued = {c["claim_id"] for c in queue}
        self.assertTrue({first, second} <= queued and third not in queued)
        self.assertIn("item_title", queue[0])

        self.assertEqual(self._post(self.admin, f"/api/claims/{first}/admin-decision", {"decision": "APPROVED"}).status_code, 200)
        self.assertEqual(self._item_status(item_id), "CLAIMED")
        # a second approval on the same item must be refused while the first stands
        self.assertEqual(self._post(self.admin, f"/api/claims/{second}/admin-decision", {"decision": "APPROVED"}).status_code, 409)
        # approval can be cancelled (reason required) and the item reopens for the other claim
        self.assertEqual(self._post(self.admin, f"/api/claims/{first}/cancel-approval", {}).status_code, 400)
        self.assertEqual(self._post(self.admin, f"/api/claims/{first}/cancel-approval", {"reason": "no show"}).status_code, 200)
        self.assertEqual(self._item_status(item_id), "CLAIM_PENDING")
        cancelled = self.claimant["client"].get(f"/api/claims/{first}").get_json()["claim"]
        self.assertEqual((cancelled["status"], cancelled["admin_decision"]), ("REJECTED", "REJECTED"))
        self.assertIn("no show", cancelled["admin_remarks"])

        self.assertEqual(self._post(self.admin, f"/api/claims/{second}/admin-decision", {"decision": "APPROVED"}).status_code, 200)
        self.assertEqual(self.claimant2["client"].get(f"/api/claims/{second}/handover").status_code, 404)  # none yet
        done = self._post(self.admin, f"/api/claims/{second}/handover", {"remarks": "ID checked"})
        self.assertEqual(done.status_code, 201, done.get_data(as_text=True))
        self.assertEqual(self._item_status(item_id), "RETURNED")
        self.assertEqual(self._post(self.admin, f"/api/claims/{second}/handover", {}).status_code, 409)
        self.assertEqual(self._post(self.admin, f"/api/claims/{second}/cancel-approval", {"reason": "late"}).status_code, 409)

        recorded = self.claimant2["client"].get(f"/api/claims/{second}/handover").get_json()["handover"]
        self.assertEqual(recorded["remarks"], "ID checked")
        self.assertEqual(self.finder["client"].get(f"/api/claims/{second}/handover").status_code, 200)
        self.assertEqual(self.other["client"].get(f"/api/claims/{second}/handover").status_code, 403)
        left_over = self.other["client"].get(f"/api/claims/{third}").get_json()["claim"]
        self.assertEqual(left_over["status"], "REJECTED")  # pending claims are closed at handover

    def test_notifications_reach_every_party_and_can_be_marked_read(self):
        item_id = self._report(self.finder)
        claim_id = self._claim(self.claimant, item_id, SECRET_1)
        inbox = self.finder["client"].get("/api/notifications").get_json()
        self.assertGreaterEqual(inbox["unread_count"], 1)
        mine = [n for n in inbox["notifications"] if n["claim_id"] == claim_id]
        self.assertTrue(mine)  # the finder inbox in review.html discovers claims through this field
        self.assertEqual(self._post(self.finder, f"/api/notifications/{mine[0]['notification_id']}/read").status_code, 200)
        after = self.finder["client"].get("/api/notifications", query_string={"per_page": 1}).get_json()
        self.assertEqual(after["unread_count"], inbox["unread_count"] - 1)
        # nobody can mark someone else's notification
        self.assertEqual(self._post(self.other, f"/api/notifications/{mine[0]['notification_id']}/read").status_code, 404)
        self._post(self.finder, f"/api/claims/{claim_id}/finder-decision", {"decision": "APPROVED"})
        self.assertGreaterEqual(self.claimant["client"].get("/api/notifications").get_json()["unread_count"], 1)
        self.assertGreaterEqual(len(self.admin["client"].get("/api/admin/dashboard").get_json()), 3)


    def test_my_items_lists_only_the_users_own_reports(self):
        found_id = self._report(self.finder, title=self.run_tag + " found one")
        lost_id = self._report(self.finder, "LOST", title=self.run_tag + " lost one")
        foreign_id = self._report(self.other)
        self._claim(self.claimant, found_id, SECRET_1)
        response = self.finder["client"].get("/api/items/mine")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        items = response.get_json()["items"]
        self.assertEqual([i["item_id"] for i in items], [lost_id, found_id])  # newest first, nobody else's
        by_id = {i["item_id"]: i for i in items}
        self.assertEqual((by_id[found_id]["claim_count"], by_id[found_id]["claims_awaiting_review"]), (1, 1))
        self.assertEqual((by_id[lost_id]["claim_count"], by_id[lost_id]["claims_awaiting_review"]), (0, 0))
        self.assertNotIn("SECRET-EVIDENCE", body)
        for private_key in ("user_id", "email", "phone"):
            self.assertNotIn(private_key, items[0])
        page_two = self.finder["client"].get("/api/items/mine", query_string={"per_page": 1, "page": 2}).get_json()["items"]
        self.assertEqual([i["item_id"] for i in page_two], [found_id])
        self.assertEqual(self.finder["client"].get("/api/items/mine?page=abc").status_code, 400)
        self.assertNotIn(found_id, [i["item_id"] for i in self.claimant["client"].get("/api/items/mine").get_json()["items"]])
        self.assertIn(foreign_id, [i["item_id"] for i in self.other["client"].get("/api/items/mine").get_json()["items"]])
        self.assertEqual(self.app.test_client().get("/api/items/mine").status_code, 401)
        self.assertEqual(self.admin["client"].get("/api/items/mine").status_code, 403)

    def test_finder_queue_lists_claims_on_the_finders_items(self):
        item_id = self._report(self.finder)
        foreign_item = self._report(self.other)
        first = self._claim(self.claimant, item_id, SECRET_1)
        second = self._claim(self.claimant2, item_id, SECRET_2)
        foreign_claim = self._claim(self.claimant, foreign_item, "evidence for someone else's item")
        queue = self.finder["client"].get("/api/claims/finder-queue").get_json()["claims"]
        self.assertEqual({c["claim_id"] for c in queue}, {first, second})
        self.assertNotIn(foreign_claim, [c["claim_id"] for c in queue])
        self.assertEqual(queue[0]["item_title"], self.run_tag + " item")
        self.assertIn(queue[0]["ownership_evidence"], (SECRET_1, SECRET_2))  # the finder may see it
        self.assertEqual(self._post(self.finder, f"/api/claims/{first}/finder-decision", {"decision": "APPROVED"}).status_code, 200)
        pending = self.finder["client"].get("/api/claims/finder-queue?state=pending").get_json()["claims"]
        self.assertEqual([c["claim_id"] for c in pending], [second])
        everything = self.finder["client"].get("/api/claims/finder-queue").get_json()["claims"]
        self.assertEqual(everything[0]["claim_id"], second)  # awaiting claims are listed first
        self.assertEqual({c["claim_id"] for c in everything}, {first, second})
        self.assertEqual([c["claim_id"] for c in self.other["client"].get("/api/claims/finder-queue").get_json()["claims"]], [foreign_claim])
        self.assertEqual(self.claimant["client"].get("/api/claims/finder-queue?state=pending").get_json()["claims"], [])
        self.assertEqual(self.finder["client"].get("/api/claims/finder-queue?state=bogus").status_code, 400)
        self.assertEqual(self.app.test_client().get("/api/claims/finder-queue").status_code, 401)
        self.assertEqual(self.admin["client"].get("/api/claims/finder-queue").status_code, 403)

    def test_handover_queue_lists_approved_claims_for_admins_only(self):
        item_id = self._report(self.finder)
        claim_id = self._claim(self.claimant, item_id, SECRET_1)
        self._post(self.finder, f"/api/claims/{claim_id}/finder-decision", {"decision": "APPROVED"})
        ids = lambda state: [c["claim_id"] for c in self.admin["client"].get(f"/api/claims/handover-queue?state={state}&per_page=50").get_json()["claims"]]
        self.assertNotIn(claim_id, ids("pending"))  # finder-approved only: admin has not approved yet
        self._post(self.admin, f"/api/claims/{claim_id}/admin-decision", {"decision": "APPROVED"})
        self.assertIn(claim_id, ids("pending"))
        self.assertNotIn(claim_id, ids("completed"))
        row = [c for c in self.admin["client"].get("/api/claims/handover-queue").get_json()["claims"] if c["claim_id"] == claim_id][0]
        self.assertEqual((row["item_title"], row["item_status"], row["handover"]), (self.run_tag + " item", "CLAIMED", None))
        for account in (self.finder, self.claimant, self.other):
            self.assertEqual(account["client"].get("/api/claims/handover-queue").status_code, 403)
        self.assertEqual(self.app.test_client().get("/api/claims/handover-queue").status_code, 401)
        self.assertEqual(self.admin["client"].get("/api/claims/handover-queue?state=bogus").status_code, 400)
        self.assertEqual(self._post(self.admin, f"/api/claims/{claim_id}/handover", {"remarks": "ID checked"}).status_code, 201)
        self.assertNotIn(claim_id, ids("pending"))
        self.assertIn(claim_id, ids("completed"))
        self.assertIn(claim_id, ids("all"))
        done = [c for c in self.admin["client"].get("/api/claims/handover-queue?state=completed&per_page=50").get_json()["claims"] if c["claim_id"] == claim_id][0]
        self.assertEqual(done["handover"]["remarks"], "ID checked")


if __name__ == "__main__":
    unittest.main()

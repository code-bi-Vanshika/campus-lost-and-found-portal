# Campus Lost & Found backend

The backend is a Flask JSON API using the existing `campus_lost_found` MySQL
schema. It does not create, drop, or migrate database objects. Confirm that the
live database matches `schema.sql` before connecting; do not execute that
development script against a database containing data because it drops the
database first.

## Local setup

1. Install the packages from the project root:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`, set a private `FLASK_SECRET_KEY` and the
   credentials for the existing MySQL database. `COOKIE_SECURE=false` is only
   appropriate for local HTTP development; set it to `true` when served over
   HTTPS.
3. Run from the project root:

   ```powershell
   python -m backend.app
   ```

Public registration creates STUDENT accounts. STAFF and ADMIN roles must be
assigned through a trusted administrative process in MySQL Workbench; the
registration API ignores client-supplied roles.

## API outline

All endpoints are under `/api`. Obtain a CSRF token from `GET /auth/csrf`
before sending a POST, PATCH, PUT, or DELETE request. Send it in the
`X-CSRF-Token` header and retain the session cookie. Login returns a fresh
token; logout clears the session.

| Area | Routes |
| --- | --- |
| Authentication | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Items | `GET /items`, `GET /items/meta`, `GET /items/{id}`, `GET /items/mine`, `POST /items`, `PATCH /items/{id}`, `POST /items/{id}/close` |
| Item images | `GET /items/{id}/images/{image_id}` |
| Claims | `POST /claims/items/{item_id}`, `GET /claims/mine`, `GET /claims/items/{item_id}`, `GET /claims/review-queue`, `GET /claims/finder-queue`, `GET /claims/handover-queue`, `GET /claims/{id}` |
| Claim decisions | `POST /claims/{id}/finder-decision`, `POST /claims/{id}/admin-decision`, `POST /claims/{id}/cancel-approval` |
| Handover | `POST /claims/{id}/handover`, `GET /claims/{id}/handover` |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read` |
| Administration | `GET /admin/dashboard` |

## User and claim queues

The following read-only endpoints use the existing session cookie and return paginated JSON
(`page` defaults to 1; `per_page` defaults to 20 and is capped at 50):

| Route | Access | Query parameters and response |
| --- | --- | --- |
| `GET /api/items/mine` | STUDENT, STAFF | Optional `page`, `per_page`; returns `{ "items": [...], "page": n, "per_page": n }`. Each item is one reported by the current user and includes `claim_count` and `claims_awaiting_review`. |
| `GET /api/claims/finder-queue` | STUDENT, STAFF | Optional `state=all\|pending` (default `all`), `page`, `per_page`; returns `{ "claims": [...], "page": n, "per_page": n }`. Lists claims on the current user's reports, with claims awaiting a finder decision first. |
| `GET /api/claims/handover-queue` | ADMIN | Optional `state=pending\|completed\|all` (default `pending`), `page`, `per_page`; returns `{ "claims": [...], "page": n, "per_page": n }`. Lists admin-approved claims and includes handover details when recorded. |

`/items/mine` does not return claimant evidence or other users' contact details. Claim evidence
is returned only in claim views authorized for the claimant, the reporting finder, or an admin;
the finder queue is scoped to the logged-in finder's own reports and the handover queue is
admin-only. GET requests do not require a CSRF token; all state-changing requests remain
protected by the application's global CSRF check.

Item reports use `multipart/form-data` with `title`, `description`,
`category_id`, `location_id`, `item_type` (`LOST` or `FOUND`), `item_date`
(`YYYY-MM-DD`), and optional repeated `images` fields. Each image is
signature-checked and limited to 2 MiB; image data is stored in `Item_Images`.
The whole request is limited to 16 MiB.

Claims expose ownership evidence only to the claimant, the reporting finder,
and administrators. Finder-approved claims are reviewed by administrators.
Cancelling an approval before handover is represented as an administrator
rejection with the cancellation reason in `admin_remarks`, keeping the existing
claim status enum and database structure unchanged. Claim decisions and
handover use item-row locks and transactions to serialize competing actions.

## Test safety

Integration tests run only against `campus_lost_found_test` using the separate
`TEST_MYSQL_USER` and `TEST_MYSQL_PASSWORD` settings. Run them with
`python tests/run_local_integration_tests.py` after configuring those credentials
and `TEST_ACCOUNT_PASSWORD` for test accounts. The test runner verifies the selected
database and account grants before it runs; do not use the production database or
the database bootstrap script as part of routine test execution.

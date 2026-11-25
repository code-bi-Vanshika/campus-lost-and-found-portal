# Campus Lost & Found - frontend (HTML5 / CSS3 / vanilla JavaScript)

Served by Flask's default static folder (`backend/static/`). The frontend uses the Flask JSON API,
including the owner and claim-queue endpoints documented below. No database schema change or
JavaScript dependency is required. No build step.

## Run locally
1. Create the MySQL database and tables (`schema.sql`, then `seed.sql`) and fill in `.env`
   (see `.env.example`; for plain http on localhost keep `COOKIE_SECURE=false`).
2. `pip install -r requirements.txt`
3. Make an admin: register normally in the portal, then in MySQL Workbench run
   `UPDATE Users SET role = 'ADMIN' WHERE email = 'you@example.edu';` (staff: `role = 'STAFF'`).
4. Start the server from the project root: `python -m backend.app`
5. Open **http://127.0.0.1:5000/static/index.html**. Always use the Flask address, not the file on disk,
   so the session cookie and CSRF token work. (`/` has no page: the backend defines no root route.)

## Pages
index, login, register, items (browse/search/filter), item (details, claim form, finder/admin claim list),
report (lost/found + edit), dashboard, reports (my reports), claims (my claims), review (finder inbox), claim (details),
notifications, admin. Shared code: js/api.js (session + `X-CSRF-Token`), auth.js, layout.js, ui.js,
claims-ui.js, item-cards.js, css/styles.css.

## Tests
```
python -m unittest tests.test_frontend_static -v     # no database: URL/method/field contract, imports, ids, links, access rules
python -m unittest tests.test_backend_security -v    # existing, no database
python tests/run_local_integration_tests.py          # backend + frontend integration tests; test DB only
```
The integration runner requires a separately configured `campus_lost_found_test` database account
(`TEST_MYSQL_USER`, `TEST_MYSQL_PASSWORD`) and `TEST_ACCOUNT_PASSWORD`. It verifies the selected
database and grants before running; do not point it at `campus_lost_found`.
`tests/test_frontend_integration.py` covers the call sequences the browser makes: CSRF/login rotation,
multipart image upload and retrieval, privacy of ownership evidence, role rules, competing claims, approval
cancel, handover, notifications and the three new queue endpoints. The runner executes it together with the existing integration tests.

## Privacy rules enforced
- Ownership evidence is returned only by claim endpoints, to the claimant, the item's finder and admins.
  Public item endpoints never contain it or the reporter's identity.
- The frontend keeps no application data in localStorage/sessionStorage/cookies (a test enforces this).
- User text is HTML-escaped before display; `next=` redirects accept only pages inside this site.

## Backend additions (read-only, no schema change, same auth/role/CSRF rules)
| Route | Who | Purpose |
|---|---|---|
| `GET /api/items/mine?page=&per_page=` | STUDENT, STAFF | Returns `{items, page, per_page}` for the signed-in user's reports; item rows include `claim_count` and `claims_awaiting_review` but no claim evidence or other users' contact details. `per_page` is capped at 50. |
| `GET /api/claims/finder-queue?state=all\|pending&page=&per_page=` | STUDENT, STAFF | Returns `{claims, page, per_page}` for claims on the signed-in user's reports, with awaiting decisions first. The finder can see the ownership evidence needed to review those claims. |
| `GET /api/claims/handover-queue?state=pending\|completed\|all&page=&per_page=` | ADMIN | Returns `{claims, page, per_page}` for admin-approved claims; includes handover details when completed. Claim evidence is available here only to admins. |

These are read-only GET requests and do not require CSRF tokens. Their session authentication and role checks still apply; all mutating API calls require the session's `X-CSRF-Token`.

## Remaining limitations
- No user-management or admin close/delete endpoints exist, so the admin dashboard has no such screens.
- Item list responses carry no image info, so card thumbnails are fetched lazily per visible card.
- Registration always creates STUDENT accounts; staff/admin roles are set in MySQL.
- `/` has no page (no root route); open `/static/index.html`.

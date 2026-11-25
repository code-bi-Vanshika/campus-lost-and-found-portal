# Campus Lost & Found Portal

A full-stack campus portal for reporting lost items, reporting found items, submitting ownership claims, coordinating verification, and recording item handovers.

This project is implemented with a Python Flask JSON API, a MySQL relational database, and a server-rendered static frontend built with HTML, CSS, and vanilla JavaScript. It contains no framework build step and has no separate frontend package manager configuration.

## Key Features

- **Registration and login:** Public registration creates STUDENT accounts. Passwords are hashed before storage, and login establishes a server-side session.
- **Lost and found reports:** Authenticated STUDENT and STAFF users can create and edit their own reports and close active reports.
- **Item search:** Public item browsing supports text search and filters for category, location, item type, status, and date.
- **Images:** Found or lost item reports accept repeated JPEG, PNG, or WebP uploads. Images are validated by file signature, limited to 2 MB each, and stored as binary data in MySQL.
- **Ownership claims:** Authenticated users can submit one claim containing ownership evidence for a found item. Users cannot claim an item they reported.
- **Two-stage claim review:** The reporting finder makes the first approve/reject decision. An ADMIN makes the final approve/reject decision.
- **Approval and handover:** An administrator can cancel an approval before handover or record a handover after final approval.
- **Notifications:** Claim, decision, cancellation, and handover events create in-app notifications for the relevant users.
- **Role-specific views:** Separate pages support student/staff dashboards, personal reports and claims, finder review queues, notifications, and an admin dashboard.
- **Claim and handover queues:** The application provides paginated finder and handover queues, plus an administrator claim-review queue.
- **Database integrity:** Foreign keys, uniqueness rules, status check constraints, generated winning-claim indexes, transactions, and item-row locks help enforce the workflow.

## Technology Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, Flask |
| Database | MySQL 8.0.16 or newer |
| Database driver | mysql-connector-python |
| Authentication/session utilities | Werkzeug password hashing, Flask signed sessions |
| Frontend | HTML5, CSS3, vanilla JavaScript modules |
| Configuration | python-dotenv |
| Testing | Python `unittest` |

The project does not specify or pin a particular Python release. The repository's current virtual environment is not part of application source and should not be committed.

## Application Workflow

1. A user registers or logs in.
2. A STUDENT or STAFF user reports a LOST or FOUND item, optionally with images.
3. Other users browse or search public item listings.
4. A claimant submits ownership evidence for a FOUND item.
5. The finder reviews the claim:
   - A rejection requires remarks and ends the claim.
   - An approval advances the claim to administrator review.
6. An ADMIN reviews finder-approved claims:
   - Rejection ends the claim.
   - Approval sets the item to CLAIMED.
   - Before handover, the administrator can cancel the approval and reopen the item.
7. The ADMIN records handover after final approval. The item becomes RETURNED, and other pending claims are rejected.
8. The claimant, finder, and administrators receive relevant notifications.

There is no root page route. Run the Flask server and open `http://127.0.0.1:5000/static/index.html`.

## Database Tables

The schema is defined in [`schema.sql`](schema.sql). Dropdown values are seeded with [`seed.sql`](seed.sql).

| Table | Purpose |
| --- | --- |
| `Users` | User profile, Werkzeug password hash, role (`STUDENT`, `STAFF`, or `ADMIN`), and phone number |
| `Categories` | Available item categories |
| `Locations` | Available campus locations |
| `Items` | Lost/found reports, status, category, location, and reporting user |
| `Item_Images` | Item images stored as JPEG, PNG, or WebP binary data in MySQL |
| `Claims` | Ownership evidence, finder decision, administrator decision, claim status, and approval rules |
| `Handover` | Handover date, remarks, and the administrator who recorded it |
| `Notifications` | User inbox messages and optional links to claims |

Important relationships include:

- `Items.user_id` belongs to `Users.user_id`.
- `Items.category_id` belongs to `Categories.category_id`.
- `Items.location_id` belongs to `Locations.location_id`.
- `Item_Images.item_id` belongs to `Items.item_id` and cascades on item-image deletion.
- `Claims.item_id` and `Claims.claimant_id` belong to `Items.item_id` and `Users.user_id`.
- `Claims.admin_id` belongs to the administrator in `Users`.
- `Handover.claim_id` belongs to `Claims.claim_id`.
- `Notifications.user_id` belongs to `Users.user_id`; `Notifications.claim_id` is optional.

## Project Directory Structure

```text
Campus_Lost_Found_Project_Final/
|-- backend/
|   |-- app.py                 # Flask application factory and route registration
|   |-- config.py              # Environment-backed application settings
|   |-- db.py                  # MySQL connection and transaction helpers
|   |-- security.py            # Session user lookup, CSRF, and role decorators
|   |-- routes/
|   |   |-- auth.py            # Registration, login, logout, and current user
|   |   |-- items.py           # Item reports, search, editing, closing, and images
|   |   |-- claims.py          # Claim submission, review, queues, cancellation, handover
|   |   |-- notifications.py   # Notification listing and read state
|   |   `-- admin.py           # Administrator dashboard counts
|   `-- static/
|       |-- *.html             # Portal pages
|       |-- css/styles.css
|       `-- js/
|           |-- api.js         # Shared fetch and session/CSRF wrapper
|           |-- auth.js
|           |-- layout.js
|           |-- ui.js
|           |-- claims-ui.js
|           |-- item-cards.js
|           |-- icons.js
|           `-- pages/         # Per-page JavaScript modules
|-- tests/
|   |-- bootstrap_test_database.py
|   |-- run_integration_tests.py
|   |-- run_local_integration_tests.py
|   |-- test_backend_integration.py
|   |-- test_backend_security.py
|   |-- test_database.py
|   |-- test_frontend_integration.py
|   `-- test_frontend_static.py
|-- .env.example
|-- .gitignore
|-- requirements.txt
|-- schema.sql                 # Development schema; destructive if rerun
|-- seed.sql                   # Category and location seed data
|-- tests.sql                  # Interactive database constraint tests
|-- audit.sql                  # Database consistency audit
|-- FRONTEND_README.md
`-- backend/README.md
```

## Windows PowerShell Setup

### Prerequisites

- Python 3 available from PowerShell
- MySQL 8.0.16 or newer
- A MySQL account that can create the application database and tables
- PowerShell execution policy that permits the local virtual-environment activation script

No exact Python version is declared by the project.

### 1. Open the project

```powershell
cd "C:\path\to\Campus_Lost_Found_Project_Final"
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Create the application database

Open MySQL Workbench or another MySQL client. Run [`schema.sql`](schema.sql) once for initial setup, then run [`seed.sql`](seed.sql).

> **Warning:** [`schema.sql`](schema.sql) starts with `DROP DATABASE IF EXISTS campus_lost_found`. It destroys existing data in `campus_lost_found`. Do not run it on a populated database.

The seed script is not destructive in the same way, but it assumes the `campus_lost_found` database exists.

### 4. Configure the environment

Create `.env` from the example:

```powershell
Copy-Item .env.example .env
```

Do not commit `.env`. It is ignored by Git.

Set private values in `.env` according to the table below. Never publish actual passwords or secret keys.

| Variable | Purpose |
| --- | --- |
| `FLASK_SECRET_KEY` | Required secret used by Flask sessions. Use a long, random, private value. |
| `FLASK_DEBUG` | Set `true` only for local development. |
| `COOKIE_SECURE` | Set `false` for local HTTP and `true` when the application is served over HTTPS. |
| `MYSQL_HOST` | MySQL host, normally `127.0.0.1`. |
| `MYSQL_PORT` | MySQL port, normally `3306`. |
| `MYSQL_USER` | Application MySQL account. |
| `MYSQL_PASSWORD` | Password for the application MySQL account. |
| `MYSQL_DATABASE` | Application database; defaults to `campus_lost_found`. |
| `LOG_LEVEL` | Flask/Python log level; defaults to `INFO`. |
| `TEST_MYSQL_*` | Dedicated test-database settings described under Testing. |
| `TEST_ACCOUNT_PASSWORD` | Password used for accounts created by integration tests. |

Public registration always creates STUDENT accounts. To create an ADMIN or STAFF account, register normally and update the trusted database row with MySQL Workbench or a database administrator. The application itself does not provide a role-management endpoint.

### 5. Run the application

From the repository root:

```powershell
python -m backend.app
```

Open:

```text
http://127.0.0.1:5000/static/index.html
```

Use the Flask address rather than opening the HTML file directly, because login and CSRF protection depend on same-origin session cookies.

## Testing

Run all commands from the repository root.

### Static frontend and security tests

These tests require no database:

```powershell
python -m unittest tests.test_frontend_static -v
python -m unittest tests.test_backend_security -v
```

The static test verifies Flask API contracts, page/script/module links, HTML element IDs, role declarations, browser-storage restrictions, and public/private response shapes. The security test verifies CSRF enforcement, request validation, authentication rules, image validation, and transaction commit/rollback behavior.

### Integration-test database setup

The integration suite uses only `campus_lost_found_test`. Configure these values in `.env`:

- `TEST_MYSQL_DATABASE=campus_lost_found_test`
- `TEST_MYSQL_HOST`
- `TEST_MYSQL_PORT`
- `TEST_MYSQL_USER`
- `TEST_MYSQL_PASSWORD`
- `TEST_ACCOUNT_PASSWORD`

The test bootstrap prompts for an existing MySQL administrator account and creates a dedicated test database/account only where permitted:

```powershell
python tests/bootstrap_test_database.py
```

The bootstrap:

- Requires `TEST_MYSQL_DATABASE` to equal `campus_lost_found_test`.
- Creates the test database and runner account.
- Imports a safe subset of [`schema.sql`](schema.sql) and [`seed.sql`](seed.sql).
- Checks that the runner account has no grants outside the test database.

The integration suite verifies the selected database before running. It refuses `campus_lost_found` and aborts if the test database or grants are unsafe.

Run the integration suite:

```powershell
python tests/run_local_integration_tests.py
```

This runner executes both [`test_backend_integration.py`](tests/test_backend_integration.py) and [`test_frontend_integration.py`](tests/test_frontend_integration.py). It is designed to test authentication/CSRF, item lifecycle, uploads, privacy, roles, competing claims, finder/admin decisions, approval cancellation, handovers, and notifications.

### Database constraint tests

[`tests.sql`](tests.sql) is an interactive MySQL Workbench script containing setup, constraint/error tests, and rollback instructions.

> **DANGER: `tests.sql` must only run against `campus_lost_found_test`.** It uses `USE campus_lost_found_test` and inserts, updates, and deletes test records. Never execute it against `campus_lost_found` or any database containing real data.

For general database consistency, [`audit.sql`](audit.sql) contains read-only audit queries against `campus_lost_found`. Every query is intended to return zero rows.

## Security Features Verified in the Code

- Mutating API requests require a valid session CSRF token.
- Login clears the existing session and rotates the CSRF token.
- Passwords are rejected if shorter than 12 characters or longer than 128 characters and are stored with Werkzeug password hashes.
- Route-specific role decorators restrict STUDENT/STAFF and ADMIN actions.
- Public item responses do not include ownership evidence or reporter contact details.
- Ownership evidence is limited to authorized claimants, the reporting finder, and administrators.
- Uploaded images are checked by signature, MIME type, and 2 MB size limit.
- Image responses include `X-Content-Type-Options: nosniff`.
- `next` redirects after login are restricted to known local portal pages.
- The frontend does not use browser storage or browser cookies for application data.
- Database queries use parameterized values.
- Mutating claim and item workflows use transactions and, where necessary, MySQL row locks.

The project implements these application-level controls but does not claim to provide formal security certification or HTTPS configuration of its own. Cookie and development settings are environment-controlled.

## Current Repository Limitations

- The project does not include Docker, a hosted deployment, or deployment configuration.
- No license file is present. A repository maintainer should add one before public distribution if an open-source license is intended.
- No automated CI workflow is present in the inspected project.
- Public registration cannot create ADMIN or STAFF accounts; roles must be assigned through MySQL by a trusted administrator.
- The application does not include user-management or item-deletion endpoints.
- The application has no root (`/`) route; serve the static index explicitly.

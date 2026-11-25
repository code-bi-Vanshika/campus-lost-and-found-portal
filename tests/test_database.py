import os
import re
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


TEST_DATABASE = "campus_lost_found_test"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = PROJECT_ROOT / "schema.sql"
SEED_FILE = PROJECT_ROOT / "seed.sql"
load_dotenv(PROJECT_ROOT / ".env")


class TestDatabaseSafetyError(RuntimeError):
    pass


def require_safe_test_database_name(database):
    if database != TEST_DATABASE:
        raise TestDatabaseSafetyError(
            "Refusing to use a database other than campus_lost_found_test."
        )
    return database


def get_test_database_config():
    database = os.environ.get("TEST_MYSQL_DATABASE")
    require_safe_test_database_name(database)

    user = os.environ.get("TEST_MYSQL_USER", "").strip()
    password = os.environ.get("TEST_MYSQL_PASSWORD")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}", user):
        raise TestDatabaseSafetyError("TEST_MYSQL_USER is missing or invalid.")
    if password is None or not password:
        raise TestDatabaseSafetyError("TEST_MYSQL_PASSWORD is missing.")

    return {
        "host": os.environ.get("TEST_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("TEST_MYSQL_PORT", "3306")),
        "user": user,
        "password": password,
        "database": TEST_DATABASE,
        "connection_timeout": 5,
        "charset": "utf8mb4",
        "use_unicode": True,
    }


def verify_connection_database(connection):
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT DATABASE()")
        selected = cursor.fetchone()[0]
    finally:
        cursor.close()
    require_safe_test_database_name(selected)


def _sql_literal(value):
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _mysql_account(user, host):
    return _sql_literal(user) + "@" + _sql_literal(host)


def _split_statements(sql):
    statements = []
    current = []
    in_string = None
    escaped = False
    for char in sql:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char in {"'", '"'}:
            if in_string == char:
                in_string = None
            elif in_string is None:
                in_string = char
        if char == ";" and in_string is None:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def _read_safe_schema():
    safe_statements = []
    database_command = re.compile(
        r"^\s*(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s+)",
        re.IGNORECASE,
    )
    for line in SCHEMA_FILE.read_text(encoding="utf-8").splitlines():
        if database_command.match(line):
            continue
        safe_statements.append(line)
    text = "\n".join(safe_statements)
    if re.search(
        r"\b(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s+(?:campus_lost_found|`?campus_lost_found_test`?))",
        text,
        re.IGNORECASE,
    ):
        raise TestDatabaseSafetyError("schema.sql contains an unsafe database command.")
    return _split_statements(text)


def _read_safe_seed():
    safe_statements = []
    unsafe_database_command = re.compile(
        r"^\s*(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s+)",
        re.IGNORECASE,
    )
    for line in SEED_FILE.read_text(encoding="utf-8").splitlines():
        if unsafe_database_command.match(line):
            continue
        safe_statements.append(line)
    text = "\n".join(safe_statements)
    if re.search(
        r"\b(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s+)",
        text,
        re.IGNORECASE,
    ):
        raise TestDatabaseSafetyError("seed.sql contains an unsafe database command.")
    text = re.sub(r"\bINSERT\s+INTO\b", "INSERT IGNORE INTO", text, flags=re.IGNORECASE)
    return _split_statements(text)


def inspect_test_user_grants(connection):
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT CURRENT_USER()")
        account = cursor.fetchone()[0]
        match = re.fullmatch(r"'([^']*)'@'([^']*)'", account)
        if not match:
            match = re.fullmatch(r"([^@]+)@(.+)", account)
        if not match:
            raise TestDatabaseSafetyError(
                "The test account format returned by MySQL could not be verified."
            )
        user, host = match.groups()
        account_sql = _sql_literal(user) + "@" + _sql_literal(host)
        cursor.execute("SHOW GRANTS FOR " + account_sql)
        grants = [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
    unexpected = []
    for grant in grants:
        upper = grant.upper()
        if "USAGE ON *.*" in upper:
            continue
        if "`CAMPUS_LOST_FOUND_TEST`" not in upper:
            unexpected.append(grant)
    return {"account": account, "grants": grants, "unexpected": unexpected}


def ensure_test_database():
    test_config = get_test_database_config()

    connection = mysql.connector.connect(**test_config)
    try:
        verify_connection_database(connection)
    except mysql.connector.Error as error:
        raise TestDatabaseSafetyError(
            "Test database connection verification failed: "
            f"errno={getattr(error, 'errno', 'unknown')}; "
            f"sqlstate={getattr(error, 'sqlstate', 'unknown')}; "
            "statement=SELECT DATABASE()"
        ) from error
    cursor = connection.cursor()
    try:
        cursor.execute("SHOW TABLES")
        existing_tables = {row[0] for row in cursor.fetchall()}
        expected_tables = {
            "users", "categories", "locations", "items", "item_images",
            "claims", "handover", "notifications",
        }
        if not expected_tables.issubset(existing_tables):
            raise TestDatabaseSafetyError(
                "The campus_lost_found_test database does not contain the "
                "complete portal schema. Run the explicit bootstrap first."
            )
        cursor.execute("SELECT COUNT(*) FROM Categories")
        category_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM Locations")
        location_count = cursor.fetchone()[0]
        if category_count == 0 or location_count == 0:
            raise TestDatabaseSafetyError(
                "The test database seed data is incomplete. "
                "Run the explicit bootstrap first."
            )
    finally:
        cursor.close()
        connection.close()

    return test_config

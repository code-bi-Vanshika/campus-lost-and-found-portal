import getpass
import os
import re

import mysql.connector
from dotenv import dotenv_values


TEST_DATABASE = "campus_lost_found_test"
TEST_USER = "campus_lost_found_test_runner"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


def sql_literal(value):
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def read_test_configuration():
    values = dotenv_values(ENV_PATH)
    database = values.get("TEST_MYSQL_DATABASE")
    host = values.get("TEST_MYSQL_HOST")
    port = values.get("TEST_MYSQL_PORT")
    runner_password = values.get("TEST_MYSQL_PASSWORD")

    if database != TEST_DATABASE:
        raise RuntimeError(
            "TEST_MYSQL_DATABASE must be exactly campus_lost_found_test."
        )
    if not host or not port:
        raise RuntimeError("TEST_MYSQL_HOST and TEST_MYSQL_PORT are required.")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}", TEST_USER):
        raise RuntimeError("The test user name is invalid.")
    if not runner_password:
        raise RuntimeError(
            "TEST_MYSQL_PASSWORD must contain a separate test-runner password."
        )

    try:
        port_number = int(port)
    except ValueError:
        raise RuntimeError("TEST_MYSQL_PORT must be an integer.")

    return host, port_number, runner_password


def split_statements(sql):
    statements = []
    current = []
    in_string = None
    for char in sql:
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


def read_safe_schema():
    text = open(
        os.path.join(PROJECT_ROOT, "schema.sql"),
        "r",
        encoding="utf-8",
    ).read()
    text = "\n".join(
        line for line in text.splitlines()
        if not re.match(
            r"^\s*(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s+)",
            line,
            re.IGNORECASE,
        )
        and not re.match(
            r"^\s*(CHARACTER\s+SET|COLLATE)\b",
            line,
            re.IGNORECASE,
        )
        and not line.lstrip().startswith("--")
    )
    return split_statements(text)


def read_safe_seed():
    text = open(
        os.path.join(PROJECT_ROOT, "seed.sql"),
        "r",
        encoding="utf-8",
    ).read()
    text = "\n".join(
        line for line in text.splitlines()
        if not re.match(
            r"^\s*(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s+)",
            line,
            re.IGNORECASE,
        )
        and not line.lstrip().startswith("--")
    )
    text = re.sub(
        r"\bINSERT\s+INTO\b",
        "INSERT IGNORE INTO",
        text,
        flags=re.IGNORECASE,
    )
    return split_statements(text)


def main():
    host, port, runner_password = read_test_configuration()

    admin_user = input("Existing MySQL administrator username: ").strip()
    admin_password = getpass.getpass(
        "Existing MySQL administrator password: "
    )

    if not admin_user or not admin_password:
        raise RuntimeError("Administrator credentials are required.")

    connection = mysql.connector.connect(
        host=host,
        port=port,
        user=admin_user,
        password=admin_password,
        database=None,
        connection_timeout=5,
        charset="utf8mb4",
        use_unicode=True,
    )

    cursor = connection.cursor()
    try:
        statements = [
            (
                "CREATE DATABASE IF NOT EXISTS `campus_lost_found_test` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci",
                "create test database",
            ),
            (
                "CREATE USER IF NOT EXISTS "
                + sql_literal(TEST_USER)
                + "@"
                + sql_literal("localhost")
                + " IDENTIFIED BY "
                + sql_literal(runner_password),
                "create localhost test user",
            ),
            (
                "GRANT ALL PRIVILEGES ON `campus_lost_found_test`.* "
                "TO "
                + sql_literal(TEST_USER)
                + "@"
                + sql_literal("localhost"),
                "grant test-database privileges",
            ),
            ("FLUSH PRIVILEGES", "refresh privileges"),
        ]

        for statement, description in statements:
            try:
                cursor.execute(statement)
            except mysql.connector.Error as error:
                print(
                    "SETUP FAILED: "
                    f"errno={getattr(error, 'errno', 'unknown')}; "
                    f"sqlstate={getattr(error, 'sqlstate', 'unknown')}; "
                    f"statement={description}"
                )
                raise
    finally:
        cursor.close()
        connection.close()

    runner_connection = mysql.connector.connect(
        host=host,
        port=port,
        user=TEST_USER,
        password=runner_password,
        database=TEST_DATABASE,
        connection_timeout=5,
        charset="utf8mb4",
        use_unicode=True,
        autocommit=True,
    )
    runner_cursor = runner_connection.cursor()
    try:
        runner_cursor.execute("SELECT DATABASE()")
        selected_database = runner_cursor.fetchone()[0]
        if selected_database != TEST_DATABASE:
            raise RuntimeError(
                "Test runner did not select campus_lost_found_test."
            )

        runner_cursor.execute("SHOW TABLES")
        existing_tables = {row[0] for row in runner_cursor.fetchall()}
        if not existing_tables:
            for statement in read_safe_schema():
                try:
                    runner_cursor.execute(statement)
                    runner_cursor.fetchall()
                except mysql.connector.Error as error:
                    print(
                        "SETUP FAILED: "
                        f"errno={getattr(error, 'errno', 'unknown')}; "
                        f"sqlstate={getattr(error, 'sqlstate', 'unknown')}; "
                        "statement=safe test schema statement"
                    )
                    raise

        runner_cursor.execute("SELECT COUNT(*) FROM Categories")
        category_count = runner_cursor.fetchone()[0]
        runner_cursor.execute("SELECT COUNT(*) FROM Locations")
        location_count = runner_cursor.fetchone()[0]
        if category_count == 0 or location_count == 0:
            for statement in read_safe_seed():
                try:
                    runner_cursor.execute(statement)
                    runner_cursor.fetchall()
                except mysql.connector.Error as error:
                    print(
                        "SETUP FAILED: "
                        f"errno={getattr(error, 'errno', 'unknown')}; "
                        f"sqlstate={getattr(error, 'sqlstate', 'unknown')}; "
                        "statement=safe test seed statement"
                    )
                    raise

    finally:
        runner_cursor.close()

    grant_cursor = runner_connection.cursor()
    try:
        grant_cursor.execute(
            "SHOW GRANTS FOR "
            + sql_literal(TEST_USER)
            + "@"
            + sql_literal("localhost")
        )
        grants = [row[0] for row in grant_cursor.fetchall()]
    finally:
        grant_cursor.close()
        runner_connection.close()

    unexpected = []
    for grant in grants:
        normalized = grant.upper()
        if "USAGE ON *.*" in normalized:
            continue
        if "`CAMPUS_LOST_FOUND_TEST`" not in normalized:
            unexpected.append(grant)

    if unexpected:
        print("SETUP FAILED: unexpected privileges detected outside the test database.")
        return 1

    print(
        "SETUP COMPLETE: test database and localhost runner account "
        "are verified. No password was printed."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except mysql.connector.Error as error:
        print(
            "SETUP FAILED: "
            f"errno={getattr(error, 'errno', 'unknown')}; "
            f"sqlstate={getattr(error, 'sqlstate', 'unknown')}; "
            "statement=test database setup"
        )
        raise SystemExit(1)
    except RuntimeError as error:
        print("SETUP FAILED: " + str(error))
        raise SystemExit(1)

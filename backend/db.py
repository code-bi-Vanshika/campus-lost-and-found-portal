from contextlib import contextmanager

import mysql.connector
from flask import current_app, g


def get_db():
    if "db_connection" not in g:
        configuration = current_app.config["MYSQL_CONFIG"].copy()
        if not configuration["user"]:
            raise RuntimeError("MYSQL_USER must be configured.")
        g.db_connection = mysql.connector.connect(
            **configuration,
            autocommit=True,
        )
    return g.db_connection


def close_db(_error=None):
    connection = g.pop("db_connection", None)
    if connection is not None and connection.is_connected():
        connection.close()


@contextmanager
def transaction(connection=None):
    connection = connection or get_db()
    connection.start_transaction()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
import sys
import unittest
from pathlib import Path

import mysql.connector


TEST_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TEST_ROOT))

from test_database import ensure_test_database, TestDatabaseSafetyError
from test_backend_integration import CampusLostFoundIntegrationTests
from test_frontend_integration import FrontendIntegrationTests


def main():
    try:
        ensure_test_database()
    except TestDatabaseSafetyError as error:
        print("TEST SETUP FAILED: " + str(error))
        return 2
    except mysql.connector.Error as error:
        print(
            "TEST SETUP FAILED: "
            f"errno={getattr(error, 'errno', 'unknown')}; "
            f"sqlstate={getattr(error, 'sqlstate', 'unknown')}; "
            "statement=test database connection or setup"
        )
        return 2
    except Exception as error:
        print("TEST SETUP FAILED: " + type(error).__name__)
        return 2

    suite = unittest.TestSuite()
    for case in (CampusLostFoundIntegrationTests, FrontendIntegrationTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print(
        "\nTEST REPORT: "
        + str(result.testsRun)
        + " run, "
        + str(len(result.failures))
        + " failed, "
        + str(len(result.errors))
        + " errors, "
        + str(max(0, result.testsRun - len(result.failures) - len(result.errors)))
        + " passed"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

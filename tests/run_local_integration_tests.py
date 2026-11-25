import os
import sys
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = PROJECT_ROOT / "tests"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TEST_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

os.environ["TEST_MYSQL_DATABASE"] = "campus_lost_found_test"
os.environ["TEST_MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "127.0.0.1")
os.environ["TEST_MYSQL_PORT"] = os.environ.get("MYSQL_PORT", "3306")
os.environ["TEST_MYSQL_USER"] = "campus_lost_found_test_runner"
if __name__ == "__main__":
    from run_integration_tests import main
    exit_code = main()
    raise SystemExit(exit_code)

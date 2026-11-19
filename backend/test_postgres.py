"""Integration tests against a real PostgreSQL. Skipped unless TEST_DB_HOST is set; the
pipeline sets it and starts a database beside the job.

  export TEST_DB_PASSWORD=$(openssl rand -hex 24)
  docker run -d --name pg -e POSTGRES_PASSWORD=$TEST_DB_PASSWORD -p 127.0.0.1:55432:5432 postgres:17-alpine
  TEST_DB_HOST=127.0.0.1 TEST_DB_PORT=55432 python3 -m unittest -v test_postgres
"""
import os
import tempfile
import unittest
import uuid

import server

HOST = os.environ.get("TEST_DB_HOST")


@unittest.skipUnless(HOST, "TEST_DB_HOST is not set")
class PostgresVisitsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        values = {
            "DB_HOST": HOST,
            "DB_PORT": os.environ.get("TEST_DB_PORT", "5432"),
            "DB_NAME": os.environ.get("TEST_DB_NAME", "postgres"),
            "DB_USER": os.environ.get("TEST_DB_USER", "postgres"),
            "DB_PASSWORD": os.environ.get("TEST_DB_PASSWORD", ""),
        }
        for name, value in values.items():
            with open(os.path.join(self.folder.name, name), "w", encoding="utf-8") as handle:
                handle.write(value)
        server.SECRET_DIR = self.folder.name
        os.environ["DB_SSLMODE"] = "disable"
        # A new schema for every test, so each one starts from a database with no table.
        os.environ["ENVIRONMENT"] = "t" + uuid.uuid4().hex[:12]

    def tearDown(self):
        self.folder.cleanup()
        os.environ.pop("DB_SSLMODE", None)
        os.environ["ENVIRONMENT"] = "local"

    def test_first_read_on_a_fresh_database_is_zero(self):
        self.assertEqual(server.visits(add=False), (0, "postgres"))

    def test_writes_are_counted_and_kept(self):
        server.visits(add=True)
        server.visits(add=True)
        self.assertEqual(server.visits(add=False), (2, "postgres"))

    def test_environments_do_not_share_a_count(self):
        server.visits(add=True)
        os.environ["ENVIRONMENT"] = "t" + uuid.uuid4().hex[:12]
        self.assertEqual(server.visits(add=False)[0], 0)


if __name__ == "__main__":
    unittest.main()

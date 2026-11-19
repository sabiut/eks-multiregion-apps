import os
import tempfile
import unittest

import server


class IdentityTest(unittest.TestCase):
    def test_reports_version_and_region(self):
        os.environ["VERSION"] = "abc1234"
        os.environ["REGION"] = "ap-southeast-2"
        body = server.identity()
        self.assertEqual(body["version"], "abc1234")
        self.assertEqual(body["region"], "ap-southeast-2")

    def test_secret_value_is_never_returned(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "API_KEY"), "w", encoding="utf-8") as handle:
                handle.write("not-for-display")
            server.SECRET_DIR = folder
            body = server.identity()
            self.assertTrue(body["api_key_loaded"])
            self.assertNotIn("not-for-display", str(body))

    def test_missing_secret_is_not_an_error(self):
        server.SECRET_DIR = "/nonexistent"
        self.assertEqual(server.identity()["greeting"], "no secret mounted")


class VisitsTest(unittest.TestCase):
    def setUp(self):
        server.SECRET_DIR = "/nonexistent"   # no DB_HOST file: the in-memory counter is used
        server._memory["visits"] = 0

    def test_reading_does_not_count(self):
        self.assertEqual(server.visits(add=False)[0], 0)

    def test_adding_counts(self):
        server.visits(add=True)
        count, store = server.visits(add=True)
        self.assertEqual(count, 2)
        self.assertIn("memory", store)

    def test_database_settings_come_from_secret_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, value in {"DB_HOST": "db.internal", "DB_USER": "app", "DB_PASSWORD": "x"}.items():
                with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                    handle.write(value)
            server.SECRET_DIR = folder
            settings = server.database_settings()
            self.assertEqual(settings["host"], "db.internal")
            self.assertEqual(settings["sslmode"], "require")

    def test_schema_name_is_sanitised(self):
        os.environ["ENVIRONMENT"] = 'prd"; drop'
        self.assertEqual(server.schema(), "prddrop")
        os.environ["ENVIRONMENT"] = "stg"


if __name__ == "__main__":
    unittest.main()

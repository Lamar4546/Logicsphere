import unittest

from app.services.integration_service import import_records


class IntegrationValidationTests(unittest.TestCase):
    def test_rejects_invalid_system_resource_pair_without_database_access(self):
        with self.assertRaisesRegex(ValueError, "WMS for inventory"):
            import_records("org", "erp", "inventory", [])


if __name__ == "__main__":
    unittest.main()

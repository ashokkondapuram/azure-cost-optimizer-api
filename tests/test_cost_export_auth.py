"""Cost export storage auth resolution (no live Azure calls)."""
import os
import unittest
from unittest.mock import patch

from app import cost_export


class CostExportAuthTests(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_explicit_account_key_over_connection_string(self):
        with patch.dict(
            os.environ,
            {
                "COST_EXPORT_ACCOUNT_NAME": "coststore",
                "COST_EXPORT_ACCOUNT_KEY": "secretkey",
                "COST_EXPORT_CONNECTION_STRING": "DefaultEndpointsProtocol=https;AccountName=x;AccountKey=y;EndpointSuffix=core.windows.net",
            },
            clear=True,
        ):
            self.assertEqual(cost_export._auth_method(), "account_key")

    def test_connection_string_preferred_over_sas(self):
        with patch.dict(
            os.environ,
            {
                "COST_EXPORT_CONNECTION_STRING": "DefaultEndpointsProtocol=https;AccountName=x;AccountKey=y;EndpointSuffix=core.windows.net",
                "COST_EXPORT_SAS_URL": "https://x.blob.core.windows.net/cost?sv=old",
            },
            clear=True,
        ):
            self.assertEqual(cost_export._auth_method(), "connection_string")

    def test_account_key_when_no_connection_string(self):
        with patch.dict(
            os.environ,
            {
                "COST_EXPORT_ACCOUNT_NAME": "mystorage",
                "COST_EXPORT_ACCOUNT_KEY": "secretkey",
            },
            clear=True,
        ):
            self.assertEqual(cost_export._auth_method(), "account_key")

    def test_app_service_storage_connstr(self):
        with patch.dict(
            os.environ,
            {"STORAGECONNSTR_CostExport": "DefaultEndpointsProtocol=https;AccountName=z;AccountKey=k"},
            clear=True,
        ):
            self.assertEqual(cost_export._connection_string(), "DefaultEndpointsProtocol=https;AccountName=z;AccountKey=k")
            self.assertEqual(cost_export._auth_method(), "connection_string")

    def test_sas_only_when_no_keys(self):
        with patch.dict(
            os.environ,
            {"COST_EXPORT_SAS_URL": "https://x.blob.core.windows.net/cost?sv=1"},
            clear=True,
        ):
            self.assertEqual(cost_export._auth_method(), "sas_url")


if __name__ == "__main__":
    unittest.main()

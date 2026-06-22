import os
import requests
from azure.identity import DefaultAzureCredential


class AzureCostClient:
    def __init__(self):
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.api_version = "2023-03-01"
        self.base_url = "https://management.azure.com"

    def _get_token(self) -> str:
        token = self.credential.get_token("https://management.azure.com/.default")
        return token.token

    def query_cost(self, scope: str, timeframe: str = "MonthToDate", granularity: str = "Daily") -> dict:
        url = f"{self.base_url}{scope}/providers/Microsoft.CostManagement/query?api-version={self.api_version}"
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json"
        }
        payload = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": {
                "granularity": granularity,
                "aggregation": {
                    "totalCost": {
                        "name": "PreTaxCost",
                        "function": "Sum"
                    }
                },
                "grouping": [
                    {
                        "type": "Dimension",
                        "name": "ResourceGroup"
                    }
                ]
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

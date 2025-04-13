"""
testrail_client.py

"""

import requests
from tenacity import retry, stop_after_attempt, wait_exponential


class TestRailClient:
    """
    A client for interacting with the TestRail API.

    """

    def __init__(self, config):
        """
        Initialize the TestRail client.

        Args:
            config (dict): Configuration settings for TestRail.
        """

        self.base_url = config["base_url"].rstrip("/")
        self.auth = (config["username"], config["api_key"])
        self.project_id = config["project_id"]
        self.suite_id = config.get("suite_id")
        self.run_id = None

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5)
    )
    def create_test_run(self, name):
        """
        Create a new test run in TestRail.

        Args:
            name (str): The name of the test run.

        Raises:
            requests.exceptions.HTTPError: If the API request fails.
        """

        url = f"{self.base_url}/index.php?/api/v2/add_run/{self.project_id}"
        payload = {
            "name": name,
            "suite_id": self.suite_id,
            "include_all": False,
            "case_ids": [],
        }
        response = requests.post(url, auth=self.auth, json=payload, timeout=5)
        response.raise_for_status()
        self.run_id = response.json()["id"]

    @retry(wait=wait_exponential(multiplier=1), stop=stop_after_attempt(5))
    def add_cases_to_run(self, case_ids):
        """
        Add cases to an existing test run.

        Args:
            case_ids (set): A set of case IDs to add to the run.

        Raises:
            requests.exceptions.HTTPError: If the API request fails.
            ValueError: If the test run ID is not set.
        """
        if not self.run_id:
            raise ValueError("Test run ID is not set. Create a test run first.")

        url = f"{self.base_url}/index.php?/api/v2/update_run/{self.run_id}"
        response = requests.post(
            url, auth=self.auth, json={"case_ids": list(case_ids)}, timeout=5
        )
        response.raise_for_status()

    @retry(wait=wait_exponential(multiplier=1), stop=stop_after_attempt(5))
    def update_test_result(self, case_id, status_id, comment=""):
        """
        Update the result of a test case in TestRail.

        Args:
            case_id (str): The ID of the test case.
            status_id (int): The status ID of the test result.
            comment (str): A comment for the test result.

        Raises:
            requests.exceptions.HTTPError: If the API request fails.
            ValueError: If the test run ID is not set.
        """
        if not self.run_id:
            raise ValueError("Test run ID is not set. Create a test run first.")

        url = f"{self.base_url}/index.php?/api/v2/add_result_for_case/{self.run_id}/{case_id}"
        payload = {"status_id": status_id, "comment": comment}
        response = requests.post(url, auth=self.auth, json=payload, timeout=5)
        response.raise_for_status()

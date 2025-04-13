"""
testrail_client.py

This module provides a client for interacting with the TestRail API.

"""

import requests
from tenacity import retry, stop_after_attempt, wait_exponential


# Define TestrailException
class TestRailException(Exception):
    """
    Custom exception for TestRail API errors.
    """

    def __init__(self, message, response=None):
        """
        Initialize the TestRailException.

        Args:
            message (str): The error message.
            response (requests.Response, optional): The response object. Defaults to None.
        """
        super().__init__(message)
        self.response = response


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
        self.timeout = config.get("timeout", 5)  # Optional timeout configuration

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
        response = requests.post(
            url, auth=self.auth, json=payload, timeout=self.timeout
        )
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
            url, auth=self.auth, json={"case_ids": list(case_ids)}, timeout=self.timeout
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
        response = requests.post(
            url, auth=self.auth, json=payload, timeout=self.timeout
        )
        response.raise_for_status()

    @retry(wait=wait_exponential(multiplier=1), stop=stop_after_attempt(5))
    def attach_to_case(self, case_id, file_path):
        """
        Attach a file to a test case in TestRail.

        Args:
            case_id: The ID of the test case.
            file_path: The path to the file to attach.

        Raises:
            TestRailException: If the API request fails.
        """
        url = f"{self.base_url}/index.php?/api/v2/add_attachment_to_case/{self.project_id}/{case_id}"
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(
                url, files=files, auth=self.auth, timeout=self.timeout
            )
            if response.status_code != 200:
                raise TestRailException(f"Failed to attach file: {response.content}")

    @retry(wait=wait_exponential(multiplier=1), stop=stop_after_attempt(5))
    def add_comment_to_case(self, case_id, comment):
        """
        Add a comment to a test case in TestRail.

        Args:
            case_id: The ID of the test case.
            comment: The comment to add.

        Raises:
            TestRailException: If the API request fails.
        """
        url = f"{self.base_url}/index.php?/api/v2/add_result_for_case/{self.run_id}/{case_id}"
        payload = {"comment": comment}
        response = requests.post(
            url, json=payload, auth=self.auth, timeout=self.timeout
        )
        if response.status_code != 200:
            raise TestRailException(f"Failed to add comment: {response.content}")

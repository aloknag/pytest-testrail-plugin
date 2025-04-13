"""
testrail fixtures
"""

import logging

import pytest
import requests

from .testrail_client import TestRailClient, TestRailException

logger = logging.getLogger(__name__)


@pytest.fixture
def testrail(request):
    """
    Provides access to TestRail actions from within tests.

    Usage:
        def test_something(testrail):
            testrail.comment(123, "this ran")
            testrail.attach(123, "file.png")
            testrail.pass_case(123)
    """
    client: TestRailClient = request.config.testrail_client

    class TestrailHelper:
        """Testrail helper class"""

        def comment(self, case_id, text):
            """
            Add a comment to a test case in TestRail.

            Args:
                case_id (int): The ID of the test case.
                text (str): The comment text.
            """
            try:
                client.add_comment_to_case(case_id, text)
            except TestRailException as e:
                logger.error(f"Failed to add comment to case {case_id}: {e}")

        def attach(self, case_id, path):
            """
            Attach a file to a test case in TestRail.

            Args:
                case_id (int): The ID of the test case.
                path (str): The path to the file to attach.
            """
            try:
                client.attach_to_case(case_id, path)
            except TestRailException as e:
                logger.error(f"Failed to attach file to case {case_id}: {e}")

        def pass_case(self, case_id):
            """
            Mark a test case as passed in TestRail.

            Args:
                case_id (int): The ID of the test case.
            """
            try:
                client.update_test_result(case_id, status_id=1)  # 1 = Passed
            except TestRailException as e:
                logger.error(f"Failed to mark case {case_id} as passed: {e}")

        def fail_case(self, case_id):
            """
            Mark a test case as failed in TestRail.

            Args:
                case_id (int): The ID of the test case.
            """
            try:
                client.update_test_result(case_id, status_id=5)  # 5 = Failed
            except requests.exceptions.HTTPError as e:
                logger.error(f"Failed to mark case {case_id} as failed: {e}")
            except ValueError:
                logger.error("Test run ID is not set. Create a test run first.")

    return TestrailHelper()

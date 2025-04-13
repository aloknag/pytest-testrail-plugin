"""
pytest-testrail-plugin

"""

import logging
import os

import pytest
import yaml

# Register fixture
from .fixture import testrail as _testrail_fixture  # pylint: disable=unused-import
from .testrail_client import TestRailClient

logger = logging.getLogger(__name__)


# Add pytest options
def pytest_addoption(parser):
    """
    Add TestRail options to pytest.

    Args:
        parser: The pytest parser.
    """
    group = parser.getgroup("testrail")
    group.addoption(
        "--testrail-config", action="store", help="Path to TestRail YAML config"
    )
    group.addoption(
        "--testrail-dry-run", action="store_true", help="Dry run mode: no API calls"
    )
    group.addoption(
        "--testrail-log-mapping",
        action="store_true",
        help="Log pytest-to-CaseID mapping",
    )
    group.addoption(
        "--testrail-run-name", action="store", help="Override TestRail run name"
    )


def pytest_configure(config):
    """
    Configure the TestRail client and load settings.

    Args:
        config: The pytest configuration.
    """
    if config.getoption("--testrail-dry-run"):
        config.testrail_client = None
        return

    path = config.getoption("--testrail-config")
    if not path or not os.path.exists(path):
        logger.error("TestRail plugin skipped: --testrail-config not provided.")
        return

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = raw.get("testrail", {})

    cfg["username"] = os.environ.get("TESTRAIL_USERNAME", cfg.get("username"))
    cfg["api_key"] = os.environ.get("TESTRAIL_API_KEY", cfg.get("api_key"))

    if not cfg.get("api_key") or not cfg.get("username"):
        raise pytest.UsageError(
            "TestRail credentials must be set via environment or YAML."
        )

    config.testrail_client = TestRailClient(cfg)
    config.testrail_config = cfg


def pytest_collection_modifyitems(session, config, items):
    """
    Process collected test items and extract TestRail case IDs.

    Args:
        session: The pytest session.
        config: The pytest configuration.
        items: The collected test items.
    """
    mapping = {}
    reverse_mapping = {}

    for item in items:
        marker = item.get_closest_marker("testrail_case")
        if marker:
            case_ids = marker.args[0]
            case_list = case_ids if isinstance(case_ids, list) else [case_ids]
            item.testrail_case_ids = case_list
            mapping[item.nodeid] = case_list

            for cid in case_list:
                reverse_mapping.setdefault(cid, []).append(item.nodeid)

    config.testrail_case_mapping = mapping
    config.testrail_reverse_mapping = reverse_mapping


def pytest_sessionstart(session):
    """
    Start the TestRail session and create a test run.

    Args:
        session: The pytest session.
    """
    config = session.config
    dry_run = config.getoption("--testrail-dry-run")
    mapping = getattr(config, "testrail_case_mapping", {})
    reverse = getattr(config, "testrail_reverse_mapping", {})

    if config.getoption("--testrail-log-mapping"):
        print("\n[TESTRAIL] Case Mapping:")
        for nodeid, cases in mapping.items():
            print(f"  {nodeid} → {', '.join(cases)}")

        print("\n[TESTRAIL] Reverse Mapping:")
        for cid, tests in reverse.items():
            if len(tests) > 1:
                print(f"  ⚠️  Case ID {cid} mapped to multiple tests: {tests}")

    if dry_run:
        print("[DRY-RUN] Would create TestRail run and add all mapped cases.")
        return

    client = config.testrail_client
    run_name = config.getoption("--testrail-run-name") or "Automated Run (Real-Time)"
    client.create_test_run(name=run_name)

    all_case_ids = {case_id for case_list in mapping.values() for case_id in case_list}
    client.add_cases_to_run(all_case_ids)


def pytest_runtest_makereport(item, call):
    """
    Add custom properties to the report, storing TestRail case IDs for later use.

    Args:
        item: The pytest test item.
        call: The pytest call object.
    """
    # Store testrail_case_ids in report user properties for access in pytest_runtest_logreport
    if hasattr(item, "testrail_case_ids"):
        item.user_properties.append(("testrail_case_ids", item.testrail_case_ids))


def pytest_runtest_logreport(report):
    """
    Log test results to TestRail.

    Args:
        report: pytest report object.
    """
    if report.when != "call":
        return

    config = report.config
    dry_run = config.getoption("--testrail-dry-run")
    client = getattr(config, "testrail_client", None)

    if not hasattr(report, "nodeid") or not hasattr(report, "wasxfail"):
        return

    case_ids = next(
        (
            value
            for name, value in report.user_properties
            if name == "testrail_case_ids"
        ),
        None,
    )
    if not case_ids:
        return

    status = (
        1 if report.passed else (5 if report.failed else 2)
    )  # 1=passed, 5=failed, 2=blocked
    for cid in case_ids:
        if dry_run:
            print(f"[DRY-RUN] Would report: {report.nodeid} → {cid} → status {status}")
        else:
            client.update_test_result(
                case_id=cid, status_id=status, comment=report.nodeid
            )


# Helper functions for adding comments, attachments, and marking passed tests


def testrail_comment(comment, *case_ids):
    """
    Add a comment to the given TestRail cases.

    Args:
        comment (str): The comment to add.
        *case_ids: The TestRail case IDs to add the comment to.
    """

    def _comment_decorator(func):
        def wrapper(request, *args, **kwargs):
            client = request.config.testrail_client
            for case_id in case_ids:
                client.add_comment_to_case(case_id, comment)
            return func(request, *args, **kwargs)

        return wrapper

    return _comment_decorator


def testrail_attach(attachment_path, *case_ids):
    """
    Attach a file to the given TestRail cases.

    Args:
        attachment_path (str): The path to the file to attach.
        *case_ids: The TestRail case IDs to attach the file to.
    """

    def _attach_decorator(func):
        def wrapper(request, *args, **kwargs):
            client = request.config.testrail_client
            for case_id in case_ids:
                client.attach_to_case(case_id, attachment_path)
            return func(request, *args, **kwargs)

        return wrapper

    return _attach_decorator


def testrail_pass(*case_ids):
    """
    Mark the given TestRail cases as passed.

    Args:
        *case_ids: The TestRail case IDs to mark as passed.
    """

    def _pass_decorator(func):
        def wrapper(request, *args, **kwargs):
            client = request.config.testrail_client
            for case_id in case_ids:
                client.update_test_result(case_id, 1)  # Passed status
            return func(request, *args, **kwargs)

        return wrapper

    return _pass_decorator

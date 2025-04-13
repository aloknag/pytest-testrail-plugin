"""
pytest-testrail-plugin

"""

import logging
import os

import pytest
import yaml

from .testrail_client import TestRailClient

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    """
    Add TestRail options to pytest.

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
        config: pytest config object.

    Raises:
        pytest.UsageError: If the config file is missing or invalid.
        pytest.UsageError: If TestRail credentials are not set.


    """
    if config.getoption("--testrail-dry-run"):
        config.testrail_client = None
        return

    path = config.getoption("--testrail-config")
    if not path or not os.path.exists(path):
        raise pytest.UsageError(
            "--testrail-config must be provided and point to a valid YAML file"
        )

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


# pylint disable=unused-argument
def pytest_collection_modifyitems(
    session, config, items  # pylint disable=unused-argument
):
    """
    Process collected test items and extract TestRail case IDs.

    Args:
        session: pytest session object.
        config: pytest config object.
        items: list of pytest item objects.
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
        session: pytest session object.
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

    item = report
    case_ids = getattr(item, "testrail_case_ids", None)
    if not case_ids:
        return

    status = (
        1 if report.passed else (5 if report.failed else 2)
    )  # 1=passed, 5=failed, 2=blocked
    for cid in case_ids:
        if dry_run:
            print(f"[DRY-RUN] Would report: {item.nodeid} → {cid} → status {status}")
        else:
            client.update_test_result(
                case_id=cid, status_id=status, comment=item.nodeid
            )

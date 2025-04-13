import pytest
import yaml
from unittest import mock
from pytest_testrail_plugin import plugin
from pytest_testrail_plugin.testrail_client import TestRailClient

# --- Fixtures ---


@pytest.fixture
def mock_config(tmp_path):
    """Creates a mock pytest config object and a dummy config file."""
    config_data = {
        "testrail": {
            "base_url": "https://example.testrail.io/",
            "username": "testuser",
            "api_key": "testkey",
            "project_id": 1,
            "suite_id": 5,
        }
    }
    config_path = tmp_path / "testrail.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    # Mock the config object with necessary methods/attributes
    config = mock.Mock()
    config.getoption = mock.Mock(
        side_effect=lambda name: {
            "--testrail-config": str(config_path),
            "--testrail-dry-run": False,
            "--testrail-log-mapping": False,
            "--testrail-run-name": None,
        }.get(name)
    )
    config.testrail_client = None  # Will be set by pytest_configure
    config.testrail_config = None  # Will be set by pytest_configure
    config.testrail_case_mapping = {}
    config.testrail_reverse_mapping = {}
    return config


@pytest.fixture
def mock_item_factory():
    """Factory to create mock pytest Item objects."""

    def _create_item(nodeid, case_ids=None):
        item = mock.Mock(spec=pytest.Item)
        item.nodeid = nodeid
        marker = None
        if case_ids:
            marker = mock.Mock()
            marker.args = (case_ids,)
        item.get_closest_marker = mock.Mock(return_value=marker)
        # Add attribute that might be set later
        item.testrail_case_ids = None
        return item

    return _create_item


@pytest.fixture
def mock_report_factory(mock_config):
    """Factory to create mock pytest Report objects."""

    def _create_report(nodeid, outcome, when="call", case_ids=None, wasxfail=False):
        report = mock.Mock(spec=pytest.TestReport)
        report.nodeid = nodeid
        report.when = when
        report.passed = outcome == "passed"
        report.failed = outcome == "failed"
        report.skipped = outcome == "skipped"
        report.outcome = outcome
        report.wasxfail = wasxfail
        report.config = mock_config  # Link the report to the config
        # Simulate attribute set during collection
        report.testrail_case_ids = case_ids
        return report

    return _create_report


# --- Test Functions ---


def test_pytest_addoption():
    """Verify that TestRail options are added."""
    parser = mock.Mock()
    group = mock.Mock()
    parser.getgroup.return_value = group
    plugin.pytest_addoption(parser)

    parser.getgroup.assert_called_once_with("testrail")
    expected_calls = [
        mock.call("--testrail-config", action="store", help=mock.ANY),
        mock.call("--testrail-dry-run", action="store_true", help=mock.ANY),
        mock.call("--testrail-log-mapping", action="store_true", help=mock.ANY),
        mock.call("--testrail-run-name", action="store", help=mock.ANY),
    ]
    group.addoption.assert_has_calls(expected_calls, any_order=True)
    assert group.addoption.call_count == len(expected_calls)


def test_pytest_configure_success(mock_config, tmp_path):
    """Test successful configuration loading."""
    with mock.patch("pytest_testrail_plugin.plugin.TestRailClient") as MockClient:
        plugin.pytest_configure(mock_config)

        # Assert client was initialized
        MockClient.assert_called_once()
        call_args = MockClient.call_args[0][
            0
        ]  # Get the config dict passed to TestRailClient
        assert call_args["base_url"] == "https://example.testrail.io/"
        assert call_args["username"] == "testuser"
        assert call_args["api_key"] == "testkey"
        assert call_args["project_id"] == 1
        assert call_args["suite_id"] == 5

        # Assert config attributes are set
        assert isinstance(mock_config.testrail_client, (mock.Mock, mock.MagicMock))
        assert mock_config.testrail_config["base_url"] == "https://example.testrail.io/"


def test_pytest_configure_env_override(mock_config, monkeypatch, tmp_path):
    """Test environment variables override YAML config."""
    monkeypatch.setenv("TESTRAIL_USERNAME", "envuser")
    monkeypatch.setenv("TESTRAIL_API_KEY", "envkey")

    with mock.patch("pytest_testrail_plugin.plugin.TestRailClient") as MockClient:
        plugin.pytest_configure(mock_config)

        MockClient.assert_called_once()
        call_args = MockClient.call_args[0][0]
        assert call_args["username"] == "envuser"
        assert call_args["api_key"] == "envkey"
        assert mock_config.testrail_config["username"] == "envuser"
        assert mock_config.testrail_config["api_key"] == "envkey"


def test_pytest_configure_missing_config_file(mock_config):
    """Test error when config file path is invalid."""
    mock_config.getoption.side_effect = lambda name: {
        "--testrail-config": "/non/existent/path.yaml",
        "--testrail-dry-run": False,
    }.get(name)

    with pytest.raises(
        pytest.UsageError, match="must be provided and point to a valid YAML file"
    ):
        plugin.pytest_configure(mock_config)


def test_pytest_configure_missing_credentials(mock_config, tmp_path):
    """Test error when credentials are not provided."""
    # Create a config file without credentials
    config_data = {
        "testrail": {
            "base_url": "https://example.testrail.io/",
            "project_id": 1,
        }
    }
    config_path = tmp_path / "bad_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    mock_config.getoption.side_effect = lambda name: {
        "--testrail-config": str(config_path),
        "--testrail-dry-run": False,
    }.get(name)

    with pytest.raises(pytest.UsageError, match="TestRail credentials must be set"):
        plugin.pytest_configure(mock_config)


def test_pytest_configure_dry_run(mock_config):
    """Test dry-run mode skips client initialization."""
    mock_config.getoption.side_effect = lambda name: {
        "--testrail-config": "dummy_path",  # Path doesn't matter in dry run
        "--testrail-dry-run": True,
    }.get(name)

    with mock.patch("pytest_testrail_plugin.plugin.TestRailClient") as MockClient:
        plugin.pytest_configure(mock_config)
        assert mock_config.testrail_client is None
        MockClient.assert_not_called()


def test_pytest_collection_modifyitems(mock_config, mock_item_factory):
    """Test processing of test items and markers."""
    items = [
        mock_item_factory("test_one.py::test_a", case_ids="C1"),
        mock_item_factory("test_one.py::test_b", case_ids=["C2", "C3"]),
        mock_item_factory("test_two.py::test_c"),  # No marker
        mock_item_factory("test_one.py::test_d", case_ids="C3"),  # Duplicate case ID
    ]
    session = mock.Mock()  # Session isn't used directly in the function

    plugin.pytest_collection_modifyitems(session, mock_config, items)

    # Check item attributes
    assert items[0].testrail_case_ids == ["C1"]
    assert items[1].testrail_case_ids == ["C2", "C3"]
    assert items[2].testrail_case_ids is None  # Should not be set
    assert items[3].testrail_case_ids == ["C3"]

    # Check mappings on config
    expected_mapping = {
        "test_one.py::test_a": ["C1"],
        "test_one.py::test_b": ["C2", "C3"],
        "test_one.py::test_d": ["C3"],
    }
    expected_reverse_mapping = {
        "C1": ["test_one.py::test_a"],
        "C2": ["test_one.py::test_b"],
        "C3": ["test_one.py::test_b", "test_one.py::test_d"],
    }
    assert mock_config.testrail_case_mapping == expected_mapping
    assert mock_config.testrail_reverse_mapping == expected_reverse_mapping


@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_sessionstart(MockClient, mock_config):
    """Test session start creates run and adds cases."""
    # Setup mock client instance on config
    mock_client_instance = MockClient.return_value
    mock_config.testrail_client = mock_client_instance

    # Setup mappings as if collection happened
    mock_config.testrail_case_mapping = {
        "test_a": ["C1"],
        "test_b": ["C2", "C3"],
    }
    mock_config.testrail_reverse_mapping = {
        "C1": ["test_a"],
        "C2": ["test_b"],
        "C3": ["test_b"],
    }

    session = mock.Mock()
    session.config = mock_config

    plugin.pytest_sessionstart(session)

    # Verify client calls
    mock_client_instance.create_test_run.assert_called_once_with(
        name="Automated Run (Real-Time)"
    )
    mock_client_instance.add_cases_to_run.assert_called_once_with({"C1", "C2", "C3"})


@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_sessionstart_custom_run_name(MockClient, mock_config):
    """Test session start with a custom run name."""
    mock_client_instance = MockClient.return_value
    mock_config.testrail_client = mock_client_instance
    mock_config.getoption.side_effect = lambda name: {  # Override run name option
        "--testrail-config": "dummy",
        "--testrail-dry-run": False,
        "--testrail-log-mapping": False,
        "--testrail-run-name": "My Custom Run",
    }.get(
        name, False
    )  # Default to False for other options

    mock_config.testrail_case_mapping = {"test_a": ["C1"]}
    mock_config.testrail_reverse_mapping = {"C1": ["test_a"]}

    session = mock.Mock()
    session.config = mock_config

    plugin.pytest_sessionstart(session)

    mock_client_instance.create_test_run.assert_called_once_with(name="My Custom Run")
    mock_client_instance.add_cases_to_run.assert_called_once_with({"C1"})


@mock.patch("builtins.print")
@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_sessionstart_dry_run(MockClient, mock_print, mock_config):
    """Test session start in dry-run mode."""
    mock_config.getoption.side_effect = lambda name: {  # Enable dry run
        "--testrail-config": "dummy",
        "--testrail-dry-run": True,
        "--testrail-log-mapping": False,
        "--testrail-run-name": None,
    }.get(name, False)
    mock_config.testrail_client = None  # Client is None in dry run

    mock_config.testrail_case_mapping = {"test_a": ["C1"]}
    mock_config.testrail_reverse_mapping = {"C1": ["test_a"]}

    session = mock.Mock()
    session.config = mock_config

    plugin.pytest_sessionstart(session)

    # Verify no client calls were made
    MockClient.assert_not_called()
    MockClient.return_value.create_test_run.assert_not_called()
    MockClient.return_value.add_cases_to_run.assert_not_called()

    # Verify dry-run message
    mock_print.assert_any_call(
        "[DRY-RUN] Would create TestRail run and add all mapped cases."
    )


@mock.patch("builtins.print")
def test_pytest_sessionstart_log_mapping(mock_print, mock_config):
    """Test session start with log mapping enabled."""
    mock_config.getoption.side_effect = lambda name: {  # Enable log mapping
        "--testrail-config": "dummy",
        "--testrail-dry-run": True,  # Use dry run to avoid client setup
        "--testrail-log-mapping": True,
        "--testrail-run-name": None,
    }.get(name, False)
    mock_config.testrail_client = None

    mock_config.testrail_case_mapping = {
        "test_a": ["C1"],
        "test_b": ["C2", "C3"],
    }
    mock_config.testrail_reverse_mapping = {
        "C1": ["test_a"],
        "C2": ["test_b"],
        "C3": ["test_b", "test_c"],  # C3 mapped to multiple
    }

    session = mock.Mock()
    session.config = mock_config

    plugin.pytest_sessionstart(session)

    # Verify logging output
    mock_print.assert_any_call("\n[TESTRAIL] Case Mapping:")
    mock_print.assert_any_call("  test_a → C1")
    mock_print.assert_any_call("  test_b → C2, C3")
    mock_print.assert_any_call("\n[TESTRAIL] Reverse Mapping:")
    # Only logs cases mapped to multiple tests
    mock_print.assert_any_call(
        "  ⚠️  Case ID C3 mapped to multiple tests: ['test_b', 'test_c']"
    )
    # Check that C1 and C2 were NOT logged in reverse mapping section
    log_calls = [
        call[0][0] for call in mock_print.call_args_list
    ]  # Extract first arg of each print call
    assert not any("Case ID C1" in call for call in log_calls)
    assert not any("Case ID C2" in call for call in log_calls)


@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_runtest_logreport_passed(MockClient, mock_config, mock_report_factory):
    """Test reporting a passed test."""
    mock_client_instance = MockClient.return_value
    mock_config.testrail_client = mock_client_instance

    report = mock_report_factory("test_node_pass", "passed", case_ids=["C10"])

    plugin.pytest_runtest_logreport(report)

    mock_client_instance.update_test_result.assert_called_once_with(
        case_id="C10", status_id=1, comment="test_node_pass"
    )


@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_runtest_logreport_failed(MockClient, mock_config, mock_report_factory):
    """Test reporting a failed test."""
    mock_client_instance = MockClient.return_value
    mock_config.testrail_client = mock_client_instance

    report = mock_report_factory("test_node_fail", "failed", case_ids=["C11", "C12"])

    plugin.pytest_runtest_logreport(report)

    expected_calls = [
        mock.call(case_id="C11", status_id=5, comment="test_node_fail"),
        mock.call(case_id="C12", status_id=5, comment="test_node_fail"),
    ]
    mock_client_instance.update_test_result.assert_has_calls(
        expected_calls, any_order=True
    )
    assert mock_client_instance.update_test_result.call_count == 2


@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_runtest_logreport_skipped(MockClient, mock_config, mock_report_factory):
    """Test skipped tests are NOT reported (status 2 is 'blocked', not 'skipped')."""
    # Note: The current logic maps skipped tests to status 2 (Blocked).
    # If you want a different behavior (e.g., not reporting skips), adjust the test/code.
    mock_client_instance = MockClient.return_value
    mock_config.testrail_client = mock_client_instance

    report = mock_report_factory("test_node_skip", "skipped", case_ids=["C13"])

    plugin.pytest_runtest_logreport(report)

    # Current behavior: Skipped maps to Blocked (status 2)
    mock_client_instance.update_test_result.assert_called_once_with(
        case_id="C13", status_id=2, comment="test_node_skip"
    )


@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_runtest_logreport_wrong_phase(
    MockClient, mock_config, mock_report_factory
):
    """Test reports from phases other than 'call' are ignored."""
    mock_client_instance = MockClient.return_value
    mock_config.testrail_client = mock_client_instance

    report_setup = mock_report_factory(
        "test_node", "passed", when="setup", case_ids=["C14"]
    )
    report_teardown = mock_report_factory(
        "test_node", "passed", when="teardown", case_ids=["C14"]
    )

    plugin.pytest_runtest_logreport(report_setup)
    plugin.pytest_runtest_logreport(report_teardown)

    mock_client_instance.update_test_result.assert_not_called()


@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_runtest_logreport_no_case_ids(
    MockClient, mock_config, mock_report_factory
):
    """Test reports for items without case IDs are ignored."""
    mock_client_instance = MockClient.return_value
    mock_config.testrail_client = mock_client_instance

    report = mock_report_factory(
        "test_node_no_marker", "passed", case_ids=None
    )  # No case IDs

    plugin.pytest_runtest_logreport(report)

    mock_client_instance.update_test_result.assert_not_called()


@mock.patch("builtins.print")
@mock.patch("pytest_testrail_plugin.plugin.TestRailClient", spec=TestRailClient)
def test_pytest_runtest_logreport_dry_run(
    MockClient, mock_print, mock_config, mock_report_factory
):
    """Test dry-run behavior during report logging."""
    mock_config.getoption.side_effect = lambda name: {  # Enable dry run
        "--testrail-config": "dummy",
        "--testrail-dry-run": True,
        "--testrail-log-mapping": False,
        "--testrail-run-name": None,
    }.get(name, False)
    mock_config.testrail_client = None  # Client is None in dry run

    report = mock_report_factory("test_node_dry", "passed", case_ids=["C15"])

    plugin.pytest_runtest_logreport(report)

    # Verify no client calls
    MockClient.assert_not_called()
    MockClient.return_value.update_test_result.assert_not_called()

    # Verify dry-run print message
    mock_print.assert_called_once_with(
        "[DRY-RUN] Would report: test_node_dry → C15 → status 1"
    )

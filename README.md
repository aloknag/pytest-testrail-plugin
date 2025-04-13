# pytest-testrail-plugin
A Pytest plugin for real-time reporting of test results to [TestRail](https://www.gurock.com/testrail), with support for dry-run, case mapping logs, and resilient API integration.

## Installation

To install the plugin, run following command
```bash
pip install pytest-testrail-plugin
```
or install directly from GitHub
```bash
poetry add git+https://github.com/aloknag/pytest-testrail-plugin.git
```
alternatively, you can install after building the package:
```bash
poetry build
pip install dist/pytest_testrail_plugin-0.1.0.tar.gz
```

## Configuration
The plugin requires a valid TestRail account and project. You can configure the plugin using a YAML file (testrail.yaml) or by setting the following environment variables:

TESTRAIL_USERNAME (Your TestRail username)

TESTRAIL_API_KEY (Your TestRail API key)

Example `testrail.yaml` file:
```yaml
# testrail.yaml
testrail:
  base_url: "https://yourcompany.testrail.io"
  username: "your.email@example.com"
  api_key: "xxx"
  project_id: 1
  suite_id: 1
```

## Usage
1. Mark test cases with TestRail Case ID(s)

    You can use the @pytest.mark.testrail_case decorator to associate your tests with TestRail case IDs.
    ```python
    import pytest

    @pytest.mark.testrail_case("C123")
    def test_pass():
        assert True

    @pytest.mark.testrail_case(["C124", "C125"])
    def test_fail():
        assert False
    ```
2. Run tests with pytest

    Run your tests as usual with `pytest`.

    ```bash
    pytest --testrail-config testrail.yaml
    ```

3. Dry-run mode

    You can run the plugin in dry-run mode (without actually reporting to TestRail) using the --testrail-dry-run flag:

    ```bash
    pytest --testrail-config testrail.yaml --testrail-dry-run
    ```

4. TestRail Case Mapping Logging

    You can log the mapping of your tests to TestRail case IDs using the --testrail-log-mapping flag:

    ```bash
    pytest --testrail-config testrail.yaml --testrail-log-mapping
    ```

5. Over-ride Test Run Name

    You can over-ride test run name using the --testrail-run-name flag:

    ```bash
    pytest --testrail-config testrail.yaml --testrail-run-name "My Test Run"
    ```

## Features
- Real-time result updates to TestRail during the test run.

- Test case mapping between your tests and TestRail cases.

- Retry/backoff for handling TestRail API rate limits or temporary errors.

- Dry-run mode for testing without sending data to TestRail.

- Logging of test-case mappings and results.

## Example Run

```bash
pytest --testrail-config testrail.yaml --testrail-log-mapping --testrail-dry-run
```
This will simulate running the tests and log the mappings but will not make any actual API calls.

## License
MIT License



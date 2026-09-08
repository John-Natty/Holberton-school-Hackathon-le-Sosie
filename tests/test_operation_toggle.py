import pytest
from unittest.mock import Mock

import app.test_controls as test_controls
from app.agent_tools import verify_expenses_tool
from app.verification import verify_expenses


@pytest.fixture(autouse=True)
def _reset_toggles():
    test_controls._disabled_operations.clear()
    yield
    test_controls._disabled_operations.clear()


def test_endpoints_hidden_when_test_mode_is_off(client, monkeypatch):
    monkeypatch.delenv("ENABLE_TEST_CONTROLS", raising=False)
    assert client.get("/test/operations").status_code == 404
    assert client.post("/test/operations", json={"operation": "total", "enabled": False}).status_code == 404


def test_toggle_round_trip_when_enabled(client, monkeypatch):
    monkeypatch.setenv("ENABLE_TEST_CONTROLS", "1")
    assert client.get("/test/operations").get_json() == {
        "total": True, "total_by_category": True, "total_by_period": True,
    }
    response = client.post("/test/operations", json={"operation": "total_by_category", "enabled": False})
    assert response.get_json() == {"total": True, "total_by_category": False, "total_by_period": True}
    assert client.get("/test/operations").get_json()["total_by_category"] is False

    response = client.post("/test/operations", json={"operation": "total_by_category", "enabled": True})
    assert response.get_json()["total_by_category"] is True


@pytest.mark.parametrize("body", [
    {"operation": "not_a_real_operation", "enabled": False},
    {"operation": "total"},
    {"enabled": False},
    {"operation": "total", "enabled": "false"},
])
def test_toggle_rejects_invalid_payloads(client, monkeypatch, body):
    monkeypatch.setenv("ENABLE_TEST_CONTROLS", "1")
    response = client.post("/test/operations", json=body)
    assert response.status_code in (400, 422)


def test_disabled_operation_is_really_refused(application, monkeypatch):
    monkeypatch.setenv("ENABLE_TEST_CONTROLS", "1")
    test_controls.set_operation_enabled("total_by_category", False)
    run_calculators = Mock()
    monkeypatch.setattr("app.verification.run_calculators", run_calculators)

    outcome = verify_expenses(application.config["DATABASE_PATH"], {
        "operation": "total_by_category", "category": "Alimentation",
        "start_date": None, "end_date": None,
    })

    run_calculators.assert_not_called()
    assert outcome["tool_ok"] is False
    assert outcome["tool_error"]["code"] == "operation_disabled"
    assert outcome["comparison"]["status"] == "divergence"


def test_disabled_operation_is_still_refused_off_by_default(application, monkeypatch):
    """Without ENABLE_TEST_CONTROLS, disabling has no effect: production is unaffected."""
    monkeypatch.delenv("ENABLE_TEST_CONTROLS", raising=False)
    test_controls._disabled_operations.add("total_by_category")  # simulate leftover state
    run_calculators_result = ({"ok": True, "value": {"result_cents": 0, "expense_ids": [], "duration_ms": 1}},) * 2
    monkeypatch.setattr("app.verification.run_calculators", lambda *a: run_calculators_result)

    outcome = verify_expenses(application.config["DATABASE_PATH"], {
        "operation": "total_by_category", "category": "Alimentation",
        "start_date": None, "end_date": None,
    })
    assert outcome["tool_ok"] is True


def test_tool_description_warns_about_disabled_operation(monkeypatch):
    """The enum keeps all operations (a truncated enum makes a model that
    still needs one improvise a broken workaround instead of getting a clean
    operation_disabled refusal) - only the description warns Claude, and the
    backend remains the sole real enforcement point."""
    monkeypatch.setenv("ENABLE_TEST_CONTROLS", "1")
    test_controls.set_operation_enabled("total_by_category", False)
    tool = verify_expenses_tool()
    assert set(tool["input_schema"]["properties"]["operation"]["enum"]) == {
        "total", "total_by_category", "total_by_period",
    }
    assert "total_by_category" in tool["description"]


def test_tool_description_unaffected_when_test_mode_off(monkeypatch):
    monkeypatch.delenv("ENABLE_TEST_CONTROLS", raising=False)
    test_controls._disabled_operations.add("total_by_category")
    tool = verify_expenses_tool()
    assert "desactiv" not in tool["description"]

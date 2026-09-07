import pytest

from app.calculation_request import build_calculation_request
from app.calculators.python_calc import calculate_python
from app.calculators.sql_calc import calculate_sql
from app.comparator import compare_results
from app.models import ValidationError, parse_amount_to_cents


@pytest.mark.parametrize("raw,cents", [("42.50", 4250), ("42,50", 4250), ("42.5", 4250), ("0.29", 29), ("12", 1200), ("0", 0), (" 18 € ", 1800)])
def test_exact_cents(raw, cents):
    assert parse_amount_to_cents(raw) == cents


@pytest.mark.parametrize("raw", ["", "nan", "NaN", "Infinity", "-1", "1.001", "1e2", "abc", "1_000", "90071992547409.92", None, 42.5])
def test_invalid_money(raw):
    with pytest.raises(ValidationError):
        parse_amount_to_cents(raw)


@pytest.mark.parametrize("start,end", [("2026-99-99", "2026-12-31"), ("2026-02-29", "2026-03-01"), ("2026-09-07", "2026-09-01"), (123, "2026-09-01")])
def test_real_dates(start, end):
    with pytest.raises(ValidationError):
        build_calculation_request({"operation": "total_by_period", "start_date": start, "end_date": end})


@pytest.mark.parametrize("payload", [{"operation": "total", "sql": "DROP TABLE expenses"}, {"operation": "total_by_category", "category": " "}, {"operation": []}, []])
def test_unknown_or_invalid_parameters(payload):
    with pytest.raises(ValidationError):
        build_calculation_request(payload)


@pytest.mark.parametrize("calculator", [calculate_python, calculate_sql])
def test_invalid_operation_on_empty_database(application, calculator):
    result = calculator(application.config["DATABASE_PATH"], {"operation": "unknown"})
    assert result["ok"] is False


def test_malformed_tools_cannot_concord():
    for result in ({"ok": True, "value": {}}, {"ok": False}, None):
        assert compare_results(result, result)["status"] == "divergence"

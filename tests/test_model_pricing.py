"""Exact token billing, with no text tokenisation and no floating point prices."""
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from app.model_pricing import MODEL_PRICING, RequestUsage


def test_single_response_has_exact_decimal_string():
    usage = RequestUsage("claude-sonnet-5", model_calls=1)
    usage.record(SimpleNamespace(input_tokens=100, output_tokens=20))
    result = usage.snapshot()
    assert result["cost"] == {"amount": "0.00040000", "currency": "USD"}
    assert type(result["cost"]["amount"]) is str
    assert all(type(rate) is Decimal for rate in MODEL_PRICING[usage.model].values())
    assert result["metrics"]["total_tokens"] == 120
    assert result["metrics"]["cache_read_input_tokens"] == 0
    assert result["metrics"]["cache_creation_input_tokens"] == 0


def test_decimal_context_and_snapshot_are_independent():
    usage = RequestUsage("claude-sonnet-5", model_calls=1)
    usage.record({"input_tokens": 123456789, "output_tokens": 987654321})
    with localcontext() as context:
        context.prec = 3
        first = usage.snapshot()
    assert first["cost"]["amount"] == "10123.45678800"
    first["metrics"]["input_tokens"] = -1
    assert usage.snapshot()["metrics"]["input_tokens"] == 123456789


def test_cache_ttls_and_reads_never_double_count_creation():
    usage = RequestUsage("claude-sonnet-5", model_calls=1)
    usage.record({"input_tokens": 100, "output_tokens": 20,
                  "cache_read_input_tokens": 50, "cache_creation_input_tokens": 70,
                  "cache_creation": {"ephemeral_5m_input_tokens": 30, "ephemeral_1h_input_tokens": 40}})
    result = usage.snapshot()
    # (100*2 + 20*10 + 50*.20 + 30*2.50 + 40*4) / 1_000_000
    assert result["cost"]["amount"] == "0.00064500"
    assert result["metrics"]["input_tokens"] == 100  # standard input, as in Anthropic usage
    assert result["metrics"]["total_tokens"] == 120
    assert result["metrics"]["cache_creation_input_tokens"] == 70


def test_cache_legacy_total_uses_default_five_minute_ttl():
    usage = RequestUsage("claude-sonnet-5", model_calls=1)
    usage.record({"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 100})
    assert usage.snapshot()["cost"]["amount"] == "0.00025000"
    assert usage.snapshot()["metrics"]["cache_creation_1h_input_tokens"] == 0


@pytest.mark.parametrize("detail", [
    {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 40},
    {"ephemeral_5m_input_tokens": 70},
    {"ephemeral_5m_input_tokens": -1, "ephemeral_1h_input_tokens": 71},
])
def test_inconsistent_cache_never_gets_a_guessed_cost(detail):
    usage = RequestUsage("claude-sonnet-5", model_calls=1)
    usage.record({"input_tokens": 100, "output_tokens": 20,
                  "cache_creation_input_tokens": 70, "cache_creation": detail})
    assert usage.snapshot()["cost"] is None
    assert usage.snapshot()["usage_complete"] is False
    assert usage.snapshot()["metrics"]["input_tokens"] == 100


@pytest.mark.parametrize("value", [None, -1, True, "100", 1.5])
def test_invalid_required_usage_is_not_replaced_with_zero(value):
    usage = RequestUsage("claude-sonnet-5", model_calls=1)
    usage.record({"input_tokens": value, "output_tokens": 20})
    assert usage.snapshot()["cost"] is None
    assert usage.snapshot()["metrics"]["input_tokens"] is None
    assert usage.snapshot()["metrics"]["output_tokens"] == 20
    assert usage.snapshot()["metrics"]["total_tokens"] is None


def test_unknown_model_keeps_usage_without_pricing_guess():
    usage = RequestUsage("not-a-supported-model", model_calls=1)
    usage.record({"input_tokens": 100, "output_tokens": 20})
    assert usage.snapshot()["metrics"]["total_tokens"] == 120
    assert usage.snapshot()["cost"] is None


@pytest.mark.parametrize('model, expected', [
    ('claude-opus-5', '0.00161250'),
    ('claude-haiku-4-5', '0.00032250'),
])
def test_models_from_dev_keep_decimal_pricing_and_cache(model, expected):
    usage = RequestUsage(model, model_calls=1)
    usage.record({'input_tokens': 100, 'output_tokens': 20,
                  'cache_read_input_tokens': 50, 'cache_creation_input_tokens': 70,
                  'cache_creation': {'ephemeral_5m_input_tokens': 30, 'ephemeral_1h_input_tokens': 40}})
    assert usage.snapshot()['cost'] == {'amount': expected, 'currency': 'USD'}
    assert all(type(rate) is Decimal for rate in MODEL_PRICING[model].values())

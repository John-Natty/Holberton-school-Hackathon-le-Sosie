import pytest

from app.llm import LLMError, parse_question


def test_sdk_and_configurable_model(claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "configured-model")
    assert parse_question("Combien au total ?")["operation"] == "total_by_category"
    assert claude["calls"][0]["model"] == "configured-model"


@pytest.mark.parametrize("change", [{"text": "not JSON"}, {"text": "[]"}, {"stop_reason": "max_tokens"}, {"stop_reason": "refusal"}, {"status": 401}])
def test_unusable_llm_response(claude, change):
    claude.update(change)
    with pytest.raises(LLMError) as failure:
        parse_question("question")
    assert "external private details" not in str(failure.value)

"""
Tests unitaires de llm_json — garde JSON (lot 1, changement A).
Aucun réseau, aucun appel API Anthropic réel : client.messages.create est
entièrement mocké.
"""
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent


class _FakeResponse:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.content = [SimpleNamespace(text=text)]
        self.stop_reason = stop_reason


class _FakeAnthropicClient:
    """Simule client.messages.create() ; compte les appels."""

    def __init__(self, response: _FakeResponse):
        self._response = response
        self.call_count = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.call_count += 1
        return self._response


def test_llm_json_reponse_non_json_leve_llmresponseerror(monkeypatch):
    fake_client = _FakeAnthropicClient(_FakeResponse("ceci n'est pas du JSON"))
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)

    with pytest.raises(agent.LLMResponseError):
        agent.llm_json([{"role": "user", "content": "test"}], system="system de test")

    assert fake_client.call_count == 1  # aucun nouvel appel API (option a)


def test_llm_json_reponse_tronquee_max_tokens_log_sans_contenu(monkeypatch, caplog):
    secret_content = "TEXTE_DE_REPONSE_A_NE_JAMAIS_LOGGUER"
    fake_client = _FakeAnthropicClient(
        _FakeResponse('{"incomplet": ' + secret_content, stop_reason="max_tokens")
    )
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)

    with caplog.at_level(logging.WARNING, logger="agent"):
        with pytest.raises(agent.LLMResponseError):
            agent.llm_json([{"role": "user", "content": "test"}], system="system de test")

    assert fake_client.call_count == 1
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warning_records) == 1
    message = warning_records[0].getMessage()
    assert "max_tokens" in message  # stop_reason présent
    assert secret_content not in message  # jamais le contenu de la réponse


def test_llm_json_nettoie_les_balises_markdown_json(monkeypatch):
    fake_client = _FakeAnthropicClient(_FakeResponse('```json\n{"a": 1}\n```'))
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)

    result = agent.llm_json([{"role": "user", "content": "test"}], system="system de test")

    assert result == {"a": 1}
    assert fake_client.call_count == 1

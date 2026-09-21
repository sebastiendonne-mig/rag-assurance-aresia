"""
Tests unitaires de get_anthropic() — timeout/max_retries (lot 1, changement B).
Aucun appel réseau : on inspecte seulement les attributs du client construit,
jamais .messages.create(). Clé factice, jamais affichée, jamais utilisée pour
un vrai appel.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent


@pytest.fixture(autouse=True)
def _reset_anthropic_client_cache(monkeypatch):
    """Isole chaque test : force une reconstruction du client (singleton sinon)."""
    monkeypatch.setattr(agent, "_anthropic_client", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-not-a-real-key")
    yield
    monkeypatch.setattr(agent, "_anthropic_client", None)


def test_get_anthropic_expose_le_timeout_attendu():
    client = agent.get_anthropic()

    assert client.timeout == agent.ANTHROPIC_TIMEOUT
    assert client.timeout.connect == 5.0
    assert client.timeout.read == 60.0
    assert client.timeout.write == 60.0
    assert client.timeout.pool == 60.0


def test_get_anthropic_expose_le_max_retries_attendu():
    client = agent.get_anthropic()

    assert client.max_retries == 1


def test_get_anthropic_reste_un_singleton():
    client1 = agent.get_anthropic()
    client2 = agent.get_anthropic()

    assert client1 is client2

"""
Tests unitaires de l'agrégation d'usage par question (lot 1, sous-lot 1.2,
changement C). Aucun réseau, aucun appel API Anthropic réel, aucune clé.
"""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, text: str, input_tokens: int = 0, output_tokens: int = 0, stop_reason: str = "end_turn"):
        self.content = [SimpleNamespace(text=text)]
        self.stop_reason = stop_reason
        self.usage = _FakeUsage(input_tokens, output_tokens)


class _QueueAnthropicClient:
    """Renvoie les réponses de la file dans l'ordre, une par appel."""

    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.call_count = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        response = self._responses[self.call_count]
        self.call_count += 1
        return response


@pytest.fixture(autouse=True)
def _reset_usage_ctx():
    """Isole chaque test : le ContextVar ne doit jamais fuiter d'un test à l'autre."""
    token = agent._usage_ctx.set(None)
    yield
    agent._usage_ctx.reset(token)


# ─────────────────────────────────────────────
# Agrégation simple
# ─────────────────────────────────────────────

def test_agregation_sur_plusieurs_appels(monkeypatch):
    fake_client = _QueueAnthropicClient([
        _FakeResponse('{"a": 1}', input_tokens=100, output_tokens=10),
        _FakeResponse('reponse texte', input_tokens=200, output_tokens=50),
    ])
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)

    tracker = agent.UsageTracker()
    token = agent._usage_ctx.set(tracker)
    try:
        agent.llm_json([{"role": "user", "content": "q1"}], system="s")
        agent.llm_call([{"role": "user", "content": "q2"}])
    finally:
        agent._usage_ctx.reset(token)

    assert tracker.n_appels == 2
    assert tracker.tokens_in == 300
    assert tracker.tokens_out == 60


def test_pas_de_tracker_hors_run_agent_ne_plante_pas(monkeypatch):
    # _usage_ctx est None par défaut (fixture) : ne doit lever aucune erreur.
    fake_client = _QueueAnthropicClient([_FakeResponse('{"a": 1}', input_tokens=1, output_tokens=1)])
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)

    result = agent.llm_json([{"role": "user", "content": "q"}], system="s")

    assert result == {"a": 1}


def test_json_invalide_compte_quand_meme_les_tokens(monkeypatch):
    fake_client = _QueueAnthropicClient([
        _FakeResponse("pas du json", input_tokens=42, output_tokens=7, stop_reason="max_tokens"),
    ])
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)

    tracker = agent.UsageTracker()
    token = agent._usage_ctx.set(tracker)
    try:
        with pytest.raises(agent.LLMResponseError):
            agent.llm_json([{"role": "user", "content": "q"}], system="s")
    finally:
        agent._usage_ctx.reset(token)

    assert tracker.n_appels == 1
    assert tracker.tokens_in == 42
    assert tracker.tokens_out == 7


def test_reponse_sans_usage_ne_plante_pas(monkeypatch, caplog):
    import logging

    class _NoUsageResponse:
        def __init__(self, text):
            self.content = [SimpleNamespace(text=text)]

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: _NoUsageResponse("texte")))
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)

    tracker = agent.UsageTracker()
    token = agent._usage_ctx.set(tracker)
    try:
        with caplog.at_level(logging.WARNING, logger="agent"):
            result = agent.llm_call([{"role": "user", "content": "q"}])
    finally:
        agent._usage_ctx.reset(token)

    assert result == "texte"
    assert tracker.n_appels == 0  # pas comptabilisé, mais pas d'exception


# ─────────────────────────────────────────────
# Calcul de coût — test pur
# ─────────────────────────────────────────────

def test_estimer_cout_usd_valeurs_connues():
    # 1 000 000 tokens entrée + 1 000 000 tokens sortie -> 3$ + 15$ = 18$
    assert agent.estimer_cout_usd(1_000_000, 1_000_000) == pytest.approx(18.0)
    assert agent.estimer_cout_usd(0, 0) == 0.0
    # 500 000 entrée (1.5$) + 200 000 sortie (3.0$) = 4.5$
    assert agent.estimer_cout_usd(500_000, 200_000) == pytest.approx(4.5)


# ─────────────────────────────────────────────
# Intégration : vrai graphe compilé, LLM mocké, retrieval neutralisé
# ─────────────────────────────────────────────

_FAKE_CHUNK = {
    "text": "Article 1 — Texte de test suffisamment long pour le pipeline.",
    "metadata": {
        "source_doc": "DOC-TEST",
        "version": "1.0",
        "titre_humain": "Document de test",
        "chapitre_titre": "",
        "article_num": "1",
    },
}


def test_integration_graphe_reel_usage_non_nul(monkeypatch):
    """
    Fait tourner le VRAI graphe compilé (get_graph/build_graph), avec
    client.messages.create mocké et retrieve_chunks neutralisé (pas de vrai
    Chroma/embedding). Vérifie que n_appels et les tokens ne sont pas à zéro.
    """
    fake_client = _QueueAnthropicClient([
        _FakeResponse('{"multi_composantes": false, "raison": "test"}', input_tokens=50, output_tokens=20),
        _FakeResponse('{"suffisant": true, "raison": "ok"}', input_tokens=100, output_tokens=15),
        _FakeResponse("Réponse finale de test.", input_tokens=200, output_tokens=80),
    ])
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_client)
    monkeypatch.setattr(agent, "retrieve_chunks", lambda *a, **k: [_FAKE_CHUNK])
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 100)
    monkeypatch.setattr(agent, "_daily_count", 0)
    monkeypatch.setattr(agent, "_daily_date", None)

    result = agent.run_agent("Question de test ?")

    usage = result["usage"]
    assert usage["n_appels"] == 3, "comptage perdu dans les nœuds du graphe — voir usage réel : " + repr(usage)
    assert usage["tokens_in"] == 350
    assert usage["tokens_out"] == 115
    assert usage["latence_s"] >= 0
    assert usage["cout_usd"] == pytest.approx(agent.estimer_cout_usd(350, 115))
    assert fake_client.call_count == 3


# ─────────────────────────────────────────────
# Deux exécutions concurrentes
# ─────────────────────────────────────────────

class _PerThreadQueueClient:
    """
    Un SEUL client partagé entre les deux threads (installé une seule fois,
    avant leur démarrage — jamais de réassignation concurrente de
    agent.get_anthropic), mais qui sert une file de réponses différente par
    thread appelant (dispatch sur threading.get_ident()). Modélise fidèlement
    le cas réel : un seul get_anthropic() partagé par process, appelé
    concurremment par plusieurs sessions.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queues: dict[int, list] = {}
        self._counts: dict[int, int] = {}
        self.messages = SimpleNamespace(create=self._create)

    def register(self, responses: list) -> None:
        tid = threading.get_ident()
        self._queues[tid] = responses
        self._counts[tid] = 0

    def _create(self, **kwargs):
        tid = threading.get_ident()
        with self._lock:
            idx = self._counts[tid]
            self._counts[tid] += 1
        return self._queues[tid][idx]


def test_deux_run_agent_concurrents_ne_melangent_pas_les_totaux(monkeypatch):
    monkeypatch.setattr(agent, "retrieve_chunks", lambda *a, **k: [_FAKE_CHUNK])
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 1000)
    monkeypatch.setattr(agent, "_daily_count", 0)
    monkeypatch.setattr(agent, "_daily_date", None)

    shared_client = _PerThreadQueueClient()
    monkeypatch.setattr(agent, "get_anthropic", lambda: shared_client)

    results = {}
    barrier = threading.Barrier(2)  # force le chevauchement des deux exécutions

    def worker(name, tokens_value):
        shared_client.register([
            _FakeResponse('{"multi_composantes": false, "raison": "t"}', input_tokens=tokens_value, output_tokens=1),
            _FakeResponse('{"suffisant": true, "raison": "ok"}', input_tokens=tokens_value, output_tokens=1),
            _FakeResponse("reponse", input_tokens=tokens_value, output_tokens=1),
        ])
        barrier.wait()
        results[name] = agent.run_agent(f"Question {name}")

    t1 = threading.Thread(target=worker, args=("A", 1000))
    t2 = threading.Thread(target=worker, args=("B", 2000))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    usage_a = results["A"]["usage"]
    usage_b = results["B"]["usage"]
    assert usage_a["n_appels"] == 3
    assert usage_b["n_appels"] == 3
    assert usage_a["tokens_in"] == 3000  # 3 appels x 1000, jamais mélangé avec B
    assert usage_b["tokens_in"] == 6000  # 3 appels x 2000, jamais mélangé avec A

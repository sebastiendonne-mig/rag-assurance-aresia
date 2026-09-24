"""
Tests unitaires du disjoncteur des comparaisons (lot 3.1).
Vérifie surtout son indépendance vis-à-vis du disjoncteur du mode corpus.
Aucun réseau, aucune clé, aucun appel API réel.
"""
import sys
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent


@pytest.fixture(autouse=True)
def _reset_compteurs():
    """Isole chaque test : les DEUX compteurs remis à zéro avant et après."""
    agent._comparison_count = 0
    agent._comparison_date = None
    agent._daily_count = 0
    agent._daily_date = None
    yield
    agent._comparison_count = 0
    agent._comparison_date = None
    agent._daily_count = 0
    agent._daily_date = None


def test_autorise_sous_le_seuil(monkeypatch):
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 3)
    agent._check_comparison_daily_limit()
    agent._check_comparison_daily_limit()
    agent._check_comparison_daily_limit()
    assert agent._comparison_count == 3


def test_leve_au_seuil(monkeypatch):
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 2)
    agent._check_comparison_daily_limit()
    agent._check_comparison_daily_limit()
    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        agent._check_comparison_daily_limit()


def test_seuil_par_defaut_est_50():
    """50 comparaisons = 100 appels LLM par jour au plafond par défaut."""
    assert agent.COMPARISON_DAILY_LIMIT == 50


def test_bloque_a_50_par_defaut(monkeypatch):
    for _ in range(50):
        agent._check_comparison_daily_limit()
    assert agent._comparison_count == 50
    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        agent._check_comparison_daily_limit()


# ─────────────────────────────────────────────
# Indépendance des deux disjoncteurs
# ─────────────────────────────────────────────

def test_comparaisons_ne_touchent_pas_le_compteur_corpus(monkeypatch):
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 5)
    for _ in range(5):
        agent._check_comparison_daily_limit()
    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        agent._check_comparison_daily_limit()

    assert agent._comparison_count == 5
    # Le disjoncteur du mode corpus n'a jamais bougé.
    assert agent._daily_count == 0
    assert agent._daily_date is None


def test_corpus_ne_touche_pas_le_compteur_comparaisons(monkeypatch):
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 4)
    for _ in range(4):
        agent._check_daily_limit()

    assert agent._daily_count == 4
    assert agent._comparison_count == 0
    assert agent._comparison_date is None


def test_comparaisons_saturees_laissent_passer_le_corpus(monkeypatch):
    """Comparaison épuisée : les questions normales restent disponibles."""
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 1)
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 10)
    agent._check_comparison_daily_limit()
    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        agent._check_comparison_daily_limit()

    agent._check_daily_limit()  # ne doit pas lever
    assert agent._daily_count == 1


# ─────────────────────────────────────────────
# Bascule de journée UTC
# ─────────────────────────────────────────────

def test_rollover_journee_utc(monkeypatch):
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 2)

    class _FakeDatetime:
        courant = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.courant

    monkeypatch.setattr(agent, "datetime", _FakeDatetime)

    agent._check_comparison_daily_limit()
    agent._check_comparison_daily_limit()
    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        agent._check_comparison_daily_limit()

    _FakeDatetime.courant = datetime(2026, 9, 25, 0, 1, tzinfo=timezone.utc)
    agent._check_comparison_daily_limit()  # nouvelle journée : repart à zéro
    assert agent._comparison_count == 1
    assert agent._comparison_date == date(2026, 9, 25)


# ─────────────────────────────────────────────
# Thread-safety
# ─────────────────────────────────────────────

def test_thread_safe(monkeypatch):
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 50)
    n_threads = 200
    accepted: list[int] = []
    rejected: list[int] = []
    verrou = threading.Lock()

    def worker():
        try:
            agent._check_comparison_daily_limit()
        except agent.ComparisonDailyLimitExceeded:
            with verrou:
                rejected.append(1)
        else:
            with verrou:
                accepted.append(1)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(accepted) == 50
    assert len(rejected) == n_threads - 50
    assert agent._comparison_count == 50


# ─────────────────────────────────────────────
# Message visiteur
# ─────────────────────────────────────────────

def test_message_neutre_dedie():
    message = agent.format_user_error(agent.ComparisonDailyLimitExceeded("peu importe"))
    assert "comparaison" in message.lower()
    assert "questions normales restent disponibles" in message


def test_message_corpus_inchange():
    """Le message du disjoncteur du lot 0 n'est pas modifié."""
    message = agent.format_user_error(agent.DailyLimitExceeded("peu importe"))
    assert message == (
        "Le service a atteint sa limite d'usage pour aujourd'hui. Merci de revenir demain."
    )

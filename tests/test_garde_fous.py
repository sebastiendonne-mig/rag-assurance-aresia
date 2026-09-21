"""
Tests unitaires des garde-fous du lot 0 (assur2).
Aucun appel réseau, aucun appel API Anthropic — uniquement de la logique locale.
"""
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent


@pytest.fixture(autouse=True)
def _reset_daily_counter():
    """Isole chaque test : remet le compteur global à zéro avant et après."""
    agent._daily_count = 0
    agent._daily_date = None
    yield
    agent._daily_count = 0
    agent._daily_date = None


# ─────────────────────────────────────────────
# exceeds_max_length
# ─────────────────────────────────────────────

def test_exceeds_max_length_sous_la_limite():
    assert agent.exceeds_max_length("bonjour", 500) is False


def test_exceeds_max_length_exactement_a_la_limite():
    assert agent.exceeds_max_length("a" * 500, 500) is False


def test_exceeds_max_length_au_dessus_de_la_limite():
    assert agent.exceeds_max_length("a" * 501, 500) is True


# ─────────────────────────────────────────────
# format_user_error
# ─────────────────────────────────────────────

def test_format_user_error_ne_contient_jamais_le_message_brut():
    secret_message = "SECRET_INTERNAL_DETAIL_sk-ant-fake-1234"
    exc = ValueError(secret_message)
    msg = agent.format_user_error(exc)
    assert secret_message not in msg
    assert "sk-ant" not in msg


def test_format_user_error_generique():
    msg = agent.format_user_error(RuntimeError("boom"))
    assert msg == "Une erreur technique est survenue. Merci de réessayer dans quelques instants."


def test_format_user_error_daily_limit():
    msg = agent.format_user_error(agent.DailyLimitExceeded("limite atteinte"))
    assert "limite" in msg.lower()
    assert "demain" in msg.lower()


# ─────────────────────────────────────────────
# _check_daily_limit — seuil
# ─────────────────────────────────────────────

def test_daily_limit_autorise_sous_le_seuil(monkeypatch):
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 3)
    agent._check_daily_limit()
    agent._check_daily_limit()
    agent._check_daily_limit()
    assert agent._daily_count == 3


def test_daily_limit_leve_au_seuil(monkeypatch):
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 2)
    agent._check_daily_limit()
    agent._check_daily_limit()
    with pytest.raises(agent.DailyLimitExceeded):
        agent._check_daily_limit()


# ─────────────────────────────────────────────
# _check_daily_limit — changement de jour
# ─────────────────────────────────────────────

def test_daily_limit_remis_a_zero_au_changement_de_jour(monkeypatch):
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 1)

    class _FixedDateTime:
        _current = date(2026, 9, 21)

        @classmethod
        def now(cls, tz=None):
            import datetime as _dt
            return _dt.datetime(cls._current.year, cls._current.month, cls._current.day, tzinfo=tz)

    monkeypatch.setattr(agent, "datetime", _FixedDateTime)

    agent._check_daily_limit()
    with pytest.raises(agent.DailyLimitExceeded):
        agent._check_daily_limit()

    _FixedDateTime._current = date(2026, 9, 22)
    agent._check_daily_limit()  # ne doit PAS lever : nouveau jour, compteur remis à zéro
    assert agent._daily_count == 1


# ─────────────────────────────────────────────
# _check_daily_limit — concurrence
# ─────────────────────────────────────────────

def test_daily_limit_thread_safe(monkeypatch):
    monkeypatch.setattr(agent, "DAILY_QUESTION_LIMIT", 50)
    n_threads = 200
    accepted = []
    rejected = []
    lock = threading.Lock()

    def worker():
        try:
            agent._check_daily_limit()
            with lock:
                accepted.append(1)
        except agent.DailyLimitExceeded:
            with lock:
                rejected.append(1)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Le compteur ne doit jamais dépasser la limite, même sous concurrence.
    assert len(accepted) == 50
    assert len(rejected) == n_threads - 50
    assert agent._daily_count == 50

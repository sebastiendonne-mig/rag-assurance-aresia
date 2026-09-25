"""
Tests unitaires de agent.configure_stdout_logging (lot 0, commit 13).
Aucun réseau, aucun appel API Anthropic.
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent


def _clear_handlers():
    for name in ("streamlit_app", "agent", "upload_session"):
        logging.getLogger(name).handlers.clear()


@pytest.fixture(autouse=True)
def _reset_logging_handlers():
    """
    Isole chaque test : les loggers nommés ne gardent aucun handler d'un test à
    l'autre, et la garde "une fois par processus" du warning de tarif Mistral
    est remise à zéro (sinon l'ordre d'exécution des tests deviendrait
    significatif).
    """
    _clear_handlers()
    agent._tarif_warning_emis = False
    yield
    _clear_handlers()
    agent._tarif_warning_emis = False


def test_error_atteint_stdout(capsys):
    agent.configure_stdout_logging()
    logger = logging.getLogger("agent")
    logger.setLevel(logging.INFO)

    logger.error("MESSAGE_ERROR_TEST")

    captured = capsys.readouterr()
    assert "MESSAGE_ERROR_TEST" in captured.out


def test_info_natteint_pas_stdout(capsys):
    agent.configure_stdout_logging()
    logger = logging.getLogger("agent")
    logger.setLevel(logging.INFO)  # sans ça, l'INFO serait filtré avant même le handler

    logger.info("MESSAGE_INFO_TEST")

    captured = capsys.readouterr()
    assert "MESSAGE_INFO_TEST" not in captured.out
    assert captured.out == ""


def test_idempotent_pas_de_handler_duplique():
    agent.configure_stdout_logging()
    agent.configure_stdout_logging()
    agent.configure_stdout_logging()

    for logger_name in ("streamlit_app", "agent"):
        logger = logging.getLogger(logger_name)
        count = sum(1 for h in logger.handlers if h.name == "stdout_warning_handler")
        assert count == 1, f"{logger_name} a {count} handler(s) stdout_warning_handler, attendu 1"


def test_attache_bien_les_deux_loggers_nommes_pas_root():
    root_handlers_before = list(logging.root.handlers)

    agent.configure_stdout_logging()

    assert logging.root.handlers == root_handlers_before  # root non modifié
    for logger_name in ("streamlit_app", "agent"):
        logger = logging.getLogger(logger_name)
        assert any(h.name == "stdout_warning_handler" for h in logger.handlers)



# ─────────────────────────────────────────────
# Warning unique : modèle Mistral non tarifé (sous-lot 3.1b)
# ─────────────────────────────────────────────

def _lignes_tarif(sortie: str) -> list[str]:
    return [ligne for ligne in sortie.splitlines() if "TARIF_MISTRAL" in ligne]


def test_warning_tarif_emis_une_fois_pour_un_modele_non_tarife(monkeypatch, capsys):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "autre-modele")

    agent.configure_stdout_logging()

    lignes = _lignes_tarif(capsys.readouterr().out)
    assert len(lignes) == 1
    assert "WARNING" in lignes[0]
    assert "modele_non_tarife=autre-modele" in lignes[0]


def test_warning_tarif_pas_de_doublon_aux_reruns_streamlit(monkeypatch, capsys):
    """configure_stdout_logging() est ré-exécutée à chaque rerun : un seul warning."""
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "autre-modele")

    agent.configure_stdout_logging()
    agent.configure_stdout_logging()
    agent.configure_stdout_logging()

    assert len(_lignes_tarif(capsys.readouterr().out)) == 1


def test_warning_tarif_ne_contient_que_le_nom_du_modele(monkeypatch, capsys):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "autre-modele")
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-factice-jamais-affichee")

    agent.configure_stdout_logging()

    ligne = _lignes_tarif(capsys.readouterr().out)[0]
    assert ligne.endswith("TARIF_MISTRAL modele_non_tarife=autre-modele")
    assert "cle-factice" not in ligne


def test_pas_de_warning_pour_le_modele_tarife(monkeypatch, capsys):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", agent.MISTRAL_PRICED_MODEL)

    agent.configure_stdout_logging()

    assert _lignes_tarif(capsys.readouterr().out) == []


def test_pas_de_warning_si_le_modele_est_absent(monkeypatch, capsys):
    """Modèle absent : Mistral est déjà indisponible, rien à signaler."""
    monkeypatch.setattr(agent, "MISTRAL_MODEL", None)

    agent.configure_stdout_logging()

    assert _lignes_tarif(capsys.readouterr().out) == []


def test_pas_de_warning_si_le_modele_est_vide(monkeypatch, capsys):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "")

    agent.configure_stdout_logging()

    assert _lignes_tarif(capsys.readouterr().out) == []

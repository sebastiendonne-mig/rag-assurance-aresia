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
    for name in ("streamlit_app", "agent"):
        logging.getLogger(name).handlers.clear()


@pytest.fixture(autouse=True)
def _reset_logging_handlers():
    """Isole chaque test : les loggers nommés ne gardent aucun handler d'un test à l'autre."""
    _clear_handlers()
    yield
    _clear_handlers()


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

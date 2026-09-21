"""
Tests UI (streamlit.testing.v1.AppTest) pour le caption d'usage rattaché à
chaque réponse (lot 1, sous-lot 1.2). Aucun réseau, aucun appel API réel,
aucune clé, aucun chargement du modèle d'embeddings ou de Chroma : toutes
les dépendances lourdes de _warm_up() sont mockées via monkeypatch sur le
module agent, appliqué AVANT que app.py (exécuté par AppTest) ne fasse
`from agent import ...`.
"""
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent

APP_PATH = str(Path(__file__).parent.parent / "app.py")

_USAGE_Q1 = {
    "n_appels": 3,
    "tokens_in": 300,
    "tokens_out": 50,
    "latence_s": 1.23,
    "cout_usd": 0.0016,
}

_EXCEPTION_TEXT = "panne-reseau-secrete-jamais-affichee-au-visiteur"


class _FakeEmbedModel:
    def encode(self, *a, **k):
        raise AssertionError("get_embed_model ne doit jamais être appelé réellement dans ces tests")


class _FakeChromaCol:
    def query(self, *a, **k):
        raise AssertionError("get_chroma_col ne doit jamais être appelé réellement dans ces tests")


class _FakeAnthropicClient:
    """
    Client factice pour _warm_up() : volontairement AUCUN attribut `messages`,
    pour que toute tentative d'appel réel (client.messages.create(...)) échoue
    immédiatement avec une AttributeError plutôt que de risquer un appel réseau.
    """


@pytest.fixture(autouse=True)
def _clear_resource_cache():
    """
    Isole chaque test : _warm_up() est décoré @st.cache_resource dans app.py.
    Sans ce nettoyage avant ET après chaque test, les faux objets (embed
    model, chroma, client Anthropic) mis en cache par un test fuiteraient
    vers les tests suivants — ou un objet réel mis en cache par un run
    précédent fuiterait vers ce test.
    """
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture(autouse=True)
def _mock_heavy_deps(monkeypatch):
    """Neutralise les dépendances lourdes/réseau appelées par _warm_up()."""
    monkeypatch.setattr(agent, "get_embed_model", lambda: _FakeEmbedModel())
    monkeypatch.setattr(agent, "get_chroma_col", lambda: _FakeChromaCol())
    monkeypatch.setattr(agent, "get_anthropic", lambda: _FakeAnthropicClient())


def _make_success_state(reponse_text: str, usage: dict) -> dict:
    return {
        "question_originale": "peu importe pour ce test",
        "produit_filtre": None,
        "sous_questions": [],
        "resultats": [],
        "reponse_finale": reponse_text,
        "trace_log": [{"etape": "router", "decision": "react_simple"}],
        "usage": usage,
    }


def _run_two_questions(monkeypatch) -> AppTest:
    """
    Configure run_agent (mocké) pour répondre avec succès (usage connu) à la
    1re question, puis lever RuntimeError à la 2e. Lance les deux tours via
    AppTest et retourne l'app dans son état final.
    """
    outcomes = [
        _make_success_state("Réponse de test numéro 1.", _USAGE_Q1),
        RuntimeError(_EXCEPTION_TEXT),
    ]
    calls: list[str] = []

    def _fake_run_agent(question, *args, **kwargs):
        # run_agent(question: str, produit_filtre: str | None = None) : app.py
        # ne doit appeler qu'avec la question, en positionnel unique.
        assert isinstance(question, str), f"run_agent doit recevoir une chaîne, reçu {type(question)!r}"
        assert not args and not kwargs, (
            f"run_agent ne doit recevoir que la question (args={args!r}, kwargs={kwargs!r})"
        )
        calls.append(question)
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(agent, "run_agent", _fake_run_agent)

    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not at.exception, f"exception au chargement initial : {at.exception}"

    at.chat_input[0].set_value("Question 1").run()
    assert not at.exception, f"exception après question 1 : {at.exception}"

    at.chat_input[0].set_value("Question 2 qui échoue").run()
    assert not at.exception, f"exception après question 2 : {at.exception}"

    assert calls == ["Question 1", "Question 2 qui échoue"]
    return at


def _usage_captions(at: AppTest) -> list[str]:
    return [c.value for c in at.caption if c.value.startswith("⏱️")]


def test_usage_present_sur_succes_absent_sur_erreur(monkeypatch):
    at = _run_two_questions(monkeypatch)

    messages = at.session_state["messages"]
    assert len(messages) == 4  # user1, assistant1, user2, assistant2
    assert "usage" in messages[1]
    assert messages[1]["usage"] == _USAGE_Q1
    assert "usage" not in messages[3]


def test_un_seul_caption_usage_apres_question_1(monkeypatch):
    outcomes = [_make_success_state("Réponse de test numéro 1.", _USAGE_Q1)]

    def _fake_run_agent(question, *args, **kwargs):
        assert isinstance(question, str)
        assert not args and not kwargs
        return outcomes.pop(0)

    monkeypatch.setattr(agent, "run_agent", _fake_run_agent)

    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    at.chat_input[0].set_value("Question 1").run()
    assert not at.exception

    usage_captions = _usage_captions(at)
    assert len(usage_captions) == 1
    assert "estimation" in usage_captions[0]


def test_caption_usage_reste_unique_apres_question_en_erreur(monkeypatch):
    at = _run_two_questions(monkeypatch)

    # Toujours exactement un caption d'usage (celui de la question 1) : la
    # question 2, en erreur, ne doit en ajouter aucun.
    usage_captions = _usage_captions(at)
    assert len(usage_captions) == 1
    assert "estimation" in usage_captions[0]


def test_texte_brut_exception_absent_de_tout_affichage(monkeypatch):
    at = _run_two_questions(monkeypatch)

    displayed_markdown = " ".join(m.value for m in at.markdown)
    displayed_captions = " ".join(c.value for c in at.caption)
    assert _EXCEPTION_TEXT not in displayed_markdown
    assert _EXCEPTION_TEXT not in displayed_captions


def test_vider_conversation_reinitialise_messages_et_last_usage(monkeypatch):
    at = _run_two_questions(monkeypatch)
    assert at.session_state["messages"]

    # Force un last_usage non vide avant de vider, pour un test plus strict
    # (le dernier tour de _run_two_questions est une erreur, qui le laisse déjà à None).
    at.session_state["last_usage"] = _USAGE_Q1

    vider_buttons = [b for b in at.button if "Vider" in b.label]
    assert len(vider_buttons) == 1, "bouton « Vider la conversation » introuvable ou ambigu"
    vider_buttons[0].click().run()
    assert not at.exception

    assert at.session_state["messages"] == []
    assert at.session_state["last_usage"] is None

"""
Tests unitaires du mode comparaison sur le chemin upload (lot 3.1).
Aucun réseau, aucune clé, aucun appel API réel : llm_call est toujours
remplacé par un double.
"""
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent
import upload_session


class _FakeCollection:
    """Collection Chroma factice — retrieve_from_upload est mocké par-dessus."""


@pytest.fixture(autouse=True)
def _reset_etat():
    agent._comparison_count = 0
    agent._comparison_date = None
    agent._daily_count = 0
    agent._daily_date = None
    token = agent._usage_ctx.set(None)
    yield
    agent._usage_ctx.reset(token)
    agent._comparison_count = 0
    agent._comparison_date = None
    agent._daily_count = 0
    agent._daily_date = None


@pytest.fixture(autouse=True)
def _chunks_factices(monkeypatch):
    """Aucun embedding réel : le retrieval de l'upload est court-circuité."""
    monkeypatch.setattr(
        upload_session,
        "retrieve_from_upload",
        lambda collection, question, **kw: [
            {
                "text": "Article 4.1 — Franchise de 30 jours.",
                "metadata": {
                    "source_doc": "DOC-TEST",
                    "version": "2024",
                    "titre_humain": "Contrat test",
                    "chapitre_titre": "Garanties",
                    "article_num": "4.1",
                },
                "distance": 0.1,
            }
        ],
    )


@pytest.fixture(autouse=True)
def _mistral_configure(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "dummy-not-a-real-key")
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "fake-model-for-tests")


def _fake_llm(reponses: dict, appels: list | None = None, tokens: dict | None = None):
    """
    Double de llm_call : renvoie (ou lève) selon le moteur demandé, et
    alimente le tracker du ContextVar comme le ferait un vrai appel.
    """
    tokens = tokens or {}

    def _call(messages, system=None, engine=agent.ENGINE_ANTHROPIC):
        if appels is not None:
            appels.append(engine)
        tracker = agent._usage_ctx.get()
        if tracker is not None:
            tin, tout = tokens.get(engine, (0, 0))
            tracker.record_tokens(tin, tout)
        resultat = reponses[engine]
        if isinstance(resultat, Exception):
            raise resultat
        return resultat

    return _call


# ─────────────────────────────────────────────
# Cas nominal
# ─────────────────────────────────────────────

def test_renvoie_les_deux_moteurs_dans_l_ordre(monkeypatch):
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "réponse claude", agent.ENGINE_MISTRAL: "réponse mistral"}),
    )

    resultats = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert [r.engine for r in resultats] == [agent.ENGINE_ANTHROPIC, agent.ENGINE_MISTRAL]
    assert resultats[0].reponse == "réponse claude"
    assert resultats[1].reponse == "réponse mistral"
    assert all(r.succes for r in resultats)
    assert all(r.erreur is None for r in resultats)
    assert all(r.latence_s >= 0 for r in resultats)


def test_les_deux_moteurs_recoivent_le_meme_prompt(monkeypatch):
    prompts = {}

    def _call(messages, system=None, engine=agent.ENGINE_ANTHROPIC):
        prompts[engine] = messages[0]["content"]
        return "ok"

    monkeypatch.setattr(upload_session, "llm_call", _call)
    upload_session.compare_engines_on_upload(_FakeCollection(), "ma question")

    assert prompts[agent.ENGINE_ANTHROPIC] == prompts[agent.ENGINE_MISTRAL]
    assert "ma question" in prompts[agent.ENGINE_ANTHROPIC]


# ─────────────────────────────────────────────
# Isolation des échecs (décision 7)
# ─────────────────────────────────────────────

def test_mistral_en_echec_n_empeche_pas_anthropic(monkeypatch):
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({
            agent.ENGINE_ANTHROPIC: "réponse claude",
            agent.ENGINE_MISTRAL: RuntimeError("boom"),
        }),
    )

    anthropic_res, mistral_res = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert anthropic_res.succes is True
    assert anthropic_res.reponse == "réponse claude"
    assert mistral_res.succes is False
    assert mistral_res.reponse is None
    assert "Une erreur technique est survenue" in mistral_res.erreur
    assert "boom" not in mistral_res.erreur  # jamais str(exc) côté visiteur


def test_anthropic_en_echec_n_empeche_pas_mistral(monkeypatch):
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({
            agent.ENGINE_ANTHROPIC: RuntimeError("boom"),
            agent.ENGINE_MISTRAL: "réponse mistral",
        }),
    )

    anthropic_res, mistral_res = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert anthropic_res.succes is False
    assert "boom" not in anthropic_res.erreur
    assert mistral_res.succes is True
    assert mistral_res.reponse == "réponse mistral"


def test_les_deux_en_echec_restent_neutres(monkeypatch):
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({
            agent.ENGINE_ANTHROPIC: RuntimeError("boom A"),
            agent.ENGINE_MISTRAL: RuntimeError("boom M"),
        }),
    )

    resultats = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert not any(r.succes for r in resultats)
    for r in resultats:
        assert "boom" not in r.erreur


# ─────────────────────────────────────────────
# Isolation du coût par moteur, y compris en parallèle
# ─────────────────────────────────────────────

def test_cout_isole_par_moteur(monkeypatch):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", agent.MISTRAL_PRICED_MODEL)
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "eu")
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm(
            {agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"},
            tokens={
                agent.ENGINE_ANTHROPIC: (1_000_000, 1_000_000),
                agent.ENGINE_MISTRAL: (2_000_000, 2_000_000),
            },
        ),
    )

    anthropic_res, mistral_res = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    # Aucun mélange entre les deux trackers.
    assert (anthropic_res.tokens_in, anthropic_res.tokens_out) == (1_000_000, 1_000_000)
    assert (mistral_res.tokens_in, mistral_res.tokens_out) == (2_000_000, 2_000_000)
    assert anthropic_res.cout_usd == pytest.approx(3.0 + 15.0)
    # 2 M en entrée x 0.55 + 2 M en sortie x 1.65 (tarif catalogue x 1.1, endpoint UE).
    assert mistral_res.cout_usd == pytest.approx(2 * 0.55 + 2 * 1.65)


def test_cout_isole_meme_avec_appels_reellement_concurrents(monkeypatch):
    """
    Force le chevauchement réel des deux threads via une barrière : chaque
    moteur attend l'autre avant de comptabiliser, donc si les ContextVar
    fuyaient d'un thread à l'autre, les tokens se mélangeraient.
    """
    barriere = threading.Barrier(2, timeout=5)
    tokens = {
        agent.ENGINE_ANTHROPIC: (3_000, 300),
        agent.ENGINE_MISTRAL: (6_000, 600),
    }

    def _call(messages, system=None, engine=agent.ENGINE_ANTHROPIC):
        barriere.wait()
        tracker = agent._usage_ctx.get()
        tin, tout = tokens[engine]
        tracker.record_tokens(tin, tout)
        barriere.wait()
        return f"réponse {engine}"

    monkeypatch.setattr(upload_session, "llm_call", _call)

    anthropic_res, mistral_res = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert (anthropic_res.tokens_in, anthropic_res.tokens_out) == (3_000, 300)
    assert (mistral_res.tokens_in, mistral_res.tokens_out) == (6_000, 600)


def test_cout_mistral_non_disponible_pour_un_modele_non_tarife(monkeypatch):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "un-modele-non-tarife")
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm(
            {agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"},
            tokens={agent.ENGINE_MISTRAL: (100, 10), agent.ENGINE_ANTHROPIC: (100, 10)},
        ),
    )

    anthropic_res, mistral_res = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert mistral_res.cout_usd is None          # -> "non disponible" côté interface
    assert anthropic_res.cout_usd is not None    # le tarif Anthropic reste connu


def test_appels_en_parallele(monkeypatch):
    """La latence perçue est celle du plus lent, pas la somme des deux."""
    def _call(messages, system=None, engine=agent.ENGINE_ANTHROPIC):
        time.sleep(0.2)
        return "ok"

    monkeypatch.setattr(upload_session, "llm_call", _call)

    debut = time.monotonic()
    upload_session.compare_engines_on_upload(_FakeCollection(), "q")
    ecoule = time.monotonic() - debut

    assert ecoule < 0.35  # séquentiel donnerait >= 0.4s


# ─────────────────────────────────────────────
# Disjoncteur et disponibilité
# ─────────────────────────────────────────────

def test_disjoncteur_incremente_une_fois_par_comparaison(monkeypatch):
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"}),
    )

    upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert agent._comparison_count == 1   # 1 comparaison, pas 2 appels
    assert agent._daily_count == 0        # le compteur corpus n'a pas bougé


def test_disjoncteur_bloque_au_seuil(monkeypatch):
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 1)
    appels: list[str] = []
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"}, appels=appels),
    )

    upload_session.compare_engines_on_upload(_FakeCollection(), "q")
    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert len(appels) == 2  # aucun appel LLM pour la comparaison refusée


def test_cle_mistral_absente_replie_sur_claude_seul(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    appels: list[str] = []
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"}, appels=appels),
    )

    resultats = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert [r.engine for r in resultats] == [agent.ENGINE_ANTHROPIC]
    assert resultats[0].reponse == "a"
    assert appels == [agent.ENGINE_ANTHROPIC]  # aucun appel Mistral tenté
    assert agent._comparison_count == 1  # le repli compte dans le même quota


def test_modele_mistral_absent_replie_sur_claude_seul(monkeypatch):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "")
    appels: list[str] = []
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"}, appels=appels),
    )

    resultats = upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert [r.engine for r in resultats] == [agent.ENGINE_ANTHROPIC]
    assert appels == [agent.ENGINE_ANTHROPIC]


def test_repli_claude_seul_bloque_au_meme_seuil(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 1)
    appels: list[str] = []
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"}, appels=appels),
    )

    upload_session.compare_engines_on_upload(_FakeCollection(), "q")
    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert appels == [agent.ENGINE_ANTHROPIC]  # jamais de bascule silencieuse au-delà du quota


def test_ordre_disponibilite_puis_disjoncteur_puis_retrieval(monkeypatch):
    journal: list[str] = []
    dispo = agent.mistral_disponible
    limite = agent._check_comparison_daily_limit

    def _dispo():
        journal.append("disponibilite")
        return dispo()

    def _limite():
        journal.append("disjoncteur")
        return limite()

    def _retrieve(collection, question, **kw):
        journal.append("retrieval")
        return []

    monkeypatch.setattr(agent, "mistral_disponible", _dispo)
    monkeypatch.setattr(agent, "_check_comparison_daily_limit", _limite)
    monkeypatch.setattr(upload_session, "retrieve_from_upload", _retrieve)
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"}),
    )

    upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert journal == ["disponibilite", "disjoncteur", "retrieval"]


def test_quota_atteint_leve_avant_retrieval_et_appels(monkeypatch):
    monkeypatch.setattr(agent, "COMPARISON_DAILY_LIMIT", 0)
    journal: list[str] = []
    monkeypatch.setattr(
        upload_session,
        "retrieve_from_upload",
        lambda collection, question, **kw: journal.append("retrieval") or [],
    )
    monkeypatch.setattr(
        upload_session,
        "llm_call",
        _fake_llm({agent.ENGINE_ANTHROPIC: "a", agent.ENGINE_MISTRAL: "m"}, appels=journal),
    )

    with pytest.raises(agent.ComparisonDailyLimitExceeded):
        upload_session.compare_engines_on_upload(_FakeCollection(), "q")

    assert journal == []


def test_le_chemin_upload_simple_reste_inchange(monkeypatch):
    """
    Sans comparaison, answer_question_on_upload() appelle toujours un seul
    moteur, sans paramètre engine explicite : comportement du lot 2a.
    """
    vus = []

    def _call(messages, system=None, **kwargs):
        vus.append(kwargs)
        return "réponse"

    monkeypatch.setattr(upload_session, "llm_call", _call)

    assert upload_session.answer_question_on_upload(_FakeCollection(), "q") == "réponse"
    assert vus == [{}]              # aucun engine passé
    assert agent._comparison_count == 0  # ni disjoncteur de comparaison touché

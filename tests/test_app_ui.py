"""
Tests UI (streamlit.testing.v1.AppTest) pour le caption d'usage rattaché à
chaque réponse (lot 1, sous-lot 1.2). Aucun réseau, aucun appel API réel,
aucune clé, aucun chargement du modèle d'embeddings ou de Chroma : toutes
les dépendances lourdes de _warm_up() sont mockées via monkeypatch sur le
module agent, appliqué AVANT que app.py (exécuté par AppTest) ne fasse
`from agent import ...`.
"""
import ast
import re
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent
import upload_session

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def _extract_demo_questions() -> list[tuple[str, str]]:
    """
    Extrait _DEMO_QUESTIONS depuis app.py par analyse statique (ast), sans
    importer/exécuter le module — un import direct déclencherait _warm_up()
    (appelé sans condition au niveau module) avant que les fixtures de mock
    de ce fichier ne soient en place.
    """
    tree = ast.parse(Path(APP_PATH).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_DEMO_QUESTIONS" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("_DEMO_QUESTIONS introuvable dans app.py")


def _extract_warm_up_show_spinner() -> str:
    """
    Extrait la valeur de l'argument show_spinner du décorateur
    @st.cache_resource sur _warm_up(), par analyse statique (ast) — pas
    d'import du module, même raison que _extract_demo_questions().

    Préféré à un simple grep/regex sur le texte du fichier : ça évite tout
    faux positif si la chaîne attendue apparaissait ailleurs (commentaire,
    autre décorateur show_spinner comme ceux de _load_pdf_bytes/
    _load_svg_b64) et vérifie qu'on cible bien CE décorateur sur CETTE
    fonction, pas juste une occurrence de texte quelque part dans le fichier.
    """
    tree = ast.parse(Path(APP_PATH).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_warm_up":
            for deco in node.decorator_list:
                if (
                    isinstance(deco, ast.Call)
                    and isinstance(deco.func, ast.Attribute)
                    and deco.func.attr == "cache_resource"
                ):
                    for kw in deco.keywords:
                        if kw.arg == "show_spinner":
                            return ast.literal_eval(kw.value)
    raise AssertionError("show_spinner de @st.cache_resource sur _warm_up() introuvable dans app.py")


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


def test_pas_de_dollar_non_echappe_dans_rendu_apres_succes(monkeypatch):
    """
    Lot 1.3 changement A : les $ du tarif (caption + expander "Détail de
    l'estimation") doivent être échappés (\\$), sans quoi Streamlit les
    interprète comme des délimiteurs LaTeX (KaTeX) et casse l'affichage.

    Le contenu d'un st.expander est émis par le script à chaque run, qu'il
    soit visuellement déplié ou non côté navigateur (Expander est un simple
    conteneur dans l'arbre d'éléments d'AppTest) : pas besoin d'interaction
    pour que son contenu soit inspectable ici.
    """
    outcomes = [_make_success_state("Réponse de test numéro 1.", _USAGE_Q1)]

    def _fake_run_agent(question, *args, **kwargs):
        assert isinstance(question, str)
        assert not args and not kwargs
        return outcomes.pop(0)

    monkeypatch.setattr(agent, "run_agent", _fake_run_agent)

    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    at.chat_input[0].set_value("Question 1").run()
    assert not at.exception

    unescaped_dollar = re.compile(r"(?<!\\)\$")
    for m in at.markdown:
        assert not unescaped_dollar.search(m.value), f"$ non échappé dans un markdown : {m.value!r}"
    for c in at.caption:
        assert not unescaped_dollar.search(c.value), f"$ non échappé dans un caption : {c.value!r}"


def test_cinq_boutons_de_demo_textes_exacts():
    """
    Lot 1.3 changement B : un bouton de démo par document source (4) plus le
    garde-fou anti-hallucination déjà en place (5e), dans cet ordre exact.
    Les textes de question ont été vérifiés caractère pour caractère contre
    src/test_retrieval.py (Q01, Q08, Q15, Q19) avant application du diff.
    """
    demo_questions = _extract_demo_questions()
    assert len(demo_questions) == 5

    textes_attendus = [
        "Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?",
        "Quel est le montant minimum pour un versement complémentaire sur ARESIA Patrimoine+ ?",
        "Dans quel délai doit-on déclarer un cambriolage à son assureur ?",
        "Combien d'heures de formation continue un conseiller doit-il suivre par an au titre de la DDA ?",
        "Quelle est la garantie obsèques incluse dans le contrat prévoyance ?",
    ]
    textes_reels = [q for q, _legende in demo_questions]
    assert textes_reels == textes_attendus


def test_pas_de_panneau_log_debug_visiteur(monkeypatch):
    """
    Lot 1.3 changement C : le panneau sidebar "Log debug (dernier appel)"
    affichait les 30 dernières lignes de data/streamlit_debug.log à tout
    visiteur — fichier partagé entre sessions sur une même instance de
    conteneur (confidentialité). Il ne doit plus apparaître, y compris
    après une question réussie (LOG_PATH continue d'exister et d'être
    écrit — seul l'affichage visiteur est supprimé).
    """
    outcomes = [_make_success_state("Réponse de test numéro 1.", _USAGE_Q1)]

    def _fake_run_agent(question, *args, **kwargs):
        assert isinstance(question, str)
        assert not args and not kwargs
        return outcomes.pop(0)

    monkeypatch.setattr(agent, "run_agent", _fake_run_agent)

    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    at.chat_input[0].set_value("Question 1").run()
    assert not at.exception

    labels = [e.label for e in at.expander]
    assert not any("Log debug" in label for label in labels), f"panneau encore présent : {labels}"


def _configure_mistral(monkeypatch, actif: bool, server: str = "eu") -> None:
    """Fixe l'état Mistral de façon déterministe, indépendamment de l'environnement local."""
    if actif:
        monkeypatch.setenv("MISTRAL_API_KEY", "dummy-not-a-real-key")
        monkeypatch.setattr(agent, "MISTRAL_MODEL", "modele-mistral-de-test")
    else:
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        monkeypatch.setattr(agent, "MISTRAL_MODEL", None)
    monkeypatch.setattr(agent, "MISTRAL_SERVER", server)


def _contenu_choix_et_limites(at: AppTest) -> str:
    choix_expanders = [e for e in at.expander if "Choix et limites" in e.label]
    assert len(choix_expanders) == 1
    return " ".join(m.value for m in choix_expanders[0].markdown)


def test_expander_choix_et_limites_present_avec_contenu_attendu(monkeypatch):
    """Page "Choix et limites" avec comparaison Claude / Mistral, sans mock de run_agent (pas de question posée)."""
    _configure_mistral(monkeypatch, actif=True, server="eu")
    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not at.exception

    contenu = _contenu_choix_et_limites(at)
    assert "claude-sonnet-4-6" in contenu
    assert "Comparaison de deux moteurs" in contenu
    assert "Mistral Large 3" in contenu
    assert "modele-mistral-de-test" in contenu
    assert "Mistral Medium 3.5" in contenu
    assert "endpoint européen, facturé 10 % plus cher" in contenu
    assert "https://docs.mistral.ai/inference/regional-inference" in contenu
    assert "25/09/2026" in contenu
    assert "article 6.3 qui n'existe pas dans le document" in contenu
    assert "écrit et ajusté pour Claude" in contenu
    assert "Portabilité : testée sur un seul chemin" in contenu
    assert "non testé avec un autre fournisseur" not in contenu
    assert "500 caractères" in contenu


def test_choix_et_limites_sans_mistral_ni_bloc_comparaison_ni_affirmation_mistral(monkeypatch):
    _configure_mistral(monkeypatch, actif=False)
    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not at.exception

    contenu = _contenu_choix_et_limites(at)
    assert "Comparaison de deux moteurs" not in contenu
    assert "en comparaison" not in contenu
    assert "`claude-sonnet-4-6` seul" in contenu
    assert "(voir ci-dessus)" not in contenu


def test_choix_et_limites_endpoint_europeen_uniquement_si_serveur_eu(monkeypatch):
    _configure_mistral(monkeypatch, actif=True, server="global")
    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not at.exception

    contenu = _contenu_choix_et_limites(at)
    assert "Comparaison de deux moteurs" in contenu
    assert "endpoint européen" not in contenu
    assert "regional-inference" not in contenu


def test_choix_et_limites_dollars_echappes(monkeypatch):
    _configure_mistral(monkeypatch, actif=True)
    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not at.exception

    contenu = _contenu_choix_et_limites(at)
    assert "0,5 \\$ / 1,5 \\$" in contenu
    assert not re.search(r"(?<!\\)\$", contenu)


def test_titre_assurconseil_rag_partout_dans_l_ui(monkeypatch):
    _configure_mistral(monkeypatch, actif=False)
    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not at.exception

    assert [t.value for t in at.title] == ["🛡️ AssurConseil RAG"]

    source = Path(APP_PATH).read_text(encoding="utf-8")
    assert "AssurConseil 365" not in source
    assert 'page_title="AssurConseil RAG · TKoidra"' in source


def test_info_trace_mode_upload_selon_disponibilite_mistral(monkeypatch):
    for actif, attendu, interdit in (
        (True, "envoyée en parallèle aux deux moteurs", "unique appel LLM"),
        (False, "unique appel LLM", "aux deux moteurs"),
    ):
        _configure_mistral(monkeypatch, actif=actif)
        at = AppTest.from_file(APP_PATH, default_timeout=15).run()
        at.session_state["upload_active"] = True
        at.session_state["upload_collection"] = object()
        at.session_state["upload_doc_name"] = "mon-contrat.pdf"
        at.run()
        assert not at.exception

        infos = " ".join(i.value for i in at.info)
        assert attendu in infos
        assert interdit not in infos


def test_show_spinner_warm_up_mentionne_90_secondes():
    """Lot 1.4 : le message d'attente du démarrage à froid prévient le visiteur de la durée possible."""
    show_spinner = _extract_warm_up_show_spinner()
    assert "90 secondes" in show_spinner
    assert show_spinner == "Chargement du modèle d'embeddings… (jusqu'à 90 secondes au premier chargement)"


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


def test_mode_upload_route_vers_answer_question_on_upload_jamais_run_agent(monkeypatch):
    """
    Lot 2a.1 suite, Partie C : quand upload_active est vrai, app.py doit appeler
    upload_session.answer_question_on_upload() sur la collection éphémère de la
    session — jamais run_agent() (qui interrogerait la collection globale via le
    graphe LangGraph). Le pipeline d'upload réel (consentement, file_uploader,
    extraction, embedding) est déjà couvert par tests/test_upload_session.py et
    a été vérifié manuellement en local (voir rapport) ; ce test-ci isole
    uniquement le ROUTAGE app.py une fois ce mode actif, via injection directe
    de session_state plutôt que par un vrai upload de fichier (AppTest ne pilote
    pas de file_uploader réel).
    """
    def _fail_if_called(*a, **k):
        raise AssertionError("run_agent() a été appelé en mode upload — fuite vers la collection globale")

    monkeypatch.setattr(agent, "run_agent", _fail_if_called)

    fake_collection = object()
    captured: dict = {}

    def _fake_answer(collection, question):
        captured["collection"] = collection
        captured["question"] = question
        return "**Réponse directe** : test.\n**Source(s)** : [Article 1].\n**Point d'attention** : aucun."

    monkeypatch.setattr(upload_session, "answer_question_on_upload", _fake_answer)
    monkeypatch.setattr(upload_session, "touch", lambda session_id: None)

    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not at.exception

    at.session_state["upload_active"] = True
    at.session_state["upload_collection"] = fake_collection
    at.session_state["upload_doc_name"] = "mon-contrat.pdf"

    at.chat_input[0].set_value("Une question sur mon document").run()
    assert not at.exception

    assert captured["collection"] is fake_collection
    assert captured["question"] == "Une question sur mon document"

    messages = at.session_state["messages"]
    assert messages[-1]["mode"] == "upload"
    assert messages[-1]["doc_name"] == "mon-contrat.pdf"
    assert "usage" not in messages[-1]  # pas de suivi de coût dans ce chemin (voir rapport)
    assert at.session_state["last_trace"] == []


def _fake_active_lock(inactif_depuis_s: float) -> dict:
    """Verrou d'upload factice (client/collection sans effet) inactif depuis N secondes."""
    import time
    from types import SimpleNamespace

    now = time.monotonic()
    return {
        "session_id": "autre-visiteur",
        "client": SimpleNamespace(delete_collection=lambda name: None),
        "collection": SimpleNamespace(name="upload_autre-visiteur"),
        "acquired_at": now - inactif_depuis_s - 10,
        "last_activity": now - inactif_depuis_s,
    }


def _busy_warnings(at: AppTest) -> list[str]:
    return [w.value for w in at.warning if w.value == upload_session.UPLOAD_BUSY_MESSAGE]


def test_verrou_upload_perime_libere_avant_affichage_occupe(monkeypatch):
    """
    Un verrou inactif depuis plus de UPLOAD_LOCK_TIMEOUT_S (onglet abandonné)
    ne doit plus bloquer le dépôt : app.py le libère avant de tester is_busy().
    """
    monkeypatch.setattr(
        upload_session, "_active", _fake_active_lock(upload_session.UPLOAD_LOCK_TIMEOUT_S + 1)
    )

    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    at.session_state["upload_consent"] = True
    at.run()
    assert not at.exception

    assert _busy_warnings(at) == []
    assert upload_session.is_busy() is False


def test_verrou_upload_actif_recent_affiche_toujours_occupe(monkeypatch):
    monkeypatch.setattr(upload_session, "_active", _fake_active_lock(5.0))

    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    at.session_state["upload_consent"] = True
    at.run()
    assert not at.exception

    assert len(_busy_warnings(at)) == 1
    assert upload_session.is_busy() is True


def test_cout_none_affiche_non_disponible_sans_exception():
    """Un usage sans coût calculable (tarif absent) ne doit ni lever ni afficher « None »."""
    at = AppTest.from_file(APP_PATH, default_timeout=15).run()
    at.session_state["messages"] = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "réponse",
            "usage": {**_USAGE_Q1, "cout_usd": None},
        },
    ]
    at.run()
    assert not at.exception

    captions = _usage_captions(at)
    assert len(captions) == 1
    assert "coût non disponible" in captions[0]
    assert "None" not in captions[0]
    assert "estimation" not in captions[0]

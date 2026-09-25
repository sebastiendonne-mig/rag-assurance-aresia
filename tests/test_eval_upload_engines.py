"""
Tests du script d'évaluation Claude / Mistral (sous-lot 3.2a).
Aucun réseau, aucune clé réelle, aucun modèle d'embedding : le chemin upload est
remplacé par un faux, les variables d'environnement sont des sentinelles.
Seul le test sur les vrais PDF lit des fichiers du dépôt (extraction, hors ligne).
"""
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import eval_upload_engines as ev

FIXED_NOW = datetime(2026, 9, 25, 10, 15, 0, tzinfo=timezone.utc)
VALEUR_TEST_A = "PLACEHOLDER-PLACEHOLDER-PLACEHOLDER-A"
VALEUR_TEST_M = "PLACEHOLDER-PLACEHOLDER-PLACEHOLDER-M"
ENV = {
    "ANTHROPIC_API_KEY": VALEUR_TEST_A,
    "MISTRAL_API_KEY": VALEUR_TEST_M,
    "MISTRAL_MODEL": "mistral-large-2512",
}
REFUS = "Je ne trouve pas cette information dans les documents disponibles."


# ─────────────────────────────────────────────
# Doubles
# ─────────────────────────────────────────────

@dataclass
class FakeResult:
    engine: str
    succes: bool = True
    reponse: str | None = "ok"
    erreur: str | None = None
    tokens_in: int = 1000
    tokens_out: int = 200
    cout_usd: float | None = 0.01
    latence_s: float = 1.5


def _verdict(test, reponse):
    """Même logique que tests/test_golden_set.py:verdict (sous-chaîne)."""
    if test["expected_article"] is None:
        ok = "Je ne trouve pas cette information" in reponse
        return ok, "refus" if ok else "pas de refus"
    cible = f"Article {test['expected_article']}"
    return (cible in reponse), ("cité" if cible in reponse else "non cité")


def _check_format(reponse):
    return [b for b in ("Réponse directe", "Source(s)", "Point d'attention") if b not in reponse]


TOOLS = ev.GoldenTools(
    non_trouve="Je ne trouve pas cette information",
    blocs=["Réponse directe", "Source(s)", "Point d'attention"],
    verdict=_verdict,
    check_format=_check_format,
)


def _test(code, article, doc, question=None):
    return {
        "label": f"{code} — libellé",
        "question": question or f"question {code} ?",
        "expected_article": article,
        "expected_doc": doc,
    }


SAMPLE_TESTS = [
    _test("Q01", "4.1", "CG-PREV-INV-2024"),
    _test("Q02", "4.2", "CG-PREV-INV-2024"),
    _test("Q13", "2.3", "BAR-IARD-2024-V2"),
    _test("Q20", None, None),
]

FAKE_DOCS = [
    {"path": Path("/fake/CG-prevoyance-invalidite.pdf"), "source_doc": "CG-PREV-INV-2024"},
    {"path": Path("/fake/CG-assurance-vie.pdf"), "source_doc": "CG-AV-MULTI-2024"},
    {"path": Path("/fake/bareme-garanties-iard.pdf"), "source_doc": "BAR-IARD-2024-V2"},
    {"path": Path("/fake/circulaire-acpr-conseil.pdf"), "source_doc": "ACPR-REC-2024-12"},
]

REFS = ev.DocReferences(
    chapitres=frozenset({"1", "4", "4.1", "4.2", "6", "2.3", "1.1", "8", "10", "13", "15", "23", "24", "9", "7", "3.1"}),
    definitions=frozenset({"1", "4", "4.1", "4.2", "6", "2.3", "1.1", "8", "10", "13", "15", "23", "24", "9", "7", "3.1", "5.1"}),
)


def _answer(article, refus=False, cite_extra=""):
    if refus:
        return f"**Réponse directe** : {REFUS}\n**Source(s)** : aucune\n**Point d'attention** : néant"
    citation = f"[Article {article} des CG — v4.2]" if article else ""
    return f"**Réponse directe** : oui\n**Source(s)** : {citation} {cite_extra}\n**Point d'attention** : néant"


class FakeApi:
    def __init__(self, tests=None, behaviors=None, ingest_errors=None, acquire_errors=None, hook=None):
        self.tests = {t["question"]: t for t in (tests or SAMPLE_TESTS)}
        self.behaviors = behaviors or {}
        self.ingest_errors = ingest_errors or {}
        self.acquire_errors = list(acquire_errors or [])
        self.hook = hook
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.touched: list[str] = []
        self.ingested: list[str] = []
        self.compare_calls: list[str] = []

    def acquire(self, sid):
        if self.acquire_errors:
            raise self.acquire_errors.pop(0)
        self.acquired.append(sid)

    def ingest(self, sid, path):
        self.ingested.append(path.name)
        if path.name in self.ingest_errors:
            raise self.ingest_errors[path.name]
        return ev.IngestInfo(n_chunks=9, n_tronques=0, refs=REFS)

    def touch(self, sid):
        self.touched.append(sid)

    def compare(self, sid, question):
        self.compare_calls.append(question)
        if self.hook:
            self.hook(len(self.compare_calls), question)
        comportement = self.behaviors.get(question)
        if isinstance(comportement, BaseException):
            raise comportement
        if comportement is not None:
            return comportement
        test = self.tests[question]
        refus = test["expected_article"] is None
        texte = _answer(test["expected_article"], refus=refus)
        return [FakeResult("anthropic", reponse=texte), FakeResult("mistral", reponse=texte)]

    def release(self, sid):
        self.released.append(sid)


def _estimer(tin, tout, moteur):
    if moteur == "anthropic":
        return (tin * 3.0 + tout * 15.0) / 1e6
    return (tin * 0.55 + tout * 1.65) / 1e6


def make_runtime(api=None, tests=None, docs=None, server="eu", tarifs=(0.55, 1.65), configure=None):
    return ev.Runtime(
        claude_model="claude-sonnet-4-6",
        mistral_model="mistral-large-2512",
        mistral_server=server,
        mistral_host="api.eu.mistral.ai",
        mistral_tarifs=tarifs,
        estimer=_estimer if tarifs else (lambda tin, tout, m: None if m == "mistral" else _estimer(tin, tout, m)),
        docs=docs or FAKE_DOCS,
        tests=tests or SAMPLE_TESTS,
        tools=TOOLS,
        api=api or FakeApi(),
        configure_logging=configure or (lambda: None),
        versions={"python": "3.13", "mistralai": "2.10.1", "anthropic": "0.111.0"},
    )


@pytest.fixture(autouse=True)
def _propre_logging():
    yield
    for nom in ("upload_session", "audit_llm"):
        lg = logging.getLogger(nom)
        lg.handlers = [h for h in lg.handlers if not isinstance(h, ev.LogCapture)]
        lg.setLevel(logging.NOTSET)


def run_main(tmp_path, argv, rt=None, environ=None):
    lignes: list[str] = []
    rt = rt or make_runtime()
    code = ev.main(
        argv + ["--out-dir", str(tmp_path)],
        environ=ENV if environ is None else environ,
        out=lignes.append,
        loader=lambda: rt,
        now=lambda: FIXED_NOW,
    )
    return code, lignes, rt


def read_report(tmp_path):
    fichiers = sorted(tmp_path.glob("upload_eval_*.json"))
    assert len(fichiers) == 1, fichiers
    return json.loads(fichiers[0].read_text(encoding="utf-8")), fichiers[0]


# ─────────────────────────────────────────────
# Citations : extraction
# ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("Voir l'Article 4.1 du contrat.", ["4.1"]),
        ("[Article 4.1 des CG Prévoyance Invalidité — v4.2]", ["4.1"]),
        ("[Article 2.3 — Barème Garanties IARD 2024 v2.0]", ["2.3"]),
        ("Article 4.1 puis encore Article 4.1 et Article 6", ["4.1", "6"]),
        ("selon Art. 8 des CG", ["8"]),
        ("Articles 4.1, 4.2 et 4.3", ["4.1", "4.2", "4.3"]),
        ("Article 4.3 & Article 6", ["4.3", "6"]),
        ("Article 4.1, 30 jours de franchise", ["4.1"]),       # virgule sans pluriel : pas une liste
        ("Article L.113-8 du Code des assurances", []),        # renvoi légal à lettre : ignoré
        ("Article 990-I du CGI", ["990"]),                     # numéro lu, sera classé "absent"
        ("aucune référence ici", []),
        # Régression : la coupure à la virgule ne doit pas avaler les citations suivantes.
        ("Article 4, Article 2.3 et Article 990-I", ["4", "2.3", "990"]),
        ("Article 4.1, 30 jours. Voir Article 6", ["4.1", "6"]),
    ],
)
def test_extract_citations(texte, attendu):
    assert ev.extract_citations(texte).numbers == attendu


@pytest.mark.parametrize("texte", ["Articles 5 à 7", "Articles 4.1-4.3", "Articles 4 au 6"])
def test_les_plages_sont_signalees_et_non_developpees(texte):
    cit = ev.extract_citations(texte)
    assert cit.plages, texte
    assert len(cit.numbers) == 2  # seulement les bornes


def test_une_liste_n_est_pas_une_plage():
    assert ev.extract_citations("Articles 4.1, 4.2 et 4.3").plages == []


# ─────────────────────────────────────────────
# Références et classement
# ─────────────────────────────────────────────

def test_build_references_exclut_les_renvois_internes_et_garde_les_sous_clauses():
    lignes = [
        "Article 4 — Franchise",
        "n Article 5.1 — La franchise est calculée par sinistre",
        "Voir l'Article 2.3 des présentes Conditions Générales",   # renvoi mort : hors définition
        "  selon l'Article 6.3 de la notice",                       # renvoi interne
        "Article 990-I du Code général des impôts",                # pas de tiret cadratin
    ]
    chunks = [
        {"metadata": {"article_num": ""}},
        {"metadata": {"article_num": "4"}},
    ]
    refs = ev.build_references(lignes, chunks)
    assert refs.chapitres == frozenset({"4"})
    assert refs.definitions == frozenset({"4", "5.1"})


def test_classement_article_sous_clause_absent():
    assert ev.classify_citation("4.1", REFS) == "article"
    assert ev.classify_citation("5.1", REFS) == "sous-clause"
    assert ev.classify_citation("990", REFS) == "absent"
    assert ev.classify_citation("99", REFS) == "absent"


def test_l_existence_se_teste_dans_le_bon_document():
    prev = ev.DocReferences(frozenset({"4", "4.2"}), frozenset({"4", "4.2"}))
    bareme = ev.DocReferences(frozenset({"1.1", "4.1"}), frozenset({"1.1", "4.1"}))
    assert ev.classify_citation("4.1", bareme) == "article"
    assert ev.classify_citation("4.1", prev) == "absent"


# ─────────────────────────────────────────────
# Analyse d'une réponse
# ─────────────────────────────────────────────

def test_analyse_reponse_nominale():
    a = ev.analyse_answer(SAMPLE_TESTS[0], REFS, _answer("4.1"), TOOLS)
    assert a["articles_cites"] == ["4.1"]
    assert a["absents"] == []
    assert a["citation_attendue"] is True
    assert a["aucune_citation"] is False
    assert a["garde_fou"] is None
    assert a["blocs_manquants"] == []


def test_citation_attendue_est_plus_stricte_que_l_ancien_verdict():
    """Attendu "4" : 'Article 4.1' satisfait la sous-chaîne de l'ancien verdict, pas le numéro exact."""
    test = _test("Q17", "4", "ACPR-REC-2024-12")
    a = ev.analyse_answer(test, REFS, _answer("4.1"), TOOLS)
    assert a["verdict_historique"]["ok"] is True
    assert a["citation_attendue"] is False


def test_citation_absente_du_document_est_signalee():
    a = ev.analyse_answer(SAMPLE_TESTS[0], REFS, _answer("4.1", cite_extra="[Article 77]"), TOOLS)
    assert a["absents"] == ["77"]


def test_renvoi_mort_et_externe_sont_absents():
    refs = ev.DocReferences(frozenset({"1", "4"}), frozenset({"1", "4"}))  # 2.3 et 990 hors définition
    a = ev.analyse_answer(SAMPLE_TESTS[0], refs, "Article 4, Article 2.3 et Article 990-I", TOOLS)
    assert set(a["absents"]) == {"2.3", "990"}


def test_reponse_sans_citation_est_signalee_sauf_garde_fou():
    normal = ev.analyse_answer(SAMPLE_TESTS[0], REFS, "Réponse directe sans aucune source", TOOLS)
    assert normal["aucune_citation"] is True
    q20 = ev.analyse_answer(SAMPLE_TESTS[3], REFS, _answer(None, refus=True), TOOLS)
    assert q20["aucune_citation"] is False


def test_garde_fou_confirme_ou_a_relire():
    confirme = ev.analyse_answer(SAMPLE_TESTS[3], REFS, _answer(None, refus=True), TOOLS)
    assert confirme["garde_fou"] == "confirme"
    paraphrase = ev.analyse_answer(
        SAMPLE_TESTS[3], REFS, "**Réponse directe** : le document ne mentionne pas cela.", TOOLS
    )
    assert paraphrase["garde_fou"] == "a_relire"


def test_faux_negatif_refus_alors_que_l_information_existe():
    a = ev.analyse_answer(SAMPLE_TESTS[0], REFS, _answer(None, refus=True), TOOLS)
    assert a["faux_negatif"] is True


def test_blocs_manquants_remontes():
    a = ev.analyse_answer(SAMPLE_TESTS[0], REFS, "juste du texte [Article 4.1]", TOOLS)
    assert "Réponse directe" in a["blocs_manquants"]


# ─────────────────────────────────────────────
# Plan : questions -> documents
# ─────────────────────────────────────────────

def test_plan_rattache_chaque_question_a_son_document_et_q20_au_prev():
    specs = ev.plan_documents(FAKE_DOCS, SAMPLE_TESTS)
    par_doc = {s.doc_id: [ev.question_code(t) for t in s.questions] for s in specs}
    assert par_doc == {
        "CG-PREV-INV-2024": ["Q01", "Q02", "Q20"],
        "BAR-IARD-2024-V2": ["Q13"],
    }
    assert [s.doc_id for s in specs] == ["CG-PREV-INV-2024", "BAR-IARD-2024-V2"]  # ordre de `docs`


def test_plan_fumee_une_seule_question():
    specs = ev.plan_documents(FAKE_DOCS, SAMPLE_TESTS, only="Q13")
    assert [(s.doc_id, len(s.questions)) for s in specs] == [("BAR-IARD-2024-V2", 1)]


def test_plan_question_inconnue_ou_document_inconnu():
    with pytest.raises(ValueError):
        ev.plan_documents(FAKE_DOCS, SAMPLE_TESTS, only="Q99")
    with pytest.raises(ValueError):
        ev.plan_documents(FAKE_DOCS, [_test("Q01", "1", "DOC-INCONNU")])


def test_plan_reel_20_questions_4_documents_q20_dans_le_prev():
    import extract_chunks
    from test_retrieval import TESTS

    specs = ev.plan_documents(extract_chunks.DOCS, TESTS)
    assert [s.doc_id for s in specs] == [
        "CG-PREV-INV-2024", "CG-AV-MULTI-2024", "BAR-IARD-2024-V2", "ACPR-REC-2024-12",
    ]
    assert [len(s.questions) for s in specs] == [7, 6, 4, 3]  # PREV = Q01-Q06 + Q20
    assert sum(len(s.questions) for s in specs) == 20
    assert ev.question_code(specs[0].questions[-1]) == "Q20"


# ─────────────────────────────────────────────
# Coût et résumé de démarrage
# ─────────────────────────────────────────────

def test_estimation_de_cout_par_moteur_et_totale():
    cout = ev.estimate_run_cost(20, _estimer)
    assert cout["par_moteur"]["anthropic"] == pytest.approx(20 * (8000 * 3.0 + 1500 * 15.0) / 1e6)
    assert cout["par_moteur"]["mistral"] == pytest.approx(20 * (8000 * 0.55 + 1500 * 1.65) / 1e6)
    assert cout["total"] == pytest.approx(sum(cout["par_moteur"].values()))


def test_estimation_avec_les_vraies_constantes_de_l_app(monkeypatch):
    """Vérifie les chiffres annoncés : ≈ 1,07 $ (complet) et ≈ 0,05 $ (fumée)."""
    import agent

    monkeypatch.setattr(agent, "MISTRAL_MODEL", agent.MISTRAL_PRICED_MODEL)
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "eu")
    complet = ev.estimate_run_cost(20, agent.estimer_cout_usd)
    fumee = ev.estimate_run_cost(1, agent.estimer_cout_usd)
    assert complet["par_moteur"]["anthropic"] == pytest.approx(0.93)
    assert complet["par_moteur"]["mistral"] == pytest.approx(0.1375)
    assert complet["total"] == pytest.approx(1.0675)
    assert fumee["total"] == pytest.approx(0.05338, abs=1e-4)


def test_estimation_sans_tarif_mistral_est_non_disponible():
    cout = ev.estimate_run_cost(20, lambda tin, tout, m: None if m == "mistral" else 0.01)
    assert cout["par_moteur"]["mistral"] is None
    assert cout["total"] is None
    assert ev.fmt_usd(None) == "non disponible"


def test_resume_de_demarrage_contient_l_essentiel():
    rt = make_runtime()
    specs = ev.plan_documents(rt.docs, rt.tests)
    texte = ev.format_startup_summary(rt, specs, smoke=False, cout=ev.estimate_run_cost(4, rt.estimer))
    for attendu in (
        "claude-sonnet-4-6", "mistral-large-2512", "api.eu.mistral.ai", "« eu »",
        "Appels réels prévus  : 8", "BORNE HAUTE", "hypothèse non mesurée", "Total",
    ):
        assert attendu in texte, attendu


def test_resume_de_demarrage_signale_un_modele_non_tarife():
    rt = make_runtime(tarifs=None)
    specs = ev.plan_documents(rt.docs, rt.tests)
    texte = ev.format_startup_summary(rt, specs, smoke=True, cout=ev.estimate_run_cost(1, rt.estimer))
    assert "NON TARIFÉ" in texte
    assert "FUMÉE" in texte
    assert "non disponible" in texte


# ─────────────────────────────────────────────
# Démarrage : variables d'environnement, garde-fous
# ─────────────────────────────────────────────

def test_missing_env_ne_renvoie_que_des_noms():
    assert ev.missing_env({}) == list(ev.REQUIRED_ENV)
    assert ev.missing_env({**ENV, "MISTRAL_API_KEY": ""}) == ["MISTRAL_API_KEY"]  # vide = absente
    assert ev.missing_env(ENV) == []


def test_cle_manquante_refus_sans_charger_le_runtime_ni_fuiter_de_valeur(tmp_path):
    def loader_interdit():
        raise AssertionError("le runtime ne doit jamais être chargé si une variable manque")

    lignes: list[str] = []
    environ = {k: v for k, v in ENV.items() if k != "MISTRAL_API_KEY"}
    code = ev.main(["--yes", "--out-dir", str(tmp_path)], environ=environ, out=lignes.append, loader=loader_interdit)
    sortie = "\n".join(lignes)

    assert code == ev.EXIT_REFUSED == 2
    assert "MISTRAL_API_KEY" in sortie
    assert "ANTHROPIC_API_KEY" not in sortie          # présente : pas mentionnée
    assert VALEUR_TEST_A not in sortie and VALEUR_TEST_M not in sortie
    assert not re.search(rf"\b{len(VALEUR_TEST_A)}\b", sortie)   # jamais de longueur
    assert list(tmp_path.iterdir()) == []


def test_subprocess_garde_fous_avant_tout_import_lourd(tmp_path):
    """Processus neuf, clé Mistral absente : code 2, noms seulement, `agent` jamais importé."""
    code = (
        "import sys; sys.path.insert(0, %r); import eval_upload_engines as e; "
        "print('IMPORT_AGENT_AU_CHARGEMENT', 'agent' in sys.modules); "
        "rc = e.main(['--out-dir', %r]); "
        "print('RC', rc); print('AGENT_IMPORTE', 'agent' in sys.modules, 'dotenv' in sys.modules)"
    ) % (str(HERE), str(tmp_path))
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "ANTHROPIC_API_KEY": VALEUR_TEST_A,
        "MISTRAL_MODEL": "mistral-large-2512",
    }
    res = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=ROOT, timeout=60)
    sortie = res.stdout + res.stderr

    assert "IMPORT_AGENT_AU_CHARGEMENT False" in res.stdout
    assert "RC 2" in res.stdout
    assert "AGENT_IMPORTE False False" in res.stdout
    assert "MISTRAL_API_KEY" in sortie
    assert VALEUR_TEST_A not in sortie


def test_neutralize_dotenv_ne_lit_aucun_fichier_env(tmp_path, monkeypatch):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", dotenv.load_dotenv)  # restauré en fin de test
    (tmp_path / ".env").write_text("SENTINELLE_DOTENV_XYZ=oui\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SENTINELLE_DOTENV_XYZ", raising=False)

    ev.neutralize_dotenv()

    assert dotenv.load_dotenv() is False
    assert "SENTINELLE_DOTENV_XYZ" not in os.environ


def test_refus_si_le_serveur_mistral_n_est_pas_eu(tmp_path):
    for serveur in ("global", "us"):
        code, lignes, rt = run_main(tmp_path, ["--yes"], make_runtime(server=serveur))
        assert code == 2
        assert f"« {serveur} »" in "\n".join(lignes)
        assert rt.api.compare_calls == [] and rt.api.acquired == []
    assert list(tmp_path.iterdir()) == []


def test_configuration_invalide_est_un_refus_propre(tmp_path):
    def loader():
        raise ValueError("MISTRAL_SERVER invalide : 'EU'")

    lignes: list[str] = []
    code = ev.main(["--yes", "--out-dir", str(tmp_path)], environ=ENV, out=lignes.append, loader=loader)
    assert code == 2
    assert "Configuration invalide" in "\n".join(lignes)


def test_sans_yes_aucun_appel_ni_fichier_et_code_2(tmp_path):
    code, lignes, rt = run_main(tmp_path, [])
    sortie = "\n".join(lignes)
    assert code == 2
    assert "Aucun appel effectué" in sortie
    assert "Appels réels prévus  : 8" in sortie
    assert rt.api.acquired == [] and rt.api.compare_calls == []
    assert list(tmp_path.iterdir()) == []
    assert VALEUR_TEST_A not in sortie and VALEUR_TEST_M not in sortie


def test_smoke_sans_yes_reste_un_resume(tmp_path):
    code, lignes, rt = run_main(tmp_path, ["--smoke"])
    assert code == 2
    assert "FUMÉE" in "\n".join(lignes)
    assert rt.api.compare_calls == []


# ─────────────────────────────────────────────
# Déroulé
# ─────────────────────────────────────────────

def test_fumee_une_seule_question_deux_moteurs(tmp_path):
    code, lignes, rt = run_main(tmp_path, ["--smoke", "--yes"])
    assert code == 0
    assert rt.api.compare_calls == [SAMPLE_TESTS[0]["question"]]   # Q01 par défaut
    report, fichier = read_report(tmp_path)
    assert fichier.name == "upload_eval_20260925_101500_smoke.json"
    assert report["en_tete"]["mode"] == "fumée"
    assert len(report["resultats"]) == 1
    assert set(report["resultats"][0]["moteurs"]) == {"anthropic", "mistral"}
    assert report["resume"]["anthropic"]["plancher"]["garde_fou"] == "non_applicable"


def test_fumee_sur_q20_teste_le_garde_fou(tmp_path):
    code, _, rt = run_main(tmp_path, ["--smoke", "Q20", "--yes"])
    assert code == 0
    assert rt.api.compare_calls == [SAMPLE_TESTS[3]["question"]]
    report, _ = read_report(tmp_path)
    assert report["resume"]["mistral"]["plancher"]["garde_fou"] == "confirme"


def test_fumee_question_inconnue_est_un_refus(tmp_path):
    code, lignes, rt = run_main(tmp_path, ["--smoke", "Q99", "--yes"])
    assert code == 2
    assert "Plan invalide" in "\n".join(lignes)
    assert rt.api.compare_calls == []


def test_run_complet_ordre_des_documents_et_verrou_libere(tmp_path):
    code, _, rt = run_main(tmp_path, ["--yes"])
    assert code == 0
    assert rt.api.ingested == ["CG-prevoyance-invalidite.pdf", "bareme-garanties-iard.pdf"]
    assert len(rt.api.compare_calls) == 4
    assert len(rt.api.acquired) == 2 and rt.api.released == rt.api.acquired
    assert len(set(rt.api.acquired)) == 2                       # un identifiant de session par document
    assert all(s.startswith("eval-") for s in rt.api.acquired)
    assert len(rt.api.touched) == 4                             # touch avant chaque question


def test_run_reel_20_comparaisons_4_documents(tmp_path):
    import extract_chunks
    from test_retrieval import TESTS

    api = FakeApi(tests=TESTS)
    rt = make_runtime(api=api, tests=TESTS, docs=list(extract_chunks.DOCS))
    code, _, _ = run_main(tmp_path, ["--yes"], rt)
    assert code == 0
    assert len(api.compare_calls) == 20 < 50                     # très en dessous du disjoncteur (50)
    assert len(api.acquired) == 4 and api.released == api.acquired
    report, _ = read_report(tmp_path)
    assert report["n_questions"] == 20 and len(report["resultats"]) == 20


def test_un_moteur_en_echec_n_arrete_ni_l_autre_ni_le_run(tmp_path):
    q = SAMPLE_TESTS[0]["question"]
    behaviors = {
        q: [
            FakeResult("anthropic", reponse=_answer("4.1")),
            FakeResult("mistral", succes=False, reponse=None, erreur="Une erreur technique est survenue.", cout_usd=0.0),
        ]
    }
    code, _, rt = run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    report, _ = read_report(tmp_path)
    assert code == 0
    assert len(rt.api.compare_calls) == 4                        # le run a continué
    premiere = report["resultats"][0]["moteurs"]
    assert premiere["anthropic"]["succes"] is True and premiere["anthropic"]["reponse"]
    assert premiere["mistral"]["succes"] is False and premiere["mistral"]["reponse"] is None
    assert report["resume"]["anthropic"]["plancher"]["technique"] == "atteint"
    assert report["resume"]["mistral"]["plancher"]["technique"] == "non_atteint"
    assert report["resume"]["mistral"]["plancher"]["pannes"] == [SAMPLE_TESTS[0]["label"]]


def test_anthropic_en_echec_dans_l_autre_sens(tmp_path):
    q = SAMPLE_TESTS[1]["question"]
    behaviors = {
        q: [
            FakeResult("anthropic", succes=False, reponse=None, erreur="neutre"),
            FakeResult("mistral", reponse=_answer("4.2")),
        ]
    }
    run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    report, _ = read_report(tmp_path)
    assert report["resume"]["anthropic"]["plancher"]["technique"] == "non_atteint"
    assert report["resume"]["mistral"]["plancher"]["technique"] == "atteint"


def test_exception_de_comparaison_continue_et_n_expose_que_le_type(tmp_path):
    q = SAMPLE_TESTS[0]["question"]
    api = FakeApi(behaviors={q: RuntimeError("DETAIL_INTERNE_SECRET chemin /tmp/x")})
    code, lignes, _ = run_main(tmp_path, ["--yes"], make_runtime(api=api))
    report, fichier = read_report(tmp_path)
    assert code == 0
    assert len(api.compare_calls) == 4
    assert report["resultats"][0]["erreur_globale"] == {"type": "RuntimeError"}
    assert "DETAIL_INTERNE_SECRET" not in fichier.read_text(encoding="utf-8")
    assert "DETAIL_INTERNE_SECRET" not in "\n".join(lignes)
    assert api.released == api.acquired                          # verrous libérés malgré l'exception


def test_document_rejete_a_l_ingestion_questions_non_evaluees_et_run_continue(tmp_path):
    from pathlib import Path as P

    api = FakeApi(ingest_errors={"CG-prevoyance-invalidite.pdf": ValueError("pas de structure")})
    code, _, _ = run_main(tmp_path, ["--yes"], make_runtime(api=api))
    report, _ = read_report(tmp_path)
    assert code == 0
    # Le PREV (3 questions) n'est pas évalué ; le barème (1 question) l'est.
    assert api.compare_calls == [SAMPLE_TESTS[2]["question"]]
    non_evalues = [r for r in report["resultats"] if r["erreur_globale"]]
    assert len(non_evalues) == 3
    assert all(r["erreur_globale"]["etape"] == "ingestion" for r in non_evalues)
    assert report["documents"]["CG-PREV-INV-2024"] == {"ingestion_erreur": "ValueError"}
    assert api.released == api.acquired and len(api.released) == 2   # verrou libéré même après l'échec
    assert report["resume"]["anthropic"]["plancher"]["technique"] == "non_atteint"


def test_acquisition_impossible_marque_les_questions_et_continue(tmp_path):
    api = FakeApi(acquire_errors=[RuntimeError("verrou pris")])
    code, _, _ = run_main(tmp_path, ["--yes"], make_runtime(api=api))
    report, _ = read_report(tmp_path)
    assert code == 0
    assert [r["erreur_globale"]["etape"] for r in report["resultats"] if r["erreur_globale"]] == ["acquisition"] * 3
    assert api.compare_calls == [SAMPLE_TESTS[2]["question"]]
    assert len(api.released) == 1                                # rien à libérer pour le document non acquis


def test_ctrl_c_libere_le_verrou_et_ecrit_un_fichier_partiel(tmp_path):
    api = FakeApi(behaviors={SAMPLE_TESTS[1]["question"]: KeyboardInterrupt()})
    code, lignes, _ = run_main(tmp_path, ["--yes"], make_runtime(api=api))
    report, fichier = read_report(tmp_path)
    assert code == ev.EXIT_INTERRUPTED == 130
    assert api.released == api.acquired and len(api.released) == 1   # libéré malgré Ctrl+C
    assert report["interrompu"] is True
    assert len(report["resultats"]) == 1                          # Q01 terminée avant l'interruption
    assert fichier.with_suffix(".md").exists()
    assert "RUN INTERROMPU" in fichier.with_suffix(".md").read_text(encoding="utf-8")
    assert "Interrompu" in "\n".join(lignes)


def test_fichier_ecrit_au_fil_de_l_eau_et_toujours_valide(tmp_path):
    vus: list[int] = []

    def hook(n, question):
        # Au moment de la n-ième comparaison, le fichier contient déjà les n-1 précédentes.
        fichiers = list(tmp_path.glob("upload_eval_*.json"))
        assert len(fichiers) == 1
        vus.append(len(json.loads(fichiers[0].read_text(encoding="utf-8")).get("resultats", [])))

    run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(hook=hook)))
    assert vus == [0, 1, 2, 3]
    assert not list(tmp_path.glob("*.tmp"))                       # aucun fichier temporaire résiduel


def test_les_logs_de_l_app_fournissent_type_status_code_et_request_id(tmp_path):
    """Capture (sans toucher au code de l'app) de COMPARE_ENGINE_ERROR et du log d'audit LLM_CALL."""
    q1, q2 = SAMPLE_TESTS[0]["question"], SAMPLE_TESTS[1]["question"]

    def hook(n, question):
        if question == q1:
            logging.getLogger("upload_session").warning(
                "COMPARE_ENGINE_ERROR moteur=%s type=%s status_code=%s", "mistral", "SDKError", 429
            )
            logging.getLogger("audit_llm").info(
                "LLM_CALL moteur=mistral endpoint=api.eu.mistral.ai server=eu modele_demande=m "
                "modele_servi=m request_id=req-abc-123 tentative=1/2"
            )

    behaviors = {
        q1: [FakeResult("anthropic", reponse=_answer("4.1")), FakeResult("mistral", succes=False, reponse=None, erreur="neutre")]
    }
    rt = make_runtime(
        api=FakeApi(behaviors=behaviors, hook=hook),
        configure=lambda: logging.getLogger("audit_llm").setLevel(logging.INFO),  # ce que fait l'app
    )
    run_main(tmp_path, ["--yes"], rt)
    report, _ = read_report(tmp_path)
    m1 = report["resultats"][0]["moteurs"]["mistral"]
    assert m1["erreur_type"] == "SDKError" and m1["erreur_status_code"] == "429"
    assert m1["request_id"] == "req-abc-123"
    assert report["resultats"][0]["moteurs"]["anthropic"]["request_id"] is None
    # Les logs d'une question ne fuient pas dans la suivante.
    m2 = report["resultats"][1]["moteurs"]["mistral"]
    assert m2["erreur_type"] is None and m2["request_id"] is None


def test_le_suivi_affiche_ne_contient_jamais_de_contenu_de_reponse(tmp_path):
    q = SAMPLE_TESTS[0]["question"]
    behaviors = {q: [FakeResult("anthropic", reponse="CONTENU_SENTINELLE_XYZ [Article 4.1]"), FakeResult("mistral", reponse="CONTENU_SENTINELLE_XYZ")]}
    _, lignes, _ = run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    assert "CONTENU_SENTINELLE_XYZ" not in "\n".join(lignes)


# ─────────────────────────────────────────────
# Plancher (résumé)
# ─────────────────────────────────────────────

def test_plancher_tout_va_bien(tmp_path):
    run_main(tmp_path, ["--yes"])
    report, _ = read_report(tmp_path)
    for moteur in ("anthropic", "mistral"):
        p = report["resume"][moteur]["plancher"]
        assert p["technique"] == "atteint"
        assert p["garde_fou"] == "confirme"
        assert p["citations"] == "aucune_citation_absente"


def test_plancher_garde_fou_a_relire_si_refus_paraphrase(tmp_path):
    q20 = SAMPLE_TESTS[3]["question"]
    behaviors = {
        q20: [
            FakeResult("anthropic", reponse=_answer(None, refus=True)),
            FakeResult("mistral", reponse="**Réponse directe** : le document ne prévoit pas cela.\n**Source(s)** : -\n**Point d'attention** : -"),
        ]
    }
    run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    report, _ = read_report(tmp_path)
    assert report["resume"]["anthropic"]["plancher"]["garde_fou"] == "confirme"
    assert report["resume"]["mistral"]["plancher"]["garde_fou"] == "a_relire"


def test_plancher_garde_fou_non_atteint_si_le_moteur_echoue_sur_q20(tmp_path):
    q20 = SAMPLE_TESTS[3]["question"]
    behaviors = {q20: [FakeResult("anthropic", reponse=_answer(None, refus=True)), FakeResult("mistral", succes=False, reponse=None, erreur="neutre")]}
    run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    report, _ = read_report(tmp_path)
    assert report["resume"]["mistral"]["plancher"]["garde_fou"] == "non_atteint"


def test_plancher_citations_a_relire_quand_un_article_est_absent(tmp_path):
    q = SAMPLE_TESTS[0]["question"]
    behaviors = {
        q: [
            FakeResult("anthropic", reponse=_answer("4.1")),
            FakeResult("mistral", reponse=_answer("4.1", cite_extra="[Article 77]")),
        ]
    }
    run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    report, _ = read_report(tmp_path)
    assert report["resume"]["anthropic"]["plancher"]["citations"] == "aucune_citation_absente"
    p = report["resume"]["mistral"]["plancher"]
    assert p["citations"] == "a_relire"
    assert p["citations_absentes"] == [{"question": SAMPLE_TESTS[0]["label"], "article": "77"}]


def test_plancher_citations_a_relire_pour_plage_et_pour_absence_de_citation(tmp_path):
    q1, q2 = SAMPLE_TESTS[0]["question"], SAMPLE_TESTS[1]["question"]
    behaviors = {
        q1: [FakeResult("anthropic", reponse=_answer("4.1")), FakeResult("mistral", reponse=_answer("4.1", cite_extra="Articles 4.1 à 4.2"))],
        q2: [FakeResult("anthropic", reponse=_answer("4.2")), FakeResult("mistral", reponse="Réponse directe sans source")],
    }
    run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    report, _ = read_report(tmp_path)
    p = report["resume"]["mistral"]["plancher"]
    assert p["citations"] == "a_relire"
    assert len(p["plages_a_relire"]) == 1
    assert p["reponses_sans_citation"] == [SAMPLE_TESTS[1]["label"]]


def test_mesures_et_cout_partiel_jamais_presente_comme_complet(tmp_path):
    q = SAMPLE_TESTS[0]["question"]
    behaviors = {q: [FakeResult("anthropic", reponse=_answer("4.1")), FakeResult("mistral", reponse=_answer("4.1"), cout_usd=None)]}
    run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    report, _ = read_report(tmp_path)
    assert report["resume"]["mistral"]["mesures"]["cout_usd"] is None        # un appel sans tarif -> non disponible
    assert report["resume"]["anthropic"]["mesures"]["cout_usd"] == pytest.approx(0.04)   # 4 x 0.01
    assert report["resume"]["anthropic"]["mesures"]["latence_mediane_s"] == 1.5


# ─────────────────────────────────────────────
# Fichiers de sortie
# ─────────────────────────────────────────────

def test_nom_horodate_et_fichiers_json_et_md(tmp_path):
    run_main(tmp_path, ["--yes"])
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "upload_eval_20260925_101500.json", "upload_eval_20260925_101500.md",
    ]
    report, _ = read_report(tmp_path)
    assert report["en_tete"]["mode"] == "complet"
    assert report["en_tete"]["mistral_host"] == "api.eu.mistral.ai"
    assert report["en_tete"]["date_utc"].startswith("2026-09-25T10:15:00")
    assert report["interrompu"] is False


def test_creation_exclusive_ne_remplace_jamais_un_fichier_existant(tmp_path):
    existant = tmp_path / "upload_eval_20260925_101500.json"
    existant.write_text("CONTENU_A_PRESERVER", encoding="utf-8")
    run_main(tmp_path, ["--yes"])
    assert existant.read_text(encoding="utf-8") == "CONTENU_A_PRESERVER"
    assert (tmp_path / "upload_eval_20260925_101500_2.json").exists()


def test_le_markdown_donne_le_plancher_les_limites_et_jamais_de_score(tmp_path):
    run_main(tmp_path, ["--yes"])
    md = (tmp_path / "upload_eval_20260925_101500.md").read_text(encoding="utf-8")
    assert "Plancher go/no-go" in md
    assert "Ce n'est pas un score" in md
    assert "le verdict est humain" in md
    assert "AIDE À LA RELECTURE" in md
    assert "Question garde-fou" in md
    assert "1. Aucune panne technique" in md and "3. Aucune citation inventée" in md
    assert "/10" not in md and "%" not in md                    # aucune note ni pourcentage


def test_aucune_cle_dans_aucune_sortie_meme_si_une_reponse_la_contient(tmp_path):
    """Filet de sécurité : une valeur secrète qui atterrirait dans une réponse est masquée."""
    q = SAMPLE_TESTS[0]["question"]
    fuite = f"réponse [Article 4.1] avec {VALEUR_TEST_A} et {VALEUR_TEST_M}"
    behaviors = {q: [FakeResult("anthropic", reponse=fuite), FakeResult("mistral", reponse=fuite)]}
    _, lignes, _ = run_main(tmp_path, ["--yes"], make_runtime(api=FakeApi(behaviors=behaviors)))
    for fichier in tmp_path.iterdir():
        contenu = fichier.read_text(encoding="utf-8")
        assert VALEUR_TEST_A not in contenu and VALEUR_TEST_M not in contenu, fichier.name
    assert "[REDACTED]" in (tmp_path / "upload_eval_20260925_101500.json").read_text(encoding="utf-8")
    assert VALEUR_TEST_A not in "\n".join(lignes) and VALEUR_TEST_M not in "\n".join(lignes)


def test_redact_ignore_les_valeurs_trop_courtes():
    assert ev.redact("abc def", ["abc"]) == "abc def"
    assert ev.redact("xx SECRET-LONG-123 yy", ["SECRET-LONG-123"]) == "xx [REDACTED] yy"


def test_en_tete_sans_aucune_valeur_secrete(tmp_path):
    run_main(tmp_path, ["--yes"])
    _, fichier = read_report(tmp_path)
    contenu = fichier.read_text(encoding="utf-8")
    assert VALEUR_TEST_A not in contenu and VALEUR_TEST_M not in contenu
    assert "api_key" not in contenu.lower()


# ─────────────────────────────────────────────
# Vrais PDF (hors ligne, sans clé, sans modèle d'embedding)
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def references_reelles():
    import extract_chunks
    import upload_session

    refs = {}
    for doc in extract_chunks.DOCS:
        chemin = Path(doc["path"])
        upload_session.validate_pdf_constraints(chemin)
        chunks = upload_session.extract_and_chunk_pdf(chemin, source_doc_id="UPLOAD-test")
        lignes = extract_chunks.extract_text_from_pdf(chemin)
        refs[doc["source_doc"]] = ev.build_references(lignes, chunks)
    return refs


def test_pdf_reels_renvois_morts_et_externes_hors_definition(references_reelles):
    prev = references_reelles["CG-PREV-INV-2024"]
    assert "2.3" not in prev.definitions and "6.3" not in prev.definitions     # renvois vers des articles inexistants
    assert {"5.1", "7.2", "13.5", "20.3"} <= prev.definitions - prev.chapitres  # vraies sous-clauses
    assert "990" not in references_reelles["CG-AV-MULTI-2024"].definitions      # renvoi au CGI
    acpr = references_reelles["ACPR-REC-2024-12"]
    assert {"4.3", "6.3", "8.2"} <= acpr.definitions - acpr.chapitres
    bareme = references_reelles["BAR-IARD-2024-V2"]
    assert {"1.3.2", "3.1.5"} <= bareme.definitions - bareme.chapitres


def test_pdf_reels_un_article_cite_a_tort_est_detecte(references_reelles):
    prev = references_reelles["CG-PREV-INV-2024"]
    assert ev.classify_citation("2.3", prev) == "absent"      # « Article 2.3 » existe dans le texte mais pas comme article
    assert ev.classify_citation("4.1", prev) == "article"
    assert ev.classify_citation("5.1", prev) == "sous-clause"


def test_pdf_reels_les_articles_attendus_du_golden_set_existent(references_reelles):
    from test_retrieval import TESTS

    for test in TESTS:
        if test["expected_doc"] is None:
            continue
        refs = references_reelles[test["expected_doc"]]
        assert test["expected_article"] in refs.chapitres, test["label"]


def test_pdf_reels_aucun_pdf_du_corpus_n_est_rejete(references_reelles):
    assert set(references_reelles) == {
        "CG-PREV-INV-2024", "CG-AV-MULTI-2024", "BAR-IARD-2024-V2", "ACPR-REC-2024-12",
    }
    assert all(r.chapitres for r in references_reelles.values())


# ─────────────────────────────────────────────
# Le script ne modifie ni l'app ni le corpus
# ─────────────────────────────────────────────

def test_le_module_n_importe_pas_agent_au_chargement():
    code = f"import sys; sys.path.insert(0, {str(HERE)!r}); import eval_upload_engines; print('agent' in sys.modules)"
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=60,
                         env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})
    assert res.stdout.strip() == "False", res.stderr


def test_le_script_ne_supprime_jamais_le_pdf_d_entree():
    """Le PDF d'entrée est celui du corpus : le script n'appelle ni unlink ni remove ni rmtree."""
    source = (HERE / "eval_upload_engines.py").read_text(encoding="utf-8")
    for interdit in (".unlink(", "os.remove(", "shutil.rmtree", "os.unlink("):
        # unlink est toléré uniquement pour le nettoyage d'un fichier de résultat réservé.
        if interdit == ".unlink(":
            assert source.count(".unlink(") == 1 and "json_path.unlink(missing_ok=True)" in source
        else:
            assert interdit not in source

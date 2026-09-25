"""
Évaluation des deux moteurs (Claude, Mistral) sur le VRAI chemin upload — sous-lot 3.2.

Rejoue les questions du golden set (rattachées chacune à son document) plus la
question garde-fou (hors corpus) sur les 4 PDF fictifs du corpus, en passant par
upload_session comme le ferait un visiteur : verrou -> extraction -> découpage ->
embedding éphémère -> compare_engines_on_upload() -> libération du verrou.

Ce n'est PAS un score. Le critère est un plancher (go/no-go) :
  1. aucune panne technique ;
  2. garde-fou respecté (la réponse dit que l'information n'est pas dans le document) ;
  3. aucune citation inventée.
Seul le premier est entièrement automatique. Les deux autres sont une AIDE À LA
RELECTURE : le verdict est humain (sous-lot 3.2c).

Entrée : variables d'environnement UNIQUEMENT (ANTHROPIC_API_KEY, MISTRAL_API_KEY,
MISTRAL_MODEL ; MISTRAL_SERVER laissé à son défaut "eu"). Aucun fichier .env n'est
lu : load_dotenv est neutralisé avant l'import d'agent. Les clés ne sont jamais
affichées ni écrites — on ne teste que leur PRÉSENCE.

Usage (depuis la racine du dépôt, avec l'environnement virtuel du projet) :
    .venv/bin/python tests/eval_upload_engines.py --smoke          # résumé seul
    .venv/bin/python tests/eval_upload_engines.py --smoke --yes    # 1 question, appels réels
    .venv/bin/python tests/eval_upload_engines.py --yes            # run complet, appels réels

Sans --yes, aucun appel réel n'est effectué (le résumé est affiché, code de sortie 2).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import statistics
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
RESULTS_DIR = HERE / "results"

REQUIRED_ENV = ("ANTHROPIC_API_KEY", "MISTRAL_API_KEY", "MISTRAL_MODEL")
# Variables dont la VALEUR est secrète (le nom du modèle ne l'est pas).
SECRET_ENV = ("ANTHROPIC_API_KEY", "MISTRAL_API_KEY")

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_INTERRUPTED = 130

ENGINES = ("anthropic", "mistral")
GARDE_FOU_DOC = "CG-PREV-INV-2024"  # Q20 n'a pas d'expected_doc : "le contrat prévoyance"
SMOKE_DEFAULT = "Q01"
REQUIRED_SERVER = "eu"

# Estimation de coût AVANT le run : borne haute, HYPOTHÈSE non mesurée.
# 1500 = max_tokens de llm_call (vrai plafond de sortie). 8000 en entrée =
# 10 chunks <= 512 tokens e5 + prompt système, avec marge sur la tokenisation
# française. Le coût réel est recalculé en fin de run à partir des tokens mesurés.
EST_TOKENS_IN_PAR_APPEL = 8000
EST_TOKENS_OUT_PAR_APPEL = 1500

LIMITES_CITATIONS = (
    "Le contrôle automatique des citations est une AIDE À LA RELECTURE, pas un verdict : "
    "il établit qu'un numéro d'article cité EXISTE dans le document interrogé, pas que "
    "l'affirmation citée est exacte ni pertinente.",
    "\"absent\" ne veut pas dire \"inventé\" : ce peut être un renvoi légitime hors du "
    "document (ex. Article 990 du CGI), un renvoi mort du texte source, ou un format que "
    "la détection ne sait pas lire.",
    "Les plages (\"Articles 5 à 7\") sont signalées \"à relire\", pas développées. Une "
    "virgule suivie d'un nombre n'est lue comme une liste qu'après \"Articles\" au pluriel. "
    "Une citation sans le mot \"Article\" (ex. \"[Section 3]\") n'est pas détectée.",
    "La référence est calibrée sur ces 4 PDF (lignes commençant par \"Article N —\", "
    "glyphe \"n\" des sous-clauses) : valable ici, pas généralisable à un autre document.",
    "Les numéros d'articles se répètent d'un document à l'autre : chaque réponse est "
    "vérifiée contre le seul document réellement interrogé.",
)

# ─────────────────────────────────────────────
# Variables d'environnement (présence seulement)
# ─────────────────────────────────────────────


def missing_env(environ: dict[str, str]) -> list[str]:
    """Noms des variables requises absentes ou vides. Ne lit JAMAIS leur valeur au-delà de bool()."""
    return [nom for nom in REQUIRED_ENV if not environ.get(nom)]


def neutralize_dotenv() -> None:
    """
    agent.py appelle load_dotenv() à l'import (agent.py:27), ce qui lirait un .env.
    On le remplace par un no-op AVANT l'import : l'entrée est l'environnement du
    Terminal, rien d'autre.
    """
    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False


# ─────────────────────────────────────────────
# Citations : extraction et classement
# ─────────────────────────────────────────────

_NUM = r"\d+(?:\.\d+)*"
_PREFIX = r"(?:Articles?\s+|Art\.\s*)"
_LIST_SEP = r"(?:\s*[,;&]\s*|\s+et\s+)"
_RANGE_SEP = r"(?:\s+(?:à|au)\s+|(?<=\d)[-–](?=\d))"
_TAIL_ITEM = rf"(?:{_LIST_SEP}|{_RANGE_SEP})(?:{_PREFIX})?{_NUM}"
_CITATION_RE = re.compile(rf"\b{_PREFIX}({_NUM})((?:{_TAIL_ITEM})*)", re.IGNORECASE)
_NUM_RE = re.compile(_NUM)
_RANGE_SEP_RE = re.compile(_RANGE_SEP)
# Forme "définition" : une ligne du PDF qui COMMENCE par [glyphe n] "Article N —".
# Exclut les simples renvois internes au texte ("selon l'Article 6.3 …"). Le tiret
# est un cadratin/demi-cadratin, ou un trait d'union ENTRE ESPACES : un trait d'union
# collé au numéro est celui d'un renvoi légal ("Article 990-I du CGI").
_DEFINITION_RE = re.compile(rf"^\s*(?:n\s+)?Article\s+({_NUM})(?:\s*[—–]|\s+-\s)")


@dataclass
class Citations:
    numbers: list[str]   # numéros cités, dédoublonnés, dans l'ordre d'apparition
    plages: list[str]    # extraits de plages non développées ("Articles 5 à 7")


def extract_citations(text: str) -> Citations:
    """
    Numéros d'articles cités dans une réponse. Lit "Article 4.1", "Articles 4.3 et 6",
    "Art. 8". Les listes sont développées ; les plages ("5 à 7", "4.1-4.3") ne le sont
    pas : leurs bornes sont lues, la plage est signalée. Une virgule ne prolonge la
    citation qu'après "Articles" (pluriel), pour ne pas lire "Article 4, 30 jours"
    comme deux articles.
    """
    numbers: list[str] = []
    plages: list[str] = []
    pos = 0
    while True:
        m = _CITATION_RE.search(text, pos)
        if m is None:
            break
        pluriel = m.group(0).lower().startswith("articles")
        queue = m.group(2)
        fin = m.end()
        if not pluriel:
            coupe = re.search(r"[,;]", queue)
            if coupe:
                queue = queue[: coupe.start()]
                # Reprendre le balayage à la coupure : "Article 4, Article 2.3" contient
                # une seconde citation, qu'il ne faut pas avaler avec la première.
                fin = m.start(2) + coupe.start()
        candidats = [m.group(1)] + _NUM_RE.findall(queue)
        for nombre in candidats:
            if nombre not in numbers:
                numbers.append(nombre)
        # On cherche le séparateur sur "premier numéro + queue" : le lookbehind (?<=\d)
        # du tiret exige le chiffre qui le précède, absent de `queue` seul.
        if _RANGE_SEP_RE.search(m.group(1) + queue):
            plages.append((m.group(1) + queue).strip())
        pos = max(fin, m.start() + 1)
    return Citations(numbers=numbers, plages=plages)


@dataclass(frozen=True)
class DocReferences:
    chapitres: frozenset[str]     # A : article_num des chunks (articles "chapitre")
    definitions: frozenset[str]   # D : A + sous-clauses définies dans le texte (forme "Article N —")


def build_references(lines: list[str], chunks: list[dict]) -> DocReferences:
    chapitres = {
        c["metadata"]["article_num"] for c in chunks if c["metadata"].get("article_num")
    }
    definitions = set(chapitres)
    for ligne in lines:
        m = _DEFINITION_RE.match(ligne)
        if m:
            definitions.add(m.group(1))
    return DocReferences(frozenset(chapitres), frozenset(definitions))


def classify_citation(numero: str, refs: DocReferences) -> str:
    if numero in refs.chapitres:
        return "article"
    if numero in refs.definitions:
        return "sous-clause"
    return "absent"


# ─────────────────────────────────────────────
# Outils du golden set (injectés : import tardif, après les garde-fous)
# ─────────────────────────────────────────────


@dataclass
class GoldenTools:
    non_trouve: str
    blocs: list[str]
    verdict: Callable[[dict, str], tuple[bool, str]]
    check_format: Callable[[str], list[str]]


def analyse_answer(test: dict, refs: DocReferences, reponse: str, tools: GoldenTools) -> dict:
    """Contrôles d'UNE réponse. Aucune décision de fond : des signaux pour la relecture."""
    cit = extract_citations(reponse)
    classement = {n: classify_citation(n, refs) for n in cit.numbers}
    garde_fou_applicable = test["expected_article"] is None
    ok_hist, detail_hist = tools.verdict(test, reponse)
    refus = tools.non_trouve in reponse
    return {
        "articles_cites": cit.numbers,
        "classement": classement,
        "absents": [n for n, c in classement.items() if c == "absent"],
        "plages": cit.plages,
        "aucune_citation": (not cit.numbers) and not garde_fou_applicable,
        # Plus strict que verdict() : numéro EXACT cité, pas une sous-chaîne.
        "citation_attendue": (
            None if garde_fou_applicable else test["expected_article"] in cit.numbers
        ),
        "verdict_historique": {"ok": ok_hist, "detail": detail_hist},
        "blocs_manquants": tools.check_format(reponse),
        # Refus alors que l'information existe dans le document.
        "faux_negatif": bool(refus and not garde_fou_applicable),
        "garde_fou": (
            ("confirme" if refus else "a_relire") if garde_fou_applicable else None
        ),
    }


# ─────────────────────────────────────────────
# Plan d'évaluation : questions -> documents
# ─────────────────────────────────────────────


@dataclass
class DocumentSpec:
    doc_id: str
    path: Path
    questions: list[dict] = field(default_factory=list)


def question_code(test: dict) -> str:
    """'Q01 — Franchise ITT' -> 'Q01'."""
    return test["label"].split()[0]


def plan_documents(docs: list[dict], tests: list[dict], only: str | None = None) -> list[DocumentSpec]:
    """
    Rattache chaque question à son document (expected_doc ; Q20, sans expected_doc,
    va au contrat prévoyance). Ordre des documents = ordre de `docs`.
    `only` (code de question, ex. "Q01") ne garde que cette question.
    """
    par_doc = {d["source_doc"]: DocumentSpec(d["source_doc"], Path(d["path"])) for d in docs}
    if only is not None and only not in {question_code(t) for t in tests}:
        raise ValueError(f"question inconnue : {only!r}")
    for test in tests:
        if only is not None and question_code(test) != only:
            continue
        doc_id = test["expected_doc"] or GARDE_FOU_DOC
        if doc_id not in par_doc:
            raise ValueError(f"document inconnu pour {test['label']} : {doc_id}")
        par_doc[doc_id].questions.append(test)
    return [spec for spec in par_doc.values() if spec.questions]


# ─────────────────────────────────────────────
# Coût, résumé de démarrage
# ─────────────────────────────────────────────


def fmt_usd(valeur: float | None) -> str:
    return "non disponible" if valeur is None else f"{valeur:.2f} $".replace(".", ",")


def estimate_run_cost(n_questions: int, estimer: Callable[[int, int, str], float | None]) -> dict:
    """Borne haute par moteur et totale (None = tarif non disponible). HYPOTHÈSE, voir EST_*."""
    par_moteur: dict[str, float | None] = {}
    for moteur in ENGINES:
        unitaire = estimer(EST_TOKENS_IN_PAR_APPEL, EST_TOKENS_OUT_PAR_APPEL, moteur)
        par_moteur[moteur] = None if unitaire is None else unitaire * n_questions
    total = None if any(v is None for v in par_moteur.values()) else sum(par_moteur.values())
    return {"par_moteur": par_moteur, "total": total}


@dataclass
class Runtime:
    """Tout ce que le script tire d'agent/upload_session — injectable pour les tests."""

    claude_model: str
    mistral_model: str
    mistral_server: str
    mistral_host: str
    mistral_tarifs: tuple[float, float] | None
    estimer: Callable[[int, int, str], float | None]
    docs: list[dict]
    tests: list[dict]
    tools: GoldenTools
    api: Any
    configure_logging: Callable[[], None]
    versions: dict[str, str] = field(default_factory=dict)


def format_startup_summary(rt: Runtime, specs: list[DocumentSpec], smoke: bool, cout: dict) -> str:
    n_q = sum(len(s.questions) for s in specs)
    tarif = (
        f"tarifé ({rt.mistral_tarifs[0]:.2f} $ / {rt.mistral_tarifs[1]:.2f} $ par million de tokens)"
        if rt.mistral_tarifs
        else "NON TARIFÉ (coût Mistral « non disponible »)"
    )
    lignes = [
        "=== Évaluation Claude / Mistral sur le chemin upload ===",
        f"Mode                 : {'FUMÉE (1 question)' if smoke else 'run complet'}",
        f"Modèle Claude        : {rt.claude_model}",
        f"Modèle Mistral       : {rt.mistral_model}",
        f"Endpoint Mistral     : serveur « {rt.mistral_server} » -> {rt.mistral_host}",
        f"Tarif Mistral        : {tarif}",
        f"Documents            : {len(specs)}",
        f"Questions            : {n_q}",
        f"Appels réels prévus  : {n_q * len(ENGINES)}  ({len(ENGINES)} moteurs x {n_q} question{'s' if n_q > 1 else ''})",
        "Coût estimé (BORNE HAUTE, hypothèse non mesurée : "
        f"{EST_TOKENS_IN_PAR_APPEL} tokens en entrée + {EST_TOKENS_OUT_PAR_APPEL} en sortie par appel) :",
        f"    Claude  : {fmt_usd(cout['par_moteur']['anthropic'])}",
        f"    Mistral : {fmt_usd(cout['par_moteur']['mistral'])}",
        f"    Total   : {fmt_usd(cout['total'])}",
        "Le coût réel est recalculé en fin de run à partir des tokens mesurés.",
    ]
    return "\n".join(lignes)


# ─────────────────────────────────────────────
# Capture des logs de l'app (type/status_code d'erreur, request_id) — sans toucher au code de l'app
# ─────────────────────────────────────────────

_RE_ENGINE_ERROR = re.compile(r"COMPARE_ENGINE_ERROR moteur=(\S+) type=(\S+) status_code=(\S+)")
_RE_REQUEST_ID = re.compile(r"LLM_CALL .*?request_id=(\S+)")


class LogCapture(logging.Handler):
    """
    Récupère deux informations que EngineResult ne porte pas : le type et le
    status_code de l'exception d'un moteur en échec (log COMPARE_ENGINE_ERROR de
    upload_session) et l'identifiant de requête Mistral (log d'audit LLM_CALL).
    Ne lit que ces champs ; jamais de contenu de question ni de réponse.
    """

    LOGGERS = ("upload_session", "audit_llm")

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self._lock = threading.Lock()
        self._erreurs: dict[str, dict] = {}
        self._request_ids: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        m = _RE_ENGINE_ERROR.search(message)
        if m:
            with self._lock:
                self._erreurs[m.group(1)] = {"type": m.group(2), "status_code": m.group(3)}
            return
        m = _RE_REQUEST_ID.search(message)
        if m:
            with self._lock:
                self._request_ids.append(m.group(1))

    def install(self) -> None:
        for nom in self.LOGGERS:
            logging.getLogger(nom).addHandler(self)

    def uninstall(self) -> None:
        for nom in self.LOGGERS:
            logging.getLogger(nom).removeHandler(self)

    def take(self) -> tuple[dict[str, dict], list[str]]:
        with self._lock:
            erreurs, ids = dict(self._erreurs), list(self._request_ids)
            self._erreurs.clear()
            self._request_ids.clear()
        return erreurs, ids


# ─────────────────────────────────────────────
# Fichiers de sortie
# ─────────────────────────────────────────────


def redact(texte: str, secrets: list[str]) -> str:
    """Filet de sécurité : si une valeur secrète se retrouvait dans une sortie, elle est masquée."""
    for secret in secrets:
        if len(secret) >= 8:
            texte = texte.replace(secret, "[REDACTED]")
    return texte


class ResultsWriter:
    """
    Un fichier par run, horodaté (UTC). Les deux fichiers (.json et .md) sont RÉSERVÉS en
    création exclusive : un fichier existant n'est jamais remplacé. Ensuite le .json est
    réécrit de façon atomique (fichier temporaire + os.replace) après chaque question :
    une interruption ou un plantage laisse un fichier exploitable.
    """

    def __init__(self, json_path: Path, md_path: Path, secrets: list[str]) -> None:
        self.json_path = json_path
        self.md_path = md_path
        self._secrets = secrets

    @classmethod
    def reserve(cls, directory: Path, stamp: str, smoke: bool, secrets: list[str]) -> "ResultsWriter":
        directory.mkdir(parents=True, exist_ok=True)
        base = f"upload_eval_{stamp}{'_smoke' if smoke else ''}"
        for suffixe in [""] + [f"_{i}" for i in range(2, 20)]:
            json_path = directory / f"{base}{suffixe}.json"
            md_path = directory / f"{base}{suffixe}.md"
            try:
                with open(json_path, "x", encoding="utf-8") as f:
                    f.write("{}")
            except FileExistsError:
                continue
            try:
                with open(md_path, "x", encoding="utf-8") as f:
                    f.write("")
            except FileExistsError:
                json_path.unlink(missing_ok=True)
                continue
            return cls(json_path, md_path, secrets)
        raise FileExistsError(f"impossible de réserver un nom de fichier pour {base}")

    def _atomic_write(self, chemin: Path, contenu: str) -> None:
        contenu = redact(contenu, self._secrets)
        tmp = chemin.with_name(chemin.name + ".tmp")
        tmp.write_text(contenu, encoding="utf-8")
        os.replace(tmp, chemin)

    def write_json(self, report: dict) -> None:
        self._atomic_write(self.json_path, json.dumps(report, ensure_ascii=False, indent=2))

    def write_markdown(self, texte: str) -> None:
        self._atomic_write(self.md_path, texte)


# ─────────────────────────────────────────────
# Déroulé
# ─────────────────────────────────────────────


@dataclass
class IngestInfo:
    n_chunks: int
    n_tronques: int
    refs: DocReferences


def _engine_record(res: Any, analyse: dict | None, erreur_log: dict | None, request_id: str | None) -> dict:
    return {
        "succes": bool(res.succes),
        "reponse": res.reponse,
        "erreur": res.erreur,
        "erreur_type": (erreur_log or {}).get("type"),
        "erreur_status_code": (erreur_log or {}).get("status_code"),
        "tokens_in": res.tokens_in,
        "tokens_out": res.tokens_out,
        "cout_usd": res.cout_usd,
        "latence_s": round(res.latence_s, 3),
        "request_id": request_id,
        "analyse": analyse,
    }


def evaluate_question(
    api: Any,
    session_id: str,
    test: dict,
    doc_id: str,
    refs: DocReferences,
    tools: GoldenTools,
    capture: LogCapture | None,
) -> dict:
    """UNE question, les deux moteurs. Ne lève jamais (sauf KeyboardInterrupt)."""
    if capture:
        capture.take()  # purge : ne garder que les logs de CETTE question
    enregistrement: dict = {
        "label": test["label"],
        "question": test["question"],
        "doc": doc_id,
        "expected_article": test["expected_article"],
        "garde_fou": test["expected_article"] is None,
        "moteurs": {},
        "erreur_globale": None,
    }
    try:
        resultats = api.compare(session_id, test["question"])
    except Exception as exc:  # noqa: BLE001 — une question en échec ne doit pas arrêter le run
        # Le TYPE seul : le message d'une exception interne n'a rien à faire dans un fichier de résultats.
        enregistrement["erreur_globale"] = {"type": type(exc).__name__}
        return enregistrement

    erreurs_log, request_ids = capture.take() if capture else ({}, [])
    for res in resultats:
        analyse = None
        if res.succes and res.reponse:
            analyse = analyse_answer(test, refs, res.reponse, tools)
        request_id = (request_ids[-1] if request_ids else None) if res.engine == "mistral" else None
        enregistrement["moteurs"][res.engine] = _engine_record(
            res, analyse, erreurs_log.get(res.engine), request_id
        )
    return enregistrement


def _mark_not_evaluated(spec: DocumentSpec, raison: str, erreur_type: str) -> list[dict]:
    return [
        {
            "label": t["label"],
            "question": t["question"],
            "doc": spec.doc_id,
            "expected_article": t["expected_article"],
            "garde_fou": t["expected_article"] is None,
            "moteurs": {},
            "erreur_globale": {"type": erreur_type, "etape": raison},
        }
        for t in spec.questions
    ]


def run_evaluation(
    api: Any,
    specs: list[DocumentSpec],
    report: dict,
    writer: ResultsWriter,
    tools: GoldenTools,
    capture: LogCapture | None,
    out: Callable[[str], None] = print,
) -> dict:
    """
    Boucle documents -> questions. Ne s'arrête pas au premier échec. Le verrou upload
    est libéré dans un `finally` : succès, exception d'ingestion, exception de
    comparaison ET Ctrl+C (KeyboardInterrupt traverse le finally puis remonte à main()).
    Le fichier JSON est réécrit après chaque question.
    """
    for spec in specs:
        session_id = f"eval-{uuid.uuid4().hex[:8]}"
        try:
            api.acquire(session_id)
        except Exception as exc:  # noqa: BLE001
            out(f"[{spec.doc_id}] verrou indisponible ({type(exc).__name__}) : questions non évaluées")
            report["resultats"].extend(_mark_not_evaluated(spec, "acquisition", type(exc).__name__))
            writer.write_json(report)
            continue
        try:
            try:
                info = api.ingest(session_id, spec.path)
            except Exception as exc:  # noqa: BLE001
                out(f"[{spec.doc_id}] ingestion refusée ({type(exc).__name__}) : questions non évaluées")
                report["resultats"].extend(_mark_not_evaluated(spec, "ingestion", type(exc).__name__))
                report["documents"][spec.doc_id] = {"ingestion_erreur": type(exc).__name__}
                writer.write_json(report)
                continue
            report["documents"][spec.doc_id] = {
                "chunks": info.n_chunks,
                "chunks_tronques_512_tokens": info.n_tronques,
                "articles_chapitre": sorted(info.refs.chapitres),
                "articles_definis": sorted(info.refs.definitions),
            }
            out(f"[{spec.doc_id}] ingéré : {info.n_chunks} chunks, {info.n_tronques} tronqué(s)")
            for test in spec.questions:
                api.touch(session_id)
                enreg = evaluate_question(api, session_id, test, spec.doc_id, info.refs, tools, capture)
                report["resultats"].append(enreg)
                writer.write_json(report)
                out(_progress_line(enreg))
        finally:
            try:
                api.release(session_id)
            except Exception as exc:  # noqa: BLE001 — ne jamais masquer l'erreur d'origine
                out(f"[{spec.doc_id}] libération du verrou : {type(exc).__name__}")
    return report


def _progress_line(enreg: dict) -> str:
    """Une ligne de suivi par question : statut, latence, tokens. Jamais de contenu de réponse."""
    if enreg["erreur_globale"]:
        return f"  {enreg['label']} : ERREUR GLOBALE ({enreg['erreur_globale']['type']})"
    morceaux = []
    for moteur in ENGINES:
        m = enreg["moteurs"].get(moteur)
        if m is None:
            morceaux.append(f"{moteur}=absent")
        elif m["succes"]:
            morceaux.append(f"{moteur}=ok {m['latence_s']:.1f}s {m['tokens_in']}+{m['tokens_out']}tok")
        else:
            morceaux.append(f"{moteur}=ECHEC({m['erreur_type'] or '?'})")
    return f"  {enreg['label']} : " + " | ".join(morceaux)


# ─────────────────────────────────────────────
# Résumé : le plancher, sans le maquiller en score
# ─────────────────────────────────────────────


def engine_floor(resultats: list[dict], moteur: str, n_attendus: int) -> dict:
    evalues = [r for r in resultats if not r["erreur_globale"] and moteur in r["moteurs"]]
    succes = [r for r in evalues if r["moteurs"][moteur]["succes"]]
    pannes = [r["label"] for r in resultats if r["erreur_globale"] or not r["moteurs"].get(moteur, {}).get("succes")]
    technique = "atteint" if n_attendus > 0 and len(succes) == n_attendus and not pannes else "non_atteint"

    q_garde_fou = [r for r in resultats if r["garde_fou"]]
    if not q_garde_fou:
        garde_fou = "non_applicable"  # Q20 non exécutée (fumée sur une autre question)
    else:
        m = q_garde_fou[0]["moteurs"].get(moteur)
        if not m or not m["succes"]:
            garde_fou = "non_atteint"
        else:
            garde_fou = m["analyse"]["garde_fou"] if m["analyse"] else "non_atteint"

    absents, plages, sans_citation = [], [], []
    for r in succes:
        analyse = r["moteurs"][moteur]["analyse"]
        if not analyse:
            continue
        for numero in analyse["absents"]:
            absents.append({"question": r["label"], "article": numero})
        for plage in analyse["plages"]:
            plages.append({"question": r["label"], "plage": plage})
        if analyse["aucune_citation"]:
            sans_citation.append(r["label"])
    citations = "aucune_citation_absente" if not (absents or plages or sans_citation) else "a_relire"
    return {
        "technique": technique,
        "pannes": pannes,
        "garde_fou": garde_fou,
        "citations": citations,
        "citations_absentes": absents,
        "plages_a_relire": plages,
        "reponses_sans_citation": sans_citation,
    }


def engine_measures(resultats: list[dict], moteur: str) -> dict:
    ok = [r["moteurs"][moteur] for r in resultats if moteur in r["moteurs"] and r["moteurs"][moteur]["succes"]]
    latences = [m["latence_s"] for m in ok]
    couts = [m["cout_usd"] for m in ok]
    return {
        "appels_reussis": len(ok),
        "latence_mediane_s": round(statistics.median(latences), 3) if latences else None,
        "latence_max_s": round(max(latences), 3) if latences else None,
        "tokens_in": sum(m["tokens_in"] for m in ok),
        "tokens_out": sum(m["tokens_out"] for m in ok),
        # None dès qu'un appel n'a pas de tarif : jamais un total partiel présenté comme complet.
        "cout_usd": None if (not ok or any(c is None for c in couts)) else round(sum(couts), 4),
    }


def build_summary(report: dict) -> dict:
    n_attendus = report["n_questions"]
    resultats = report["resultats"]
    return {
        moteur: {
            "plancher": engine_floor(resultats, moteur, n_attendus),
            "mesures": engine_measures(resultats, moteur),
        }
        for moteur in ENGINES
    }


_LIBELLES = {
    "technique": {"atteint": "ATTEINT", "non_atteint": "NON ATTEINT"},
    "garde_fou": {
        "confirme": "confirmé automatiquement (formule de refus présente) — relire quand même",
        "a_relire": "À RELIRE (formule exacte absente : refus paraphrasé ou réponse inventée ?)",
        "non_atteint": "NON ATTEINT (pas de réponse exploitable)",
        "non_applicable": "non évalué (question garde-fou non exécutée)",
    },
    "citations": {
        "aucune_citation_absente": "aucune citation absente du document (n'établit pas que les affirmations sont exactes)",
        "a_relire": "À RELIRE",
    },
}


def render_markdown(report: dict) -> str:
    resume = report["resume"]
    h = report["en_tete"]
    lignes = [
        f"# Évaluation Claude / Mistral — chemin upload ({h['mode']})",
        "",
        f"- Date (UTC) : {h['date_utc']}" + ("  — **RUN INTERROMPU**" if report.get("interrompu") else ""),
        f"- Modèle Claude : `{h['claude_model']}`",
        f"- Modèle Mistral : `{h['mistral_model']}` — serveur `{h['mistral_server']}` ({h['mistral_host']})",
        f"- Questions : {report['n_questions']} · appels réels prévus : {report['n_questions'] * len(ENGINES)}",
        "",
        "## Plancher go/no-go, par moteur",
        "",
        "Ce n'est pas un score. Le contrôle automatique aide à relire ; **le verdict est humain (3.2c)**.",
        "",
        "| Critère | Claude | Mistral |",
        "|---|---|---|",
    ]
    for cle, titre in (("technique", "1. Aucune panne technique"), ("garde_fou", "2. Garde-fou respecté"), ("citations", "3. Aucune citation inventée")):
        cellules = [_LIBELLES[cle][resume[m]["plancher"][cle]] for m in ENGINES]
        lignes.append(f"| {titre} | {cellules[0]} | {cellules[1]} |")
    lignes += ["", "## À relire", ""]
    a_relire = False
    for moteur in ENGINES:
        p = resume[moteur]["plancher"]
        for panne in p["pannes"]:
            lignes.append(f"- **{moteur}** — panne technique : {panne}")
            a_relire = True
        for item in p["citations_absentes"]:
            lignes.append(f"- **{moteur}** — {item['question']} : article « {item['article']} » cité mais absent du document")
            a_relire = True
        for item in p["plages_a_relire"]:
            lignes.append(f"- **{moteur}** — {item['question']} : plage non développée « {item['plage']} »")
            a_relire = True
        for label in p["reponses_sans_citation"]:
            lignes.append(f"- **{moteur}** — {label} : aucune citation détectée")
            a_relire = True
    if not a_relire:
        lignes.append("- Rien de signalé automatiquement (ce qui n'établit pas que tout est correct).")
    garde_fou = [r for r in report["resultats"] if r["garde_fou"]]
    if garde_fou:
        lignes += ["", "## Question garde-fou (réponses complètes, à lire)", ""]
        for r in garde_fou:
            lignes.append(f"**{r['label']}** — {r['question']}")
            for moteur in ENGINES:
                m = r["moteurs"].get(moteur)
                texte = (m or {}).get("reponse") or f"(pas de réponse : {(m or {}).get('erreur') or r['erreur_globale']})"
                lignes += ["", f"*{moteur}* :", "", "> " + texte.replace("\n", "\n> "), ""]
    lignes += ["## Mesures", "", "| | Claude | Mistral |", "|---|---|---|"]
    m_a, m_m = resume["anthropic"]["mesures"], resume["mistral"]["mesures"]
    lignes.append(f"| Appels réussis | {m_a['appels_reussis']} | {m_m['appels_reussis']} |")
    lignes.append(f"| Latence médiane (s) | {m_a['latence_mediane_s']} | {m_m['latence_mediane_s']} |")
    lignes.append(f"| Latence max (s) | {m_a['latence_max_s']} | {m_m['latence_max_s']} |")
    lignes.append(f"| Tokens entrée / sortie | {m_a['tokens_in']} / {m_a['tokens_out']} | {m_m['tokens_in']} / {m_m['tokens_out']} |")
    lignes.append(f"| Coût mesuré | {fmt_usd(m_a['cout_usd'])} | {fmt_usd(m_m['cout_usd'])} |")
    lignes += ["", "## Limites du contrôle automatique", ""]
    lignes += [f"{i}. {texte}" for i, texte in enumerate(LIMITES_CITATIONS, 1)]
    lignes += ["", f"Détail complet (réponses, citations, latences, tokens) : `{Path(report['fichier_json']).name}`", ""]
    return "\n".join(lignes)


def finalize(report: dict, writer: ResultsWriter, interrompu: bool) -> None:
    report["interrompu"] = interrompu
    report["resume"] = build_summary(report)
    writer.write_json(report)
    writer.write_markdown(render_markdown(report))


# ─────────────────────────────────────────────
# Runtime réel (imports lourds, APRÈS les garde-fous)
# ─────────────────────────────────────────────


class UploadApi:
    """Séquence de app.py:388-408 (dépôt) et :490-494 (question), sans Streamlit."""

    def __init__(self, upload_session: Any, extract_chunks: Any) -> None:
        self._us = upload_session
        self._extract = extract_chunks
        self._handles: dict[str, Any] = {}

    def acquire(self, session_id: str) -> None:
        self._handles[session_id] = self._us.try_acquire(session_id)

    def ingest(self, session_id: str, path: Path) -> IngestInfo:
        handle = self._handles[session_id]
        self._us.validate_pdf_constraints(path)
        chunks = self._us.extract_and_chunk_pdf(path, source_doc_id=f"UPLOAD-{session_id[:8]}")
        chunks, avertissements = self._us.apply_length_guard(chunks)
        self._us.embed_and_index(handle.collection, chunks)
        lignes = self._extract.extract_text_from_pdf(path)
        return IngestInfo(len(chunks), len(avertissements), build_references(lignes, chunks))

    def touch(self, session_id: str) -> None:
        self._us.touch(session_id)

    def compare(self, session_id: str, question: str) -> list:
        return self._us.compare_engines_on_upload(self._handles[session_id].collection, question)

    def release(self, session_id: str) -> None:
        # Le PDF d'entrée n'est JAMAIS supprimé : c'est le PDF du corpus.
        try:
            self._us.release(session_id)
        finally:
            self._handles.pop(session_id, None)


def _package_version(nom: str) -> str:
    from importlib import metadata

    try:
        return metadata.version(nom)
    except metadata.PackageNotFoundError:
        return "inconnue"


def real_runtime() -> Runtime:
    """
    Ordre imposé : HF hors ligne, .env neutralisé, PUIS import d'agent (dont les constantes
    MISTRAL_MODEL / MISTRAL_SERVER / CLAUDE_MODEL sont figées à l'import).
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    neutralize_dotenv()
    for chemin in (str(SRC), str(HERE)):
        if chemin not in sys.path:
            sys.path.insert(0, chemin)
    import agent  # noqa: E402
    import extract_chunks  # noqa: E402
    import upload_session  # noqa: E402
    import test_golden_set  # noqa: E402
    from test_retrieval import TESTS  # noqa: E402

    tools = GoldenTools(
        non_trouve=test_golden_set.NON_TROUVE,
        blocs=list(test_golden_set.BLOCS),
        verdict=test_golden_set.verdict,
        check_format=test_golden_set.check_format,
    )
    return Runtime(
        claude_model=agent.CLAUDE_MODEL,
        mistral_model=agent.MISTRAL_MODEL or "",
        mistral_server=agent.MISTRAL_SERVER,
        mistral_host=agent.mistral_endpoint_host(),
        mistral_tarifs=agent.mistral_tarifs_usd_par_mtok(),
        estimer=agent.estimer_cout_usd,
        docs=list(extract_chunks.DOCS),
        tests=list(TESTS),
        tools=tools,
        api=UploadApi(upload_session, extract_chunks),
        configure_logging=agent.configure_stdout_logging,
        versions={
            "python": sys.version.split()[0],
            "mistralai": _package_version("mistralai"),
            "anthropic": _package_version("anthropic"),
        },
    )


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Évalue Claude et Mistral sur le chemin upload (sous-lot 3.2).",
    )
    p.add_argument("--yes", action="store_true", help="confirme les appels réels (sans lui : résumé seul, aucun appel)")
    p.add_argument(
        "--smoke", nargs="?", const=SMOKE_DEFAULT, default=None, metavar="QUESTION",
        help=f"une seule question (défaut {SMOKE_DEFAULT}, ex. --smoke Q20)",
    )
    p.add_argument("--out-dir", default=str(RESULTS_DIR), help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    environ: dict[str, str] | None = None,
    out: Callable[[str], None] = print,
    loader: Callable[[], Runtime] = real_runtime,
    now: Callable[[], datetime] | None = None,
) -> int:
    args = parse_args(argv)
    environ = os.environ if environ is None else environ

    # 1. Présence des variables — AVANT tout import lourd. Noms seulement.
    manquantes = missing_env(environ)
    if manquantes:
        out("Variables d'environnement manquantes : " + ", ".join(manquantes))
        out("Le script ne lit que l'environnement (aucun .env). Rien n'a été appelé.")
        return EXIT_REFUSED

    # 2. Imports (dotenv neutralisé) : une MISTRAL_SERVER invalide fait échouer l'import d'agent.
    try:
        rt = loader()
    except ValueError as exc:
        out(f"Configuration invalide : {exc}")
        return EXIT_REFUSED

    # 3. L'objectif du 3.2 est l'endpoint UE.
    if rt.mistral_server != REQUIRED_SERVER:
        out(
            f"Refus : MISTRAL_SERVER résolu = « {rt.mistral_server} », attendu « {REQUIRED_SERVER} » "
            "(endpoint UE). Laisser la variable non définie ou à « eu »."
        )
        return EXIT_REFUSED

    # 4. Plan, résumé, confirmation.
    smoke = args.smoke is not None
    try:
        specs = plan_documents(rt.docs, rt.tests, only=args.smoke)
    except ValueError as exc:
        out(f"Plan invalide : {exc}")
        return EXIT_REFUSED
    n_questions = sum(len(s.questions) for s in specs)
    cout = estimate_run_cost(n_questions, rt.estimer)
    out(format_startup_summary(rt, specs, smoke, cout))
    if not args.yes:
        out("")
        out("Aucun appel effectué. Relancer avec --yes pour confirmer les appels réels.")
        return EXIT_REFUSED

    # 5. Run.
    rt.configure_logging()
    capture = LogCapture()
    capture.install()
    horodatage = (now or (lambda: datetime.now(timezone.utc)))()
    secrets = [environ[n] for n in SECRET_ENV if environ.get(n)]
    writer = ResultsWriter.reserve(Path(args.out_dir), horodatage.strftime("%Y%m%d_%H%M%S"), smoke, secrets)
    report = {
        "fichier_json": str(writer.json_path),
        "en_tete": {
            "date_utc": horodatage.isoformat(timespec="seconds"),
            "mode": "fumée" if smoke else "complet",
            "claude_model": rt.claude_model,
            "mistral_model": rt.mistral_model,
            "mistral_server": rt.mistral_server,
            "mistral_host": rt.mistral_host,
            "mistral_tarifs_usd_par_mtok": list(rt.mistral_tarifs) if rt.mistral_tarifs else None,
            "cout_estime_borne_haute_usd": cout,
            "versions": rt.versions,
        },
        "n_questions": n_questions,
        "documents": {},
        "resultats": [],
        "interrompu": False,
    }
    interrompu = False
    try:
        run_evaluation(rt.api, specs, report, writer, rt.tools, capture, out=out)
    except KeyboardInterrupt:
        interrompu = True
        out("Interrompu (Ctrl+C) : verrou libéré, résultats partiels conservés.")
    finally:
        capture.uninstall()
        finalize(report, writer, interrompu)
    out(f"Résultats : {writer.json_path}")
    out(f"Résumé    : {writer.md_path}")
    return EXIT_INTERRUPTED if interrompu else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

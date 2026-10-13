"""
Juge LLM hors ligne (lot C) : Gemini sur Vertex AI note la fidélité au contrat
des 40 réponses du 25/09/2026 (tests/results/upload_eval_20260925_104952.json)
et des 10 copies piégées (tests/judge/pieges.json), soit 50 jugements.

Chaque élément est jugé contre le CONTRAT ENTIER du document interrogé
(tests/judge/contrats/<doc>.json), selon la grille (tests/judge/grille.md)
reprise dans le prompt versionné tests/judge/prompt_juge.md.

À l'aveugle : le prompt ne contient ni le nom ni le fournisseur du moteur, ni
code de question, ni aucune indication qu'un élément est piégé. L'ordre est
mélangé (graine fixe) ; la correspondance id interne -> élément n'est écrite
que dans les résultats. Un contrôle refuse le lancement si un terme interdit
apparaît dans un prompt.

Entrée : variables d'environnement UNIQUEMENT (aucun .env lu) :
    GOOGLE_CLOUD_PROJECT  projet Google Cloud (jamais écrit dans les résultats)
    JUDGE_LOCATION        région UE (liste fermée ; « global » refusé)
    JUDGE_MODEL           modèle du juge (aucune valeur par défaut)
Authentification : Application Default Credentials (aucune clé lue).

Garde-fous (calqués sur tests/eval_upload_engines.py) : variables manquantes ->
refus ; vrai appel seulement avec --yes ET JUDGE_ALLOW_REAL=1 ; plafond dur
d'appels ; coût estimé affiché avant lancement ; fichiers de résultats en
création exclusive, écriture atomique, secrets masqués.

Usage (depuis la racine du dépôt, après `uv pip install --python .venv/bin/python
-r requirements-eval.txt`) :
    .venv/bin/python tests/judge/judge_upload_answers.py --smoke          # résumé seul
    JUDGE_ALLOW_REAL=1 .venv/bin/python tests/judge/judge_upload_answers.py --smoke --yes
    JUDGE_ALLOW_REAL=1 .venv/bin/python tests/judge/judge_upload_answers.py --yes
    ... --repetitions 2   # stabilité du juge (100 jugements)

Sans --yes ET JUDGE_ALLOW_REAL=1, aucun appel réel (résumé affiché, code de sortie 2).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
ROOT = TESTS.parent
RESULTS_DIR = TESTS / "results"
REFERENCE_RUN = RESULTS_DIR / "upload_eval_20260925_104952.json"
PIEGES = HERE / "pieges.json"
CONTRATS_DIR = HERE / "contrats"
PROMPT = HERE / "prompt_juge.md"
GRILLE = HERE / "grille.md"
MARQUEUR_PROMPT = "<!-- ===== DÉBUT DU PROMPT ENVOYÉ AU JUGE ===== -->"

if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from eval_upload_engines import ResultsWriter, fmt_usd, neutralize_dotenv  # noqa: E402

REQUIRED_ENV = ("GOOGLE_CLOUD_PROJECT", "JUDGE_LOCATION", "JUDGE_MODEL")
ALLOW_REAL_ENV = "JUDGE_ALLOW_REAL"
# Une clé API Google ferait passer le SDK à une autre méthode d'authentification
# (et, sans projet explicite, à l'endpoint global) : refus, ADC uniquement.
CLES_API_INTERDITES = ("GOOGLE_API_KEY", "GEMINI_API_KEY")
# Valeurs masquées par sécurité si elles se retrouvaient dans une sortie.
SECRET_ENV = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "MISTRAL_API_KEY")

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_INTERRUPTED = 130

MOTEURS = ("anthropic", "mistral")

# Régions UE acceptées. « global » n'engage sur aucun lieu de traitement ;
# europe-west2 (Royaume-Uni) et europe-west6 (Suisse) sont hors UE.
# Source : https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/data-residency
# (consultée le 13/10/2026, mise à jour du 09/10/2026).
LOCATIONS_UE = ("eu", "europe-west1", "europe-west3", "europe-west4", "europe-west9")
LOCATIONS_MULTI_REGION = ("eu",)


def traitement(location: str) -> str:
    """Lieu de traitement annoncé. Jamais un pays : la documentation n'en garantit aucun ici."""
    if location == "eu":
        return "traité dans l'UE (multi-région eu, pays non précisé)"
    return f"traité dans l'UE (région {location}, pays non précisé)"


def endpoint_attendu(location: str) -> str:
    """URL de base que le SDK google-genai 2.25.0 construit pour cette région (_api_client.py)."""
    if location in LOCATIONS_MULTI_REGION:
        return f"https://aiplatform.{location}.rep.googleapis.com/"
    return f"https://{location}-aiplatform.googleapis.com/"


@dataclass(frozen=True)
class Tarif:
    entree: float               # USD par million de tokens
    sortie: float               # USD par million de tokens (réponse + raisonnement)
    valable_jusqu_au: date | None
    note: str


TARIF_SOURCE = "https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing"
TARIF_CONSULTE_LE = "13/10/2026"
# Tarifs propres au juge (agent.estimer_cout_usd ne connaît qu'anthropic et mistral).
# Ligne « Non-global » (endpoints régionaux et multi-région), prix catalogue, sans
# le crédit promotionnel de 50 % mentionné en note de la page. La sortie est
# « Text output (response and reasoning) » : le raisonnement est facturé comme la sortie.
TARIFS_JUGE: dict[str, Tarif] = {
    "gemini-3.8-flash": Tarif(
        entree=0.825,
        sortie=4.125,
        valable_jusqu_au=date(2026, 12, 31),
        note=(
            "tarif promotionnel jusqu'au 31/12/2026 (1,65 $ / 8,25 $ à partir du 01/01/2027) ; "
            "aucune date de retrait publiée pour ce modèle (page modèle consultée le 13/10/2026)"
        ),
    ),
}

GRAINE_JUGE = 20261013
TEMPERATURE = 0.0
TEMPERATURE_NOTE = (
    "demandée à 0, probablement sans effet : la documentation Gemini 3 indique que "
    "temperature n'est plus recommandé et qu'il est ignoré par le modèle"
)
THINKING_LEVEL = "MEDIUM"  # valeur par défaut documentée de Gemini 3, rendue explicite
MAX_OUTPUT_TOKENS = 8192
TIMEOUT_MS = 120_000
MAX_REPETITIONS = 2
REESSAIS_PAR_ELEMENT = 1    # erreurs techniques seulement (exception, réponse vide)
REESSAIS_MAX = 10           # plafond = jugements + min(10, jugements) : 60 pour 50, 110 pour 100
DELAI_REESSAI_S = 5.0
# Estimation AVANT le run (borne haute, hypothèse) : 1 token pour 3 caractères en
# entrée, MAX_OUTPUT_TOKENS en sortie. Le coût réel est recalculé avec les tokens mesurés.
CARACTERES_PAR_TOKEN_BORNE = 3

TERMES_INTERDITS = re.compile(r"claude|anthropic|sonnet|mistral|pi[èe]g|\bP(?:0[1-9]|10)\b", re.IGNORECASE)

VERDICTS = {
    "C1": ("oui", "non"),
    "C2": ("oui", "non", "sans objet"),
    "C3": ("oui", "non", "sans objet"),
}


# ─────────────────────────────────────────────
# Éléments jugés et prompts
# ─────────────────────────────────────────────


@dataclass
class Element:
    id_interne: str
    source: str                 # "origine" | "piege"
    question_id: str
    moteur: str
    doc: str
    question: str
    reponse: str
    piege_id: str | None = None
    critere_vise: str | None = None
    verdict_attendu: dict | None = None

    def correspondance(self) -> dict:
        d = asdict(self)
        d.pop("question")
        d.pop("reponse")
        return d


def charger_elements(run: dict, pieges: list[dict]) -> list[Element]:
    """Les 40 réponses d'origine + les 10 pièges, mélangés (graine fixe), ids J01…"""
    elements = []
    for r in run["resultats"]:
        for moteur in MOTEURS:
            elements.append(Element(
                id_interne="", source="origine", question_id=r["label"].split()[0], moteur=moteur,
                doc=r["doc"], question=r["question"],
                reponse=(r["moteurs"].get(moteur) or {}).get("reponse") or "",
            ))
    for p in pieges:
        elements.append(Element(
            id_interne="", source="piege", question_id=p["question_id"], moteur=p["moteur"],
            doc=p["doc"], question=p["question"], reponse=p["reponse_piegee"],
            piege_id=p["id"], critere_vise=p["critere_vise"], verdict_attendu=p["verdict_attendu"],
        ))
    random.Random(GRAINE_JUGE).shuffle(elements)
    for i, e in enumerate(elements, 1):
        e.id_interne = f"J{i:02d}"
    return elements


def charger_prompt_systeme(chemin: Path = PROMPT) -> str:
    """Texte envoyé au juge : uniquement ce qui suit le marqueur (l'en-tête ne part jamais)."""
    texte = chemin.read_text(encoding="utf-8")
    if texte.count(MARQUEUR_PROMPT) != 1:
        raise ValueError(f"marqueur de prompt absent ou répété dans {chemin.name}")
    return texte.split(MARQUEUR_PROMPT, 1)[1].strip()


def rendu_contrat(contrat: dict) -> str:
    lignes = [f"# Contrat entier : {contrat['titre']} — v{contrat['version']} ({contrat['doc']})", ""]
    for e in contrat["extraits"]:
        titre = f"Article {e['article']}" if e["article"] else "Préambule (sans numéro d'article)"
        lignes += [f"## {titre}", "", e["texte"].strip(), ""]
    return "\n".join(lignes).rstrip()


def message_juge(contrat_rendu: str, question: str, reponse: str) -> str:
    return "\n\n".join([
        contrat_rendu,
        "# Question posée",
        question.strip(),
        "# Réponse à juger",
        reponse.strip(),
    ])


def termes_interdits(texte: str) -> list[str]:
    return sorted({m.group(0) for m in TERMES_INTERDITS.finditer(texte)})


def controle_aveuglement(systeme: str, messages: dict[str, str]) -> list[str]:
    """Problèmes d'aveuglement (vide = conforme). Ne montre que le terme et l'id interne."""
    problemes = []
    if termes_interdits(systeme):
        problemes.append(f"prompt système : {termes_interdits(systeme)}")
    for id_interne, message in messages.items():
        trouves = termes_interdits(message)
        if trouves:
            problemes.append(f"{id_interne} : {trouves}")
    return problemes


def schema_sortie() -> dict:
    """Schéma imposé : pour C1, C2, C3, justification PUIS verdict (property_ordering)."""
    def critere(c: str) -> dict:
        return {
            "type": "OBJECT",
            "properties": {
                "justification": {"type": "STRING"},
                "verdict": {"type": "STRING", "enum": list(VERDICTS[c])},
            },
            "required": ["justification", "verdict"],
            "property_ordering": ["justification", "verdict"],
        }

    return {
        "type": "OBJECT",
        "properties": {c: critere(c) for c in VERDICTS},
        "required": list(VERDICTS),
        "property_ordering": list(VERDICTS),
    }


def config_appel(systeme: str) -> dict:
    return {
        "system_instruction": systeme,
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "response_mime_type": "application/json",
        "response_schema": schema_sortie(),
        "thinking_config": {"thinking_level": THINKING_LEVEL},
    }


# ─────────────────────────────────────────────
# Sortie du juge : validation stricte, jamais de conversion
# ─────────────────────────────────────────────


class ReponseInvalide(Exception):
    pass


def valider_sortie(texte: str | None) -> dict:
    """Verdicts validés, ou ReponseInvalide. Un verdict hors liste n'est JAMAIS corrigé."""
    if not texte or not texte.strip():
        raise ReponseInvalide("réponse vide")
    try:
        data = json.loads(texte)
    except json.JSONDecodeError:
        raise ReponseInvalide("JSON invalide") from None
    if not isinstance(data, dict):
        raise ReponseInvalide("JSON invalide : objet attendu")
    verdicts = {}
    for c, permis in VERDICTS.items():
        bloc = data.get(c)
        if not isinstance(bloc, dict):
            raise ReponseInvalide(f"{c} manquant")
        justification = bloc.get("justification")
        verdict = bloc.get("verdict")
        if not isinstance(justification, str) or not justification.strip():
            raise ReponseInvalide(f"{c} : justification manquante")
        if verdict not in permis:
            raise ReponseInvalide(f"{c} : verdict manquant ou hors liste")
        verdicts[c] = {"justification": justification.strip(), "verdict": verdict}
    return verdicts


def verdict_global(verdicts: dict) -> str:
    """« rejetée » si au moins un critère est « non » (« sans objet » jamais bloquant), sinon « validée »."""
    return "rejetée" if any(v["verdict"] == "non" for v in verdicts.values()) else "validée"


def _int_ou_none(valeur: Any) -> int | None:
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else None


def extraire(reponse: Any) -> dict:
    """Champs utiles d'une réponse generate_content. Tolère les champs absents."""
    usage = getattr(reponse, "usage_metadata", None)
    candidats = getattr(reponse, "candidates", None) or []
    fin = getattr(candidats[0], "finish_reason", None) if candidats else None
    try:
        texte = reponse.text
    except Exception:  # noqa: BLE001 — une réponse sans texte exploitable est vide, pas un plantage
        texte = None
    return {
        "texte": texte,
        "tokens_in": _int_ou_none(getattr(usage, "prompt_token_count", None)),
        "tokens_out": _int_ou_none(getattr(usage, "candidates_token_count", None)),
        "tokens_raisonnement": _int_ou_none(getattr(usage, "thoughts_token_count", None)),
        "finish_reason": None if fin is None else str(getattr(fin, "name", fin)),
        "model_version": getattr(reponse, "model_version", None),
        "response_id": getattr(reponse, "response_id", None),
    }


def cout_usd(tarif: Tarif, tokens_in: int | None, tokens_sortie: int | None) -> float | None:
    if tokens_in is None or tokens_sortie is None:
        return None
    return tokens_in / 1_000_000 * tarif.entree + tokens_sortie / 1_000_000 * tarif.sortie


# ─────────────────────────────────────────────
# Appels : plafond dur, réessai unique sur erreur technique
# ─────────────────────────────────────────────


class Budget:
    """Plafond dur : chaque tentative d'appel consomme une unité, réessais compris."""

    def __init__(self, plafond: int) -> None:
        self.plafond = plafond
        self.utilises = 0

    def prendre(self) -> bool:
        if self.utilises >= self.plafond:
            return False
        self.utilises += 1
        return True


def plafond_appels(n_jugements: int) -> int:
    return n_jugements + min(REESSAIS_MAX, n_jugements * REESSAIS_PAR_ELEMENT)


def juger(
    client: Any,
    modele: str,
    config: dict,
    message: str,
    budget: Budget,
    tarif: Tarif,
    horloge: Callable[[], float] = time.monotonic,
    attente: Callable[[float], None] = time.sleep,
) -> dict:
    """UN jugement. Ne lève jamais (sauf KeyboardInterrupt). Une sortie invalide devient une ERREUR."""
    resultat: dict = {
        "verdicts": None, "verdict_global": None, "erreur": None, "tentatives": [],
        "tokens_in": 0, "tokens_out": 0, "tokens_raisonnement": 0,
        "finish_reason": None, "model_version": None, "response_id": None, "latence_s": None,
    }
    tokens_connus = True
    for essai in range(1 + REESSAIS_PAR_ELEMENT):
        if not budget.prendre():
            resultat["erreur"] = {"type": "plafond_atteint", "motif": f"plafond de {budget.plafond} appels atteint"}
            break
        debut = horloge()
        try:
            reponse = client.models.generate_content(model=modele, contents=message, config=config)
        except Exception as exc:  # noqa: BLE001 — un élément en échec ne doit pas arrêter le run
            # Le TYPE et le code HTTP seuls : jamais le message d'une exception dans un fichier versionné.
            resultat["tentatives"].append({"erreur_technique": type(exc).__name__, "code": _int_ou_none(getattr(exc, "code", None))})
            if essai < REESSAIS_PAR_ELEMENT:
                attente(DELAI_REESSAI_S)
                continue
            resultat["erreur"] = {"type": "erreur_technique", "motif": type(exc).__name__}
            break
        latence = round(horloge() - debut, 3)
        infos = extraire(reponse)
        resultat["tentatives"].append({"finish_reason": infos["finish_reason"], "latence_s": latence})
        for cle in ("tokens_in", "tokens_out", "tokens_raisonnement"):
            if infos[cle] is None:
                if cle != "tokens_raisonnement":
                    tokens_connus = False
            else:
                resultat[cle] += infos[cle]
        resultat.update({k: infos[k] for k in ("finish_reason", "model_version", "response_id")})
        resultat["latence_s"] = latence
        if not (infos["texte"] or "").strip() and essai < REESSAIS_PAR_ELEMENT:
            attente(DELAI_REESSAI_S)
            continue
        try:
            if infos["finish_reason"] not in (None, "STOP"):
                raise ReponseInvalide(f"arrêt anormal : {infos['finish_reason']}")
            resultat["verdicts"] = valider_sortie(infos["texte"])
            resultat["verdict_global"] = verdict_global(resultat["verdicts"])
        except ReponseInvalide as exc:
            resultat["erreur"] = {"type": "reponse_invalide", "motif": str(exc), "texte_brut": infos["texte"]}
        break
    # Tokens inconnus -> coût None (jamais un chiffre inventé). Tentatives en exception : 0 token compté.
    resultat["cout_usd"] = (
        cout_usd(tarif, resultat["tokens_in"], resultat["tokens_out"] + resultat["tokens_raisonnement"])
        if tokens_connus else None
    )
    return resultat


# ─────────────────────────────────────────────
# Client réel (import tardif, APRÈS les garde-fous)
# ─────────────────────────────────────────────


def creer_client_vertex(project: str, location: str) -> Any:
    """
    Client google-genai en mode Vertex AI (enterprise=True, nouveau nom de vertexai=True),
    authentifié par Application Default Credentials. Réessais automatiques du SDK
    coupés (attempts=1) : le plafond compte chaque tentative. Aucun appel réseau à la
    construction quand projet et région sont fournis (code du SDK 2.25.0).
    """
    from google import genai  # requirements-eval.txt, jamais dans la prod

    return genai.Client(
        enterprise=True,
        project=project,
        location=location,
        http_options={"timeout": TIMEOUT_MS, "retry_options": {"attempts": 1}},
    )


def lire_base_url(client: Any) -> str | None:
    """URL de base résolue par le SDK (attribut interne) : None si illisible."""
    options = getattr(getattr(client, "_api_client", None), "_http_options", None)
    url = getattr(options, "base_url", None)
    return url if isinstance(url, str) else None


# ─────────────────────────────────────────────
# Résumé, empreintes, rapport
# ─────────────────────────────────────────────


def sha256_fichier(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def sha256_texte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def etat_git() -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        modifie = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "arbre_modifie": None}
    return {"commit": commit, "arbre_modifie": modifie}


def _package_version(nom: str) -> str:
    from importlib import metadata

    try:
        return metadata.version(nom)
    except metadata.PackageNotFoundError:
        return "non installé"


def estimer_cout(longueurs_prompts: list[int], tarif: Tarif, plafond: int) -> dict:
    """Borne haute (HYPOTHÈSE) : longueur/3 tokens en entrée, MAX_OUTPUT_TOKENS en sortie."""
    par_appel = [
        cout_usd(tarif, -(-n // CARACTERES_PAR_TOKEN_BORNE), MAX_OUTPUT_TOKENS) for n in longueurs_prompts
    ]
    total = sum(par_appel)
    plus_cher = max(par_appel) if par_appel else 0.0
    return {
        "jugements": round(total, 4),
        "plafond": round(total + (plafond - len(par_appel)) * plus_cher, 4),
    }


def selection_fumee(elements: list[Element], cible: str) -> list[Element]:
    """« defaut » : 1re réponse d'origine ; « Q01:anthropic » ; « P03 »."""
    if cible == "defaut":
        return [next(e for e in elements if e.source == "origine")]
    if re.fullmatch(r"P\d{2}", cible):
        choix = [e for e in elements if e.piege_id == cible]
    elif re.fullmatch(r"Q\d{2}:(anthropic|mistral)", cible):
        q, m = cible.split(":")
        choix = [e for e in elements if e.source == "origine" and e.question_id == q and e.moteur == m]
    else:
        raise ValueError(f"élément de fumée invalide : {cible!r} (ex. Q01:anthropic, P03)")
    if len(choix) != 1:
        raise ValueError(f"élément de fumée introuvable : {cible!r}")
    return choix


def format_resume(
    modele: str, location: str, tarif: Tarif, n_elements: int, repetitions: int,
    plafond: int, cout: dict, smoke: bool,
) -> str:
    n_jugements = n_elements * repetitions
    return "\n".join([
        "=== Juge LLM (Gemini, Vertex AI) — fidélité au contrat ===",
        f"Mode                 : {'FUMÉE (1 élément)' if smoke else 'run complet'}",
        f"Modèle du juge       : {modele}",
        f"Région               : {location} — {traitement(location)}",
        f"Endpoint attendu     : {endpoint_attendu(location)}",
        "Authentification     : Application Default Credentials (aucune clé lue)",
        f"Tarif                : {tarif.entree} $ / {tarif.sortie} $ par million de tokens (entrée / sortie + raisonnement)",
        f"                       {tarif.note}",
        f"                       source : {TARIF_SOURCE} (consultée le {TARIF_CONSULTE_LE})",
        f"Température          : {TEMPERATURE} ({TEMPERATURE_NOTE})",
        f"Raisonnement         : thinking_level={THINKING_LEVEL}, max_output_tokens={MAX_OUTPUT_TOKENS}",
        f"Éléments             : {n_elements} x {repetitions} répétition(s) = {n_jugements} jugement(s)",
        f"Plafond dur d'appels : {plafond} (réessais compris)",
        "Coût estimé (BORNE HAUTE, hypothèse : 1 token pour "
        f"{CARACTERES_PAR_TOKEN_BORNE} caractères en entrée + {MAX_OUTPUT_TOKENS} tokens en sortie par appel) :",
        f"    {n_jugements} jugement(s) : {fmt_usd(cout['jugements'])}",
        f"    au plafond ({plafond} appels) : {fmt_usd(cout['plafond'])}",
        "Le coût réel est recalculé en fin de run à partir des tokens mesurés.",
    ])


def _resume(report: dict) -> dict:
    jugements = report["jugements"]
    couts = [j["cout_usd"] for j in jugements]
    return {
        "jugements": len(jugements),
        "valides": sum(1 for j in jugements if j["verdicts"]),
        "erreurs": sum(1 for j in jugements if j["erreur"]),
        "appels_effectues": report["appels_effectues"],
        "tokens_in": sum(j["tokens_in"] for j in jugements),
        "tokens_out": sum(j["tokens_out"] for j in jugements),
        "tokens_raisonnement": sum(j["tokens_raisonnement"] for j in jugements),
        # None dès qu'un coût manque : jamais un total partiel présenté comme complet.
        "cout_usd": None if any(c is None for c in couts) else round(sum(couts), 4),
    }


def _etiquette(j: dict) -> str:
    return j["piege_id"] if j["source"] == "piege" else "origine"


def render_markdown(report: dict) -> str:
    h = report["en_tete"]
    r = report["resume"]
    t = h["tarif"]
    lignes = [
        f"# Juge LLM — fidélité au contrat ({h['mode']})",
        "",
        f"- Date (UTC) : {h['date_utc']}" + ("  — **RUN INTERROMPU**" if report.get("interrompu") else ""),
        f"- Modèle du juge : `{h['modele']}`",
        f"- Région : `{h['location']}` — {h['traitement']}",
        f"- Endpoint : `{h['endpoint']}`",
        f"- Tarif utilisé : {t['entree']} $ / {t['sortie']} $ par million de tokens (entrée / sortie + raisonnement) — "
        f"{t['note']}. Source : {t['source']} (consultée le {t['consulte_le']}).",
        f"- Température : {h['temperature']} — {h['temperature_note']}",
        f"- Raisonnement : thinking_level={h['thinking_level']}, max_output_tokens={h['max_output_tokens']}",
        f"- Prompt : `prompt_juge.md` sha256 `{h['empreintes']['prompt_juge.md']}`",
        f"- Commit : `{h['git']['commit']}`" + (" (arbre modifié)" if h["git"]["arbre_modifie"] else ""),
        f"- Répétitions : {h['repetitions']} · graine : {h['graine']} · plafond : {h['plafond_appels']} appels",
        "",
        "## Synthèse",
        "",
        f"- Jugements : {r['jugements']} · valides : {r['valides']} · **ERREURS : {r['erreurs']}**",
        f"- Appels effectués : {r['appels_effectues']}",
        f"- Tokens : {r['tokens_in']} en entrée, {r['tokens_out']} en sortie, {r['tokens_raisonnement']} de raisonnement",
        f"- Coût mesuré : {fmt_usd(r['cout_usd'])} (estimation avant run, borne haute : {fmt_usd(h['cout_estime_borne_haute_usd']['jugements'])})",
        "",
        "Ce rapport ne compare pas au jugement humain : voir `tests/judge/compare_juge_humain.py`.",
        "",
        "## Verdicts",
        "",
        "| Id | Rép. | Source | Question | Moteur | C1 | C2 | C3 | Verdict global |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for j in report["jugements"]:
        if j["verdicts"]:
            cellules = [j["verdicts"][c]["verdict"] for c in VERDICTS] + [j["verdict_global"]]
        else:
            cellules = ["—", "—", "—", f"ERREUR ({j['erreur']['type']})"]
        lignes.append(
            f"| {j['id_interne']} | {j['repetition']} | {_etiquette(j)} | {j['question_id']} | {j['moteur']} | "
            + " | ".join(cellules) + " |"
        )
    erreurs = [j for j in report["jugements"] if j["erreur"]]
    lignes += ["", "## Erreurs du juge (ni accord ni désaccord)", ""]
    if not erreurs:
        lignes.append("- Aucune.")
    for j in erreurs:
        lignes.append(f"- {j['id_interne']} (rép. {j['repetition']}) : {j['erreur']['type']} — {j['erreur'].get('motif', '')}")
    lignes += ["", "## Justifications", ""]
    for j in report["jugements"]:
        if not j["verdicts"]:
            continue
        lignes.append(f"### {j['id_interne']} (rép. {j['repetition']}) — {_etiquette(j)} · {j['question_id']} · {j['moteur']}")
        lignes.append("")
        for c in VERDICTS:
            v = j["verdicts"][c]
            lignes.append(f"- **{c} : {v['verdict']}** — {v['justification']}")
        lignes.append("")
    lignes += [f"Détail complet : `{Path(report['fichier_json']).name}`", ""]
    return "\n".join(lignes)


def finalize(report: dict, writer: ResultsWriter, interrompu: bool) -> None:
    report["interrompu"] = interrompu
    report["resume"] = _resume(report)
    writer.write_json(report)
    writer.write_markdown(render_markdown(report))


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Juge LLM hors ligne : fidélité au contrat (lot C).")
    p.add_argument("--yes", action="store_true", help=f"confirme les appels réels (exige aussi {ALLOW_REAL_ENV}=1)")
    p.add_argument(
        "--smoke", nargs="?", const="defaut", default=None, metavar="ELEMENT",
        help="un seul élément (défaut : 1re réponse d'origine ; ex. Q01:anthropic, P03)",
    )
    p.add_argument("--repetitions", type=int, choices=range(1, MAX_REPETITIONS + 1), default=1,
                   help="2 = mesure de stabilité du juge (désactivée par défaut)")
    p.add_argument("--out-dir", default=str(RESULTS_DIR), help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    environ: dict[str, str] | None = None,
    out: Callable[[str], None] = print,
    client_factory: Callable[[str, str], Any] = creer_client_vertex,
    now: Callable[[], datetime] | None = None,
    horloge: Callable[[], float] = time.monotonic,
    attente: Callable[[float], None] = time.sleep,
) -> int:
    args = parse_args(argv)
    environ = os.environ if environ is None else environ
    maintenant = (now or (lambda: datetime.now(timezone.utc)))()
    neutralize_dotenv()

    # 1. Présence des variables — noms seulement, jamais de valeur.
    manquantes = [nom for nom in REQUIRED_ENV if not environ.get(nom)]
    if manquantes:
        out("Variables d'environnement manquantes : " + ", ".join(manquantes))
        out("Le script ne lit que l'environnement (aucun .env). Rien n'a été appelé.")
        return EXIT_REFUSED
    project, location, modele = (environ[n] for n in REQUIRED_ENV)

    # 2. Région UE seulement.
    if location not in LOCATIONS_UE:
        out(f"Refus : JUDGE_LOCATION = « {location} » hors de la liste UE acceptée ({', '.join(LOCATIONS_UE)}). "
            "L'endpoint global n'engage sur aucun lieu de traitement.")
        return EXIT_REFUSED

    # 3. Tarif connu et en vigueur : sans lui, pas d'estimation de coût.
    tarif = TARIFS_JUGE.get(modele)
    if tarif is None:
        out(f"Refus : aucun tarif connu pour JUDGE_MODEL = « {modele} » (modèles tarifés : {', '.join(TARIFS_JUGE)}).")
        return EXIT_REFUSED
    if tarif.valable_jusqu_au and maintenant.date() > tarif.valable_jusqu_au:
        out(f"Refus : le tarif enregistré pour {modele} n'est valable que jusqu'au "
            f"{tarif.valable_jusqu_au:%d/%m/%Y}. Mettre à jour TARIFS_JUGE depuis la source officielle.")
        return EXIT_REFUSED

    # 4. ADC uniquement.
    cles = [nom for nom in CLES_API_INTERDITES if environ.get(nom)]
    if cles:
        out("Refus : variable(s) de clé API Google présente(s) : " + ", ".join(cles)
            + ". L'authentification doit passer par les Application Default Credentials ; vider ces variables.")
        return EXIT_REFUSED

    # 5. Données, prompts, contrôle d'aveuglement.
    run = json.loads(REFERENCE_RUN.read_text(encoding="utf-8"))
    pieges = json.loads(PIEGES.read_text(encoding="utf-8"))["pieges"]
    elements = charger_elements(run, pieges)
    systeme = charger_prompt_systeme()
    contrats = {
        e.doc: json.loads((CONTRATS_DIR / f"{e.doc}.json").read_text(encoding="utf-8")) for e in elements
    }
    rendus = {doc: rendu_contrat(c) for doc, c in contrats.items()}
    messages = {e.id_interne: message_juge(rendus[e.doc], e.question, e.reponse) for e in elements}
    problemes = controle_aveuglement(systeme, messages)
    if problemes:
        out("Refus : aveuglement non respecté (terme interdit dans un prompt) :")
        for p in problemes:
            out(f"    {p}")
        return EXIT_REFUSED
    smoke = args.smoke is not None
    if smoke:
        try:
            elements = selection_fumee(elements, args.smoke)
        except ValueError as exc:
            out(f"Refus : {exc}")
            return EXIT_REFUSED

    # 6. Plan, coût estimé, confirmation.
    jugements = [(rep, e) for rep in range(1, args.repetitions + 1) for e in elements]
    plafond = plafond_appels(len(jugements))
    cout = estimer_cout([len(systeme) + len(messages[e.id_interne]) for _, e in jugements], tarif, plafond)
    out(format_resume(modele, location, tarif, len(elements), args.repetitions, plafond, cout, smoke))
    if not (args.yes and environ.get(ALLOW_REAL_ENV) == "1"):
        out("")
        manque = [x for x, ok in (("--yes", args.yes), (f"{ALLOW_REAL_ENV}=1", environ.get(ALLOW_REAL_ENV) == "1")) if not ok]
        out("Aucun appel effectué. Manque : " + " et ".join(manque) + " (les deux sont exigés pour un appel réel).")
        return EXIT_REFUSED

    # 7. Client (aucun réseau à la construction), contrôle de l'endpoint résolu.
    client = client_factory(project, location)
    url = lire_base_url(client)
    if url != endpoint_attendu(location):
        out(f"Refus : endpoint résolu par le SDK = « {url} », attendu « {endpoint_attendu(location)} ». Aucun appel effectué.")
        return EXIT_REFUSED

    # 8. Run.
    secrets = [environ[n] for n in SECRET_ENV if environ.get(n)]
    writer = ResultsWriter.reserve(
        Path(args.out_dir), maintenant.strftime("%Y%m%d_%H%M%S"), smoke, secrets, prefix="judge_upload",
    )
    config = config_appel(systeme)
    budget = Budget(plafond)
    report: dict = {
        "fichier_json": str(writer.json_path),
        "en_tete": {
            "date_utc": maintenant.isoformat(timespec="seconds"),
            "mode": "fumée" if smoke else "complet",
            "modele": modele,
            "location": location,
            "traitement": traitement(location),
            "endpoint": url,
            "projet": "défini (valeur non enregistrée)",
            "authentification": "Application Default Credentials",
            "tarif": {
                "entree": tarif.entree, "sortie": tarif.sortie, "note": tarif.note,
                "source": TARIF_SOURCE, "consulte_le": TARIF_CONSULTE_LE,
            },
            "temperature": TEMPERATURE,
            "temperature_note": TEMPERATURE_NOTE,
            "thinking_level": THINKING_LEVEL,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "graine": GRAINE_JUGE,
            "repetitions": args.repetitions,
            "plafond_appels": plafond,
            "cout_estime_borne_haute_usd": cout,
            "empreintes": {
                "prompt_juge.md": sha256_fichier(PROMPT),
                "prompt_systeme_envoye": sha256_texte(systeme),
                "grille.md": sha256_fichier(GRILLE),
                "pieges.json": sha256_fichier(PIEGES),
                REFERENCE_RUN.name: sha256_fichier(REFERENCE_RUN),
                **{f"contrats/{doc}.json": sha256_fichier(CONTRATS_DIR / f"{doc}.json") for doc in sorted(contrats)},
            },
            "git": etat_git(),
            "versions": {"python": sys.version.split()[0], "google-genai": _package_version("google-genai")},
        },
        "correspondance": [e.correspondance() for e in elements],
        "jugements": [],
        "appels_effectues": 0,
        "interrompu": False,
    }
    interrompu = False
    try:
        for rep, e in jugements:
            res = juger(client, modele, config, messages[e.id_interne], budget, tarif, horloge, attente)
            report["appels_effectues"] = budget.utilises
            report["jugements"].append({**e.correspondance(), "repetition": rep, **res})
            writer.write_json(report)
            etat = (f"ok {res['latence_s']:.1f}s {res['tokens_in']}+{res['tokens_out']}+{res['tokens_raisonnement']} tok"
                    if res["verdicts"] else f"ERREUR ({res['erreur']['type']})")
            out(f"  {e.id_interne} (rép. {rep}) : {etat}")
    except KeyboardInterrupt:
        interrompu = True
        out("Interrompu (Ctrl+C) : résultats partiels conservés.")
    finally:
        report["appels_effectues"] = budget.utilises
        finalize(report, writer, interrompu)
    out(f"Résultats : {writer.json_path}")
    out(f"Résumé    : {writer.md_path}")
    return EXIT_INTERRUPTED if interrompu else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

"""
Agent RAG agentique — graphe LangGraph.
Étapes : router → (planner) → retrieve → evaluate → (reformulate) → synthesize → log
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from contextvars import ContextVar
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TypedDict

import anthropic
import chromadb
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

log = logging.getLogger("agent")

load_dotenv()

# Garde "une fois par processus" du warning de modèle Mistral non tarifé (voir
# configure_stdout_logging, qui est ré-exécutée à chaque rerun Streamlit).
_tarif_warning_emis = False

# Journal d'audit des appels LLM (auditabilité de l'endpoint régional : la doc
# Mistral demande de journaliser hôte, serveur, modèle et identifiant de requête
# pour chaque appel — https://docs.mistral.ai/inference/regional-inference).
# AUCUN contenu de question, de réponse ni de document n'y figure jamais.
AUDIT_LOGGER_NAME = "audit_llm"
AUDIT_HANDLER_NAME = "audit_stdout_handler"
audit_log = logging.getLogger(AUDIT_LOGGER_NAME)


def configure_stdout_logging() -> None:
    """
    Ajoute un StreamHandler(sys.stdout) niveau WARNING sur les loggers
    "streamlit_app", "agent" et "upload_session" — pas sur root. Cloud Logging
    (et plus généralement tout collecteur de logs conteneur) ne capture que
    stdout/stderr du process, jamais un fichier écrit sur le disque local ;
    le RotatingFileHandler existant sur root (app.py) continue de tout
    recevoir (INFO compris, qui peut contenir du texte de questions/réponses)
    dans data/streamlit_debug.log — ce handler-ci ne prend que WARNING et
    au-dessus, et seulement sur ces loggers nommés.
    "upload_session" ajouté le 24/09/2026 : sans lui, les WARNING/ERROR du
    verrou upload (acquisition, purge, timeout) n'atteignaient jamais Cloud
    Logging et restaient dans un fichier local perdu à chaque redémarrage
    d'instance (min-instances=0) — le comportement du verrou était donc
    inauditable en production.
    Signale aussi, une seule fois par processus, un MISTRAL_MODEL non tarifé.
    Ce warning est émis ICI et non au niveau module : app.py importe `agent`
    (ligne 18) bien avant d'appeler cette fonction (ligne 67), donc un log
    émis à l'import partirait avant l'existence de tout handler stdout et
    n'atteindrait jamais Cloud Logging.
    Idempotent : n'ajoute rien si un handler du même nom est déjà présent sur
    le logger visé (ce code est réexécuté à chaque rerun Streamlit dans le
    même process).
    """
    global _tarif_warning_emis
    handler_name = "stdout_warning_handler"
    for logger_name in ("streamlit_app", "agent", "upload_session"):
        logger = logging.getLogger(logger_name)
        if any(h.name == handler_name for h in logger.handlers):
            continue
        handler = logging.StreamHandler(sys.stdout)
        handler.name = handler_name
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)

    # Logger d'audit (un enregistrement par appel Mistral, voir _log_appel_mistral).
    # Contrairement aux trois loggers ci-dessus, il porte des événements NOMINAUX
    # (INFO), pas des avertissements — d'où un handler et un niveau propres :
    #   - setLevel(INFO) explicite : sans lui le niveau effectif serait hérité de
    #     la racine (WARNING par défaut) et les INFO seraient éliminés avant même
    #     d'atteindre le handler ;
    #   - propagate = False : pas de doublon via le logger racine. Ces lignes ne
    #     vont donc PAS non plus dans data/streamlit_debug.log (fichier local
    #     perdu à chaque redémarrage d'instance) : stdout uniquement.
    # Setters idempotents ; handler protégé par la même garde de nom que ci-dessus.
    audit = logging.getLogger(AUDIT_LOGGER_NAME)
    audit.setLevel(logging.INFO)
    audit.propagate = False
    if not any(h.name == AUDIT_HANDLER_NAME for h in audit.handlers):
        audit_handler = logging.StreamHandler(sys.stdout)
        audit_handler.name = AUDIT_HANDLER_NAME
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        audit.addHandler(audit_handler)

    # Modèle absent : Mistral est déjà indisponible, rien à signaler.
    if MISTRAL_MODEL and MISTRAL_MODEL != MISTRAL_PRICED_MODEL and not _tarif_warning_emis:
        _tarif_warning_emis = True
        log.warning("TARIF_MISTRAL modele_non_tarife=%s", MISTRAL_MODEL)

ROOT = Path(__file__).parent.parent
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "assur_docs"
# Modèle d'embeddings : API Mistral depuis le sous-lot 2.1 (03/10/2026), à la
# place du modèle local intfloat/multilingual-e5-large (sentence-transformers),
# dont le chargement coûtait 75 à 90 s à chaque démarrage à froid (mesuré dans
# les logs Cloud Run du 26/09 au 03/10/2026). Configurable côté serveur, jamais
# par le visiteur. MODEL_NAME est aussi la valeur écrite dans les métadonnées
# de la collection Chroma (garde-fou de get_chroma_col) : changer de modèle
# déclenche une reconstruction de l'index.
MISTRAL_EMBED_MODEL = os.environ.get("MISTRAL_EMBED_MODEL") or "mistral-embed"
MODEL_NAME = MISTRAL_EMBED_MODEL
# Configurable côté serveur, jamais par le visiteur. Le défaut reproduit
# exactement la valeur en dur précédente : sans CLAUDE_MODEL dans
# l'environnement, le comportement est identique à celui du lot 2a.
# Attention : les tarifs PRIX_INPUT/OUTPUT_USD_PAR_MTOK plus bas ne valent que
# pour Sonnet 4.6 — changer ce modèle sans changer ces tarifs rendrait
# l'estimation de coût fausse.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
RETRIEVAL_K = 10
# Plafond dur : le prompt planner demande "2-4" mais rien ne garantit que le LLM
# le respecte. Sans cette borne, le nombre d'appels LLM par question n'est pas
# structurellement fini (voir boucle evaluate/reformulate, bornée par tentatives<3).
MAX_SUBQUESTIONS = int(os.environ.get("MAX_SUBQUESTIONS", "4"))

# ─────────────────────────────────────────────
# État partagé
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    question_originale: str
    produit_filtre: str | None
    sous_questions: list[dict]        # [{texte, doc_cible_probable}]
    resultats: list[dict]             # [{sous_question, chunks, suffisant, tentatives, methode_reformulation}]
    reponse_finale: str
    trace_log: list[dict]             # append-only
    usage: dict                       # rempli par run_agent() en fin d'exécution (voir UsageTracker)


# ─────────────────────────────────────────────
# Ressources partagées (chargées une fois)
# ─────────────────────────────────────────────

_chroma_client: chromadb.PersistentClient | None = None  # référence forte pour éviter le GC
_chroma_col: chromadb.Collection | None = None
_chroma_lock = threading.Lock()  # évite une reconstruction concurrente si plusieurs sessions démarrent en même temps
_anthropic_client: anthropic.Anthropic | None = None

# ── Compteurs d'instrumentation mémoire ──────────────────────────────────────
# _current_turn  : numéro de la question en cours (Q1, Q2, …), mis à jour dans run_agent()
# _turn_llm_seq  : compteur d'appels LLM dans le tour courant (remis à 0 par run_agent)
# _turn_encode_seq : compteur d'encodages (embed_query/HyDE) dans le tour courant
_turn_counter: int = 0
_current_turn: int = 0
_turn_llm_seq: int = 0
_turn_encode_seq: int = 0

# ─────────────────────────────────────────────
# Disjoncteur quotidien (lot 0 — garde-fou de coût)
# ─────────────────────────────────────────────
# Limites connues : compteur en mémoire de processus, remis à zéro au redémarrage
# (pas persistant) ; valable uniquement pour CETTE instance (aucune coordination
# multi-instance si le service scale au-delà de 1) ; ne remplace PAS une limite de
# dépense configurée côté Anthropic — seul rempart réel contre un dépassement de budget.
# Compte des QUESTIONS, pas des appels LLM : une question peut déclencher de 3 à
# 1 + MAX_SUBQUESTIONS*5 + 1 appels selon le chemin emprunté dans le graphe (voir
# MAX_SUBQUESTIONS ci-dessous) — ce disjoncteur ne borne donc pas directement le
# nombre d'appels API, seulement le nombre de questions traitées par jour.

DAILY_QUESTION_LIMIT = int(os.environ.get("DAILY_QUESTION_LIMIT", "100"))
_daily_lock = threading.Lock()
_daily_count: int = 0
_daily_date: date | None = None


class DailyLimitExceeded(Exception):
    """Levée quand DAILY_QUESTION_LIMIT est atteint pour la journée UTC courante."""


def _check_daily_limit() -> None:
    """Incrémente et vérifie le compteur de questions du jour (UTC), thread-safe."""
    global _daily_count, _daily_date
    today = datetime.now(timezone.utc).date()
    with _daily_lock:
        if _daily_date != today:
            _daily_date = today
            _daily_count = 0
        if _daily_count >= DAILY_QUESTION_LIMIT:
            raise DailyLimitExceeded(f"limite {DAILY_QUESTION_LIMIT}/jour atteinte")
        _daily_count += 1


# ─────────────────────────────────────────────
# Disjoncteur des comparaisons (lot 3.1)
# ─────────────────────────────────────────────
# Strictement indépendant de DAILY_QUESTION_LIMIT ci-dessus : compteur, verrou,
# date et exception séparés. Une comparaison n'emprunte pas run_agent() et ne
# touche donc jamais le compteur du mode corpus, et réciproquement.
# Compte des COMPARAISONS, pas des appels LLM : une comparaison = 2 appels
# (un par moteur), soit 100 appels LLM par jour au plafond par défaut. Un
# réessai Mistral ne compte pas ici : le disjoncteur est incrémenté une fois
# par comparaison, avant les appels.
# Mêmes limites connues que le disjoncteur du lot 0 : mémoire de processus,
# remis à zéro au redémarrage, aucune coordination multi-instance, et ne
# remplace pas un plafond de dépense configuré chez le fournisseur.

COMPARISON_DAILY_LIMIT = int(os.environ.get("COMPARISON_DAILY_LIMIT", "50"))
_comparison_lock = threading.Lock()
_comparison_count: int = 0
_comparison_date: date | None = None


class ComparisonDailyLimitExceeded(Exception):
    """Levée quand COMPARISON_DAILY_LIMIT est atteint pour la journée UTC courante."""


def _check_comparison_daily_limit() -> None:
    """Incrémente et vérifie le compteur de comparaisons du jour (UTC), thread-safe."""
    global _comparison_count, _comparison_date
    today = datetime.now(timezone.utc).date()
    with _comparison_lock:
        if _comparison_date != today:
            _comparison_date = today
            _comparison_count = 0
        if _comparison_count >= COMPARISON_DAILY_LIMIT:
            raise ComparisonDailyLimitExceeded(
                f"limite {COMPARISON_DAILY_LIMIT} comparaisons/jour atteinte"
            )
        _comparison_count += 1


# ─────────────────────────────────────────────
# Agrégation d'usage par question (lot 1, sous-lot 1.2)
# ─────────────────────────────────────────────
# ContextVar (pas de variable globale de module) : un tracker neuf par appel à
# run_agent(), positionné/retiré dans son try/finally. Confirmé par lecture de
# la source LangGraph installée (langgraph/pregel/_executor.py::BackgroundExecutor
# .submit, langgraph/pregel/_loop.py:1667) que chaque nœud s'exécute dans un
# thread d'un ContextThreadPoolExecutor (langchain_core.runnables.config), MAIS
# LangGraph copie explicitement le contexte contextvars courant
# (contextvars.copy_context()) avant de soumettre et exécute le nœud via
# ctx.run(fn, ...) — donc _usage_ctx positionné dans run_agent() (thread
# appelant) est bien visible à l'intérieur de chaque nœud, malgré le thread
# différent. Vérifié par lecture de code, pas par mesure en conditions réelles.

# Tarifs Sonnet 4.6 lus sur https://claude.com/pricing (redirigé depuis
# anthropic.com/pricing) le 21/09/2026 — non garantis, susceptibles de changer
# sans préavis. Le pipeline n'utilise pas le prompt caching (aucun
# cache_control envoyé, vérifié par grep) : les tokens de cache éventuels
# (cache_creation_input_tokens/cache_read_input_tokens) ne sont PAS comptés
# dans cette estimation.
# VALABLES UNIQUEMENT POUR SONNET 4.6 : ces deux constantes ne sont pas
# indexées sur CLAUDE_MODEL (configurable depuis le 24/09/2026). Pointer
# CLAUDE_MODEL vers un autre modèle sans mettre ces tarifs à jour produirait
# une estimation de coût silencieusement fausse.
PRIX_INPUT_USD_PAR_MTOK = 3.0
PRIX_OUTPUT_USD_PAR_MTOK = 15.0

# Tarif Mistral — un seul modèle tarifé, en dur, jamais surchargeable par
# l'environnement. Le tarif ne vaut que pour MISTRAL_PRICED_MODEL : pour un autre
# modèle, estimer_cout_usd() renvoie None (l'interface affiche "non disponible")
# plutôt qu'un chiffre faux. Pour tarifer un autre modèle, on modifie ces
# constantes dans le code, avec un test.
# Sources (relevées le 25/09/2026) :
#   - tarif catalogue de Mistral Large 3 : 0,5 $ entrée / 1,5 $ sortie par
#     million de tokens — https://mistral.ai/pricing/api
#   - les endpoints régionaux (eu, us) sont facturés 1,1x le tarif catalogue ;
#     l'endpoint global au tarif catalogue —
#     https://docs.mistral.ai/inference/regional-inference
# Le multiplicateur est DÉRIVÉ de MISTRAL_SERVER (une seule source de vérité :
# la même variable décide de la destination et du tarif). Tarifs effectifs en
# eu/us : 0,55 / 1,65 $ par million de tokens.
MISTRAL_PRICED_MODEL = "mistral-large-2512"
MISTRAL_PRIX_CATALOGUE_INPUT_USD_PAR_MTOK = 0.5
MISTRAL_PRIX_CATALOGUE_OUTPUT_USD_PAR_MTOK = 1.5
MISTRAL_MULTIPLICATEUR_REGIONAL = 1.1
MISTRAL_SERVERS_REGIONAUX = ("eu", "us")

ENGINE_ANTHROPIC = "anthropic"
ENGINE_MISTRAL = "mistral"


class UsageTracker:
    """Accumulateur d'usage (appels, tokens) pour UNE question, thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.n_appels = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def record(self, usage) -> None:
        """Enregistre un objet usage de forme Anthropic (input_tokens/output_tokens)."""
        self.record_tokens(
            getattr(usage, "input_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0) or 0,
        )

    def record_tokens(self, tokens_in: int, tokens_out: int) -> None:
        """
        Primitive bas niveau, indépendante du fournisseur : les objets usage
        d'Anthropic (input_tokens/output_tokens) et de Mistral
        (prompt_tokens/completion_tokens) n'ont pas les mêmes noms de champs,
        l'extraction se fait donc chez l'appelant.
        """
        with self._lock:
            self.n_appels += 1
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out


_usage_ctx: ContextVar["UsageTracker | None"] = ContextVar("usage_ctx", default=None)


def mistral_tarifs_usd_par_mtok() -> tuple[float, float] | None:
    """
    Tarifs Mistral effectifs (entrée, sortie) en USD par million de tokens, ou
    None si MISTRAL_MODEL n'est pas le modèle tarifé (égalité stricte : ni
    casse, ni préfixe, ni alias comme "-latest"). Le multiplicateur régional
    est dérivé de MISTRAL_SERVER, lu à l'appel.
    """
    if MISTRAL_MODEL != MISTRAL_PRICED_MODEL:
        return None
    multiplicateur = (
        MISTRAL_MULTIPLICATEUR_REGIONAL if MISTRAL_SERVER in MISTRAL_SERVERS_REGIONAUX else 1.0
    )
    return (
        MISTRAL_PRIX_CATALOGUE_INPUT_USD_PAR_MTOK * multiplicateur,
        MISTRAL_PRIX_CATALOGUE_OUTPUT_USD_PAR_MTOK * multiplicateur,
    )


def estimer_cout_usd(
    tokens_in: int, tokens_out: int, engine: str = ENGINE_ANTHROPIC
) -> float | None:
    """
    Coût estimé en USD, hors tokens de cache (non utilisés ici).
    Renvoie None quand le moteur n'a pas de tarif applicable (Mistral avec un
    modèle autre que MISTRAL_PRICED_MODEL) : l'appelant affiche alors
    "non disponible" plutôt qu'un chiffre inventé.
    """
    if engine == ENGINE_ANTHROPIC:
        prix_in, prix_out = PRIX_INPUT_USD_PAR_MTOK, PRIX_OUTPUT_USD_PAR_MTOK
    elif engine == ENGINE_MISTRAL:
        tarifs = mistral_tarifs_usd_par_mtok()
        if tarifs is None:
            return None
        prix_in, prix_out = tarifs
    else:
        raise ValueError(f"moteur inconnu: {engine!r}")
    return (tokens_in / 1_000_000) * prix_in + (tokens_out / 1_000_000) * prix_out


def log_memory(label: str) -> None:
    """Logue le RSS du process en MB. print flush=True garantit la visibilité dans Streamlit Cloud."""
    try:
        import psutil as _psutil
        rss_mb = _psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        msg = f"[MEM] {label} — RSS={rss_mb:.1f} MB"
    except Exception as exc:
        msg = f"[MEM] {label} — psutil error: {exc}"
    print(msg, flush=True)
    log.info(msg)


def _rebuild_chroma_index(client: chromadb.PersistentClient, raison: str) -> chromadb.Collection:
    """
    Reconstruit la collection Chroma en encodant les chunks via embed_texts().
    Chemin anormal en production : l'index est construit au build Docker
    (src/index_chroma.py, à partir des embeddings pré-calculés). Le passer ici
    signifie des appels réels à l'API d'embeddings depuis le serveur, d'où le
    WARNING (visible dans Cloud Logging, sans aucun contenu).
    """
    import hashlib as _hashlib

    chunks_path = ROOT / "data" / "chunks" / "chunks.json"
    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)
    log.warning(
        "CHROMA rebuild au runtime : raison=%s chunks=%d modele=%s — appels à l'API "
        "d'embeddings depuis le serveur (l'index aurait dû être construit au build)",
        raison, len(chunks), MODEL_NAME,
    )

    # Encodage AVANT de supprimer l'ancienne collection : si l'API échoue,
    # l'erreur remonte sans avoir détruit l'index existant.
    emb_list = embed_texts([c["text"] for c in chunks])

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "model_name": MODEL_NAME},
    )

    def _id(c: dict) -> str:
        key = f"{c['metadata']['source_doc']}_{c['metadata']['article_num']}_{c['text'][:50]}"
        return _hashlib.md5(key.encode()).hexdigest()

    ids = [_id(c) for c in chunks]
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            embeddings=emb_list[i : i + batch_size],
            documents=[c["text"] for c in chunks[i : i + batch_size]],
            metadatas=[c["metadata"] for c in chunks[i : i + batch_size]],
        )

    log.info("CHROMA rebuild terminé — %d documents", collection.count())
    return collection


def get_chroma_col() -> chromadb.Collection:
    global _chroma_client, _chroma_col
    if _chroma_col is None:
        # Verrou : évite que deux sessions Streamlit démarrant en même temps dans le
        # même processus ne déclenchent chacune une reconstruction concurrente.
        # Double-check locking : les conditions de déclenchement ci-dessous sont
        # inchangées, seule la synchronisation est ajoutée.
        with _chroma_lock:
            if _chroma_col is None:
                _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))

                raison = None
                try:
                    col = _chroma_client.get_collection(COLLECTION_NAME)
                    modele_index = (col.metadata or {}).get("model_name")
                    if modele_index != MODEL_NAME:
                        raison = f"modele_index={modele_index}"
                    elif col.count() == 0:
                        raison = "collection_vide"
                    else:
                        _chroma_col = col
                except Exception:
                    raison = "collection_absente"

                if raison is not None:
                    _chroma_col = _rebuild_chroma_index(_chroma_client, raison)

                log.info(
                    "CHROMA loaded: collection=%r count=%d id=%s",
                    _chroma_col.name,
                    _chroma_col.count(),
                    _chroma_col.id,
                )
    return _chroma_col


# Défauts SDK (anthropic 0.111.0, vérifiés dans anthropic._base_client) :
# Timeout(connect=5.0, read=600, write=600, pool=600), max_retries=2. Cloud Run
# coupe toute requête — y compris le WebSocket long-lived de Streamlit
# (`/_stcore/stream`) — à timeoutSeconds du service : relevé à 1800s (30 min)
# depuis le 22/09/2026, relevé de 300s posé au lot 0. Incident daté du
# 22/09/2026 (test réel lot 2a) : à 300s, toute session visiteur dépassant
# ~5 min (upload ou non — pas spécifique au lot 2a) se faisait couper son
# WebSocket par Cloud Run, provoquant une tentative de reconnexion qui
# retombait dans le même piège et déclenchait une rafale de 429 (confirmé par
# corrélation temporelle exacte : 3 fermetures de WebSocket à ~301,00xs après
# ouverture, alignées sur --timeout 300, dans les logs Cloud Run bruts).
# Avec 1800s, un read=600s par appel Anthropic reste toujours sans effet
# pratique (Cloud Run coupe après, mais bien plus tard qu'avant). Le SDK
# retente sur 408/409/429/5xx (sauf en-tête x-should-retry:false) et sur
# APIConnectionError/APITimeoutError (vérifié dans _should_retry/
# _should_retry_exception de la source installée) ; walk du __cause__ compris.
# VALEURS PROVISOIRES — à réajuster après mesure de la latence réelle par
# appel (non mesurée à ce jour, seule la latence totale du pipeline l'est,
# via le golden set : médiane 18,65s pour 3-6 appels).
ANTHROPIC_TIMEOUT = anthropic.Timeout(connect=5.0, read=60.0, write=60.0, pool=60.0)
ANTHROPIC_MAX_RETRIES = 1


def get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            timeout=ANTHROPIC_TIMEOUT,
            max_retries=ANTHROPIC_MAX_RETRIES,
        )
    return _anthropic_client


# ─────────────────────────────────────────────
# Moteur Mistral (chemin upload uniquement — voir llm_call)
# ─────────────────────────────────────────────

# Aucune valeur par défaut dans le code (décision du 24/09/2026), aucune valeur
# devinée. Sans MISTRAL_MODEL dans l'environnement, la comparaison est
# indisponible (voir mistral_disponible()). Modèle retenu au sous-lot 3.0
# (25/09/2026) : mistral-large-2512 — seul modèle tarifé, voir
# MISTRAL_PRICED_MODEL ; tout autre modèle donne un coût "non disponible".
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL")

# Endpoint : UE par défaut. Le SDK Mistral 2.10.1 accepte `server=` (nom) en plus
# de `server_url=` (mistralai/client/sdk.py:80,82), avec la table
# {"global", "eu", "us"} de sdkconfiguration.py:25-29.
# Deux pièges vérifiés dans sdkconfiguration.py:51-60 (get_server_details) :
#   - un `server` vide retombe SILENCIEUSEMENT sur "global" (lignes 54-55),
#     endpoint sur lequel Mistral ne s'engage sur aucun lieu d'inférence
#     (https://docs.mistral.ai/inference/regional-inference) ;
#   - un `server_url` non vide l'emporte sur `server` (lignes 52-53).
# On ne transmet donc au SDK qu'un nom validé et non vide, jamais server_url.
# Liste écrite en dur pour ne pas importer mistralai au chargement du module ;
# un test compare ces valeurs aux clés de SERVERS du SDK installé.
MISTRAL_SERVERS_VALIDES = ("eu", "us", "global")
MISTRAL_SERVER_DEFAUT = "eu"


def _resolve_mistral_server() -> str:
    """
    Lit MISTRAL_SERVER. Absente, vide ou faite uniquement d'espaces : "eu".
    Sinon comparaison EXACTE (ni strip, ni normalisation de casse) : toute
    valeur inconnue lève ValueError, jamais de repli sur "global".
    """
    brut = os.environ.get("MISTRAL_SERVER")
    if brut is None or brut.strip() == "":
        return MISTRAL_SERVER_DEFAUT
    if brut not in MISTRAL_SERVERS_VALIDES:
        raise ValueError(
            f"MISTRAL_SERVER invalide : {brut!r}. Valeurs acceptées : "
            f"{', '.join(MISTRAL_SERVERS_VALIDES)} (minuscules, sans espaces)."
        )
    return brut


MISTRAL_SERVER = _resolve_mistral_server()


def mistral_endpoint_host() -> str:
    """Nom d'hôte de l'endpoint choisi, dérivé de la table SERVERS du SDK."""
    from urllib.parse import urlparse

    from mistralai.client.sdkconfiguration import SERVERS

    return urlparse(SERVERS[MISTRAL_SERVER]).hostname


# Mêmes timeouts que côté Anthropic. Le SDK Mistral 2.10.1 n'expose pas d'objet
# Timeout propre : il accepte un httpx.Client personnalisé (constructeur
# `Mistral(client=...)`), ce qui revient au même réglage.
MISTRAL_TIMEOUT_CONNECT_S = 5.0
MISTRAL_TIMEOUT_RW_S = 60.0

# Politique de réessai — écrite ici plutôt que déléguée au SDK Mistral, parce
# que celui-ci ne sait pas exprimer "exactement 1 réessai" : son modèle est un
# budget de temps (BackoffStrategy(initial_interval, max_interval, exponent,
# max_elapsed_time) en ms) et sa boucle `while True` ne s'arrête que sur
# `now - start > max_elapsed_time` (mistralai/client/utils/retries.py:305-314),
# sans aucun compteur de tentatives. Le client Mistral est donc construit sans
# RetryConfig (défaut du SDK = aucun réessai, sdkconfiguration.py:48) et le
# réessai unique est fait ici.
#
# Les catégories réessayées reproduisent celles du SDK anthropic 0.111.0, pour
# que la comparaison entre moteurs ne soit pas biaisée par des politiques
# différentes :
#   - codes HTTP 408, 409, 429 et >= 500 (_base_client.py:855-872)
#   - erreurs de connexion et de timeout : APIConnectionError, dont
#     APITimeoutError hérite (_exceptions.py:86,91), traitées comme
#     réessayables (_base_client.py:897-898)
# L'en-tête propriétaire `x-should-retry` d'Anthropic (_base_client.py:844-852)
# n'a pas d'équivalent Mistral : non repris.
MISTRAL_RETRY_STATUS_CODES = (408, 409, 429)

# Délai avant réessai. Retry-After est respecté s'il est présent et plafonné,
# comme le fait le SDK anthropic (0 < retry_after <= 60, _base_client.py:828).
# Sinon délai fixe calé sur INITIAL_RETRY_DELAY = 0.5 du SDK anthropic
# (_constants.py:13 ; son premier réessai attend 0.5 * 2**0 = 0.5s avant
# jitter). VALEURS PROVISOIRES, comme ANTHROPIC_TIMEOUT.
MISTRAL_RETRY_DELAY_S = 0.5
MISTRAL_RETRY_AFTER_CAP_S = 60.0

# Jamais plus de 2 tentatives au total (1 appel + 1 réessai).
MISTRAL_MAX_ATTEMPTS = 2

_mistral_client = None


class MistralUnavailableError(Exception):
    """
    Levée quand le moteur Mistral n'est pas configuré (clé ou modèle absent).
    Ne doit jamais interrompre le reste de l'application : seule la
    comparaison devient indisponible.
    """


def mistral_disponible() -> bool:
    """Vrai si le moteur Mistral est configuré côté serveur (clé ET modèle)."""
    return bool(os.environ.get("MISTRAL_API_KEY")) and bool(MISTRAL_MODEL)


def mistral_embeddings_disponible() -> bool:
    """
    Vrai si l'API d'embeddings Mistral est utilisable : la clé suffit.
    Distinct de mistral_disponible() : MISTRAL_MODEL ne concerne que le moteur
    de chat comparé sur le chemin upload, pas l'encodage.
    """
    return bool(os.environ.get("MISTRAL_API_KEY"))


def get_mistral():
    """Client Mistral pour le moteur de chat : exige la clé ET MISTRAL_MODEL."""
    if not mistral_disponible():
        raise MistralUnavailableError("MISTRAL_API_KEY ou MISTRAL_MODEL absent")
    return _get_mistral_client()


def _get_mistral_client():
    """
    Client Mistral unique du processus, partagé par le chat et les embeddings
    (même endpoint MISTRAL_SERVER, mêmes timeouts). Ne vérifie que la clé :
    chaque appelant contrôle sa propre disponibilité avant.
    """
    global _mistral_client
    if _mistral_client is None:
        import httpx
        from mistralai.client import Mistral

        _mistral_client = Mistral(
            api_key=os.environ["MISTRAL_API_KEY"],
            server=MISTRAL_SERVER,
            client=httpx.Client(
                timeout=httpx.Timeout(
                    connect=MISTRAL_TIMEOUT_CONNECT_S,
                    read=MISTRAL_TIMEOUT_RW_S,
                    write=MISTRAL_TIMEOUT_RW_S,
                    pool=MISTRAL_TIMEOUT_RW_S,
                )
            ),
        )
    return _mistral_client


def _mistral_status_code(exc: Exception) -> int | None:
    """Code HTTP porté par une exception Mistral, s'il y en a un.

    MistralError expose .status_code (message/status_code/headers/body/
    raw_response) — une seule classe de base, contrairement aux exceptions
    typées par statut du SDK anthropic.
    """
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _mistral_should_retry(exc: Exception) -> bool:
    """Reproduit les catégories réessayées par le SDK anthropic (voir plus haut)."""
    import httpx

    if isinstance(exc, (httpx.NetworkError, httpx.TimeoutException)):
        return True
    code = _mistral_status_code(exc)
    if code is None:
        return False
    return code in MISTRAL_RETRY_STATUS_CODES or code >= 500


def _mistral_retry_delay_s(exc: Exception) -> float:
    """Délai avant réessai : Retry-After plafonné si présent, sinon délai fixe."""
    headers = getattr(exc, "headers", None)
    brut = None
    if headers is not None:
        try:
            brut = headers.get("retry-after")
        except Exception:
            brut = None
    if brut is not None:
        try:
            propose = float(brut)
        except (TypeError, ValueError):
            propose = None
        if propose is not None and propose > 0:
            return min(propose, MISTRAL_RETRY_AFTER_CAP_S)
    return MISTRAL_RETRY_DELAY_S


# ─────────────────────────────────────────────
# Embeddings (API Mistral — sous-lot 2.1)
# ─────────────────────────────────────────────
# Point d'entrée UNIQUE de tout encodage : questions (mode corpus et mode
# upload), passages HyDE, chunks du corpus (reconstruction runtime et script
# de pré-calcul) et chunks d'un document uploadé.
# Aucun préfixe "query: " / "passage: " : convention propre à e5, la doc
# Mistral n'en utilise pas. Vecteurs de norme 1 d'après la doc Mistral : la
# métrique cosine des collections Chroma reste inchangée.
# Pas de repli vers un modèle local : en cas d'indisponibilité ou d'erreur,
# EmbeddingServiceError remonte et l'interface affiche un message neutre
# (format_user_error).

# Dimension attendue des vecteurs mistral-embed. Vérifiée sur chaque vecteur
# reçu : un écart (autre modèle configuré, changement côté fournisseur) ferait
# échouer l'insertion dans un index existant, ou pire, mélangerait deux
# espaces de vecteurs incomparables.
EMBED_DIMENSION = 1024

# Taille de lot : la limite officielle (nombre d'entrées et tokens par
# requête) n'est pas documentée dans la doc du SDK consultée le 03/10/2026.
# Valeur prudente : 16 textes par requête. Les chunks font au plus ~2 000
# caractères (corpus : 1 977 max ; upload : tronqués à MAX_CHUNK_CHARS), soit
# environ 32 000 caractères par requête au pire. Si l'API refuse un lot, le
# code HTTP est journalisé (sans contenu) et EmbeddingServiceError remonte.
EMBED_BATCH_SIZE = 16


class EmbeddingServiceError(Exception):
    """
    Encodage impossible : clé absente, erreur de l'API après réessai, ou
    réponse inattendue (nombre ou dimension des vecteurs). Le message ne
    contient jamais de texte encodé ; il n'est de toute façon jamais affiché
    au visiteur (voir format_user_error).
    """


def _log_appel_embeddings(response, tentative: int, n_textes: int) -> None:
    """Audit d'un appel d'embeddings réussi, même logique que _log_appel_mistral. Aucun contenu."""
    audit_log.info(
        "EMBED_CALL moteur=mistral endpoint=%s server=%s modele_demande=%s "
        "modele_servi=%s request_id=%s n_textes=%d tentative=%d/%d",
        mistral_endpoint_host(),
        MISTRAL_SERVER,
        MISTRAL_EMBED_MODEL,
        getattr(response, "model", None) or "absent",
        getattr(response, "id", None) or "absent",
        n_textes,
        tentative,
        MISTRAL_MAX_ATTEMPTS,
    )


def _embed_batch(client, lot: list[str]) -> list[list[float]]:
    """Un appel à l'API pour un lot, avec la politique de réessai du moteur de chat."""
    for tentative in range(1, MISTRAL_MAX_ATTEMPTS + 1):
        try:
            response = client.embeddings.create(model=MISTRAL_EMBED_MODEL, inputs=lot)
        except Exception as exc:
            reessai = tentative < MISTRAL_MAX_ATTEMPTS and _mistral_should_retry(exc)
            # Jamais le texte encodé dans le log : type, statut, taille du lot.
            log.warning(
                "EMBED_ERROR endpoint=%s server=%s modele=%s type=%s status_code=%s "
                "n_textes=%d tentative=%d/%d reessai=%s",
                mistral_endpoint_host(),
                MISTRAL_SERVER,
                MISTRAL_EMBED_MODEL,
                type(exc).__name__,
                _mistral_status_code(exc),
                len(lot),
                tentative,
                MISTRAL_MAX_ATTEMPTS,
                reessai,
            )
            if not reessai:
                raise EmbeddingServiceError(
                    f"échec de l'API d'embeddings ({type(exc).__name__}, "
                    f"status_code={_mistral_status_code(exc)})"
                ) from exc
            time.sleep(_mistral_retry_delay_s(exc))
            continue

        _log_appel_embeddings(response, tentative, len(lot))
        donnees = sorted(response.data or [], key=lambda d: d.index if d.index is not None else 0)
        vecteurs = [d.embedding for d in donnees]
        if len(vecteurs) != len(lot) or any(v is None for v in vecteurs):
            log.warning(
                "EMBED_REPONSE_INVALIDE attendus=%d recus=%d modele=%s",
                len(lot), len(vecteurs), MISTRAL_EMBED_MODEL,
            )
            raise EmbeddingServiceError("nombre de vecteurs reçus différent du nombre de textes")
        dimensions = {len(v) for v in vecteurs}
        if dimensions != {EMBED_DIMENSION}:
            log.warning(
                "EMBED_DIMENSION_INATTENDUE attendue=%d recue=%s modele=%s",
                EMBED_DIMENSION, sorted(dimensions), MISTRAL_EMBED_MODEL,
            )
            raise EmbeddingServiceError(f"dimension inattendue {sorted(dimensions)}")
        return vecteurs
    # Inatteignable : la boucle sort par return ou par raise.
    raise EmbeddingServiceError("boucle de réessai épuisée")


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Encode `texts` via l'API d'embeddings Mistral, par lots de
    EMBED_BATCH_SIZE, en conservant l'ordre. Un vecteur de EMBED_DIMENSION
    floats par texte. Lève EmbeddingServiceError si la clé est absente ou si
    un lot échoue (après le réessai unique pour les erreurs réessayables).
    """
    if not texts:
        return []
    if not mistral_embeddings_disponible():
        log.warning("EMBED_INDISPONIBLE MISTRAL_API_KEY absente — aucun encodage possible")
        raise EmbeddingServiceError("MISTRAL_API_KEY absente")
    client = _get_mistral_client()
    vecteurs: list[list[float]] = []
    for debut in range(0, len(texts), EMBED_BATCH_SIZE):
        vecteurs.extend(_embed_batch(client, texts[debut : debut + EMBED_BATCH_SIZE]))
    return vecteurs


# ─────────────────────────────────────────────
# Prompt système
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un assistant spécialisé dans les contrats d'assurance ARESIA Assurances.

Règles non négociables :
1. GROUNDING STRICT : Tu ne dois utiliser QUE les informations présentes dans les chunks fournis. Aucune connaissance générale sur les garanties, montants, délais ou règles d'assurance.
2. CITATION OBLIGATOIRE : Chaque affirmation doit être sourcée avec le format exact : [Article X.Y des CG {Produit} — v{version}]
3. HONNÊTETÉ SUR LES LIMITES : Si l'information n'est pas dans les chunks, réponds EXACTEMENT :
   "Je ne trouve pas cette information dans les documents disponibles. Je vous recommande de contacter votre référent produit ou le service technique de ARESIA Assurances."
   Ne jamais inventer, extrapoler ou inférer au-delà des chunks.
4. LANGAGE ACCESSIBLE : Explique le jargon technique en une phrase si indispensable.
5. FORMAT EN 3 BLOCS OBLIGATOIRE :
   **Réponse directe** : [réponse factuelle et concise]
   **Source(s)** : [citations exactes avec articles]
   **Point d'attention** : [mise en garde ou nuance importante]
6. QUESTIONS FISCALES/SUCCESSORALES COMPLEXES : Recommander un expert (notaire, conseiller fiscal), jamais d'interprétation personnelle."""


# ─────────────────────────────────────────────
# Helpers LLM
# ─────────────────────────────────────────────

def exceeds_max_length(text: str, max_chars: int) -> bool:
    """Vrai si `text` dépasse `max_chars` caractères — utilisé côté UI avant tout appel API."""
    return len(text) > max_chars


def format_user_error(exc: Exception) -> str:
    """
    Message neutre affiché au visiteur en cas d'échec de la pipeline.
    Ne doit JAMAIS inclure str(exc) : le message d'exception brut (potentiellement
    des détails d'implémentation, de statut HTTP, etc.) reste uniquement dans les
    logs serveur (type d'exception + horodatage, voir app.py).
    """
    if isinstance(exc, DailyLimitExceeded):
        return "Le service a atteint sa limite d'usage pour aujourd'hui. Merci de revenir demain."
    if isinstance(exc, ComparisonDailyLimitExceeded):
        return (
            f"Limite quotidienne atteinte : cette démo traite au maximum {COMPARISON_DAILY_LIMIT} "
            "questions par jour sur les documents uploadés, tous visiteurs confondus, pour "
            "maîtriser son coût. Votre question n'a pas été envoyée. Réessayez demain, ou "
            "quittez le mode document (« Nouveau document ») pour interroger le corpus ARESIA, "
            "qui a sa propre limite quotidienne."
        )
    if isinstance(exc, MistralUnavailableError):
        return "La comparaison entre moteurs n'est pas disponible pour le moment."
    if isinstance(exc, EmbeddingServiceError):
        return (
            "La recherche dans les documents est momentanément indisponible. Merci de "
            "réessayer dans quelques instants."
        )
    return "Une erreur technique est survenue. Merci de réessayer dans quelques instants."


def _record_usage(response) -> None:
    """
    Enregistre response.usage dans le tracker de la question en cours, s'il y
    en a un (_usage_ctx est None hors d'un run_agent(), ex. tests unitaires
    appelant llm_call/llm_json directement — ne rien faire, sans erreur).
    Si response n'a pas d'attribut usage, ne plante pas : log WARNING sans
    contenu (ni texte de réponse, ni question).
    """
    tracker = _usage_ctx.get()
    if tracker is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        log.warning("LLM_USAGE reponse sans attribut usage — non comptabilisee")
        return
    tracker.record(usage)


def _record_usage_mistral(response) -> None:
    """
    Équivalent de _record_usage() pour la forme Mistral : l'objet usage y
    expose prompt_tokens/completion_tokens là où Anthropic expose
    input_tokens/output_tokens.
    """
    tracker = _usage_ctx.get()
    if tracker is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        log.warning("LLM_USAGE reponse sans attribut usage — non comptabilisee")
        return
    tracker.record_tokens(
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


def _log_appel_mistral(response, tentative: int) -> None:
    """
    Un enregistrement d'audit par appel Mistral RÉUSSI : hôte de l'endpoint,
    nom du serveur, modèle demandé et servi, identifiant de requête.
    L'identifiant est response.id (mistralai/client/models/
    chatcompletionresponse.py:22) : seul disponible en cas de succès, le SDK
    abandonnant l'objet httpx.Response (chat.py:289). Lu par getattr : un champ
    absent s'affiche "absent" et ne peut jamais faire échouer un appel nominal.
    Aucun contenu de question, de réponse ni de document.
    """
    audit_log.info(
        "LLM_CALL moteur=mistral endpoint=%s server=%s modele_demande=%s "
        "modele_servi=%s request_id=%s tentative=%d/%d",
        mistral_endpoint_host(),
        MISTRAL_SERVER,
        MISTRAL_MODEL,
        getattr(response, "model", None) or "absent",
        getattr(response, "id", None) or "absent",
        tentative,
        MISTRAL_MAX_ATTEMPTS,
    )


def _llm_call_mistral(messages: list[dict], system: str) -> str:
    """
    Appel Mistral avec un réessai unique (voir la politique de réessai plus
    haut : catégories reprises du SDK anthropic, 2 tentatives maximum).
    L'usage n'est comptabilisé que pour la tentative qui réussit — un réessai
    ne double pas les tokens comptés, et ne touche pas le disjoncteur des
    comparaisons (compté une fois par comparaison, pas par appel).
    Le système est passé comme premier message de rôle "system" : le SDK
    Mistral n'a pas de paramètre `system=` séparé, mais accepte un dict brut
    {"role": "system", "content": ...} (SystemMessageTypedDict, membre de
    l'union ChatCompletionRequestMessageTypedDict).
    """
    client = get_mistral()
    messages_mistral = [{"role": "system", "content": system}] + messages
    derniere_exc: Exception | None = None
    for tentative in range(1, MISTRAL_MAX_ATTEMPTS + 1):
        try:
            response = client.chat.complete(
                model=MISTRAL_MODEL,
                max_tokens=1500,
                messages=messages_mistral,
            )
        except Exception as exc:
            derniere_exc = exc
            if tentative >= MISTRAL_MAX_ATTEMPTS or not _mistral_should_retry(exc):
                raise
            # Jamais le contenu de la question ni de la réponse dans le log.
            log.warning(
                "LLM_RETRY moteur=mistral endpoint=%s server=%s status_code=%s tentative=%d/%d",
                mistral_endpoint_host(),
                MISTRAL_SERVER,
                _mistral_status_code(exc),
                tentative,
                MISTRAL_MAX_ATTEMPTS,
            )
            time.sleep(_mistral_retry_delay_s(exc))
            continue
        _record_usage_mistral(response)
        _log_appel_mistral(response, tentative)
        return response.choices[0].message.content
    # Inatteignable : la boucle sort par return ou par raise.
    raise derniere_exc  # type: ignore[misc]


def llm_call(
    messages: list[dict], system: str = SYSTEM_PROMPT, engine: str = ENGINE_ANTHROPIC
) -> str:
    """
    Appel LLM texte libre. `engine` vaut "anthropic" par défaut : tous les
    appelants existants (mode corpus, chemin upload simple) empruntent donc
    exactement le même chemin de code qu'avant l'introduction de Mistral.
    Seul le mode comparaison du chemin upload passe engine="mistral".
    """
    global _turn_llm_seq
    _turn_llm_seq += 1
    seq = _turn_llm_seq
    if engine == ENGINE_MISTRAL:
        return _llm_call_mistral(messages, system)
    if engine != ENGINE_ANTHROPIC:
        raise ValueError(f"moteur inconnu: {engine!r}")
    client = get_anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        system=system,
        messages=messages,
    )
    _record_usage(response)
    return response.content[0].text


class LLMResponseError(Exception):
    """Levée quand la réponse JSON du modèle ne peut pas être parsée (option (a),
    aucune nouvelle tentative — voir llm_json)."""


def llm_json(messages: list[dict], system: str) -> dict:
    """Appel LLM avec sortie JSON stricte. temperature=0 pour la reproductibilité."""
    global _turn_llm_seq
    _turn_llm_seq += 1
    seq = _turn_llm_seq
    client = get_anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        temperature=0,
        system=system + "\n\nRéponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans explication.",
        messages=messages,
    )
    _record_usage(response)  # avant tout parsing : compté même si le JSON est invalide ensuite
    text = response.content[0].text.strip()
    # Nettoyer les balises markdown si présentes
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Aucune nouvelle tentative (option (a)) : échec propre, 1 seul appel API.
        # Jamais le contenu de la réponse ni de la question dans le log.
        log.warning(
            "LLM_JSON parse_error stop_reason=%s text_len=%d",
            response.stop_reason,
            len(text),
        )
        # `from exc` : __cause__ = ce JSONDecodeError, dont seul le TYPE est jamais
        # relu (app.py:RUN_AGENT log cause_type via type(e.__cause__).__name__,
        # jamais son message) — préserve un diagnostic utile sans fuite de contenu.
        raise LLMResponseError("Réponse LLM non-JSON après nettoyage markdown") from exc


def embed_query(text: str) -> list[float]:
    import math
    global _turn_encode_seq
    _turn_encode_seq += 1
    seq = _turn_encode_seq
    vec = embed_texts([text])[0]
    norm = math.sqrt(sum(x * x for x in vec))
    log.debug("EMBED query=%r norm=%.4f first5=%s", text[:60], norm, vec[:5])
    return vec


def retrieve_chunks(query: str, doc_filter: str | None = None, k: int = RETRIEVAL_K) -> list[dict]:
    col = get_chroma_col()
    log.info(
        "RETRIEVE col=%r count=%d id=%s filter=%r query=%r",
        col.name, col.count(), col.id, doc_filter, query[:60],
    )
    emb = embed_query(query)
    where = {"source_doc": doc_filter} if doc_filter else None
    results = col.query(
        query_embeddings=[emb],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({"text": doc, "metadata": meta, "distance": dist})
    top3 = [(c["metadata"]["source_doc"], c["metadata"]["article_num"], round(c["distance"], 4)) for c in chunks[:3]]
    log.info("RETRIEVE top3=%s", top3)
    return chunks


def format_chunks_for_prompt(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        m = c["metadata"]
        ref = f"[Article {m['article_num']} — {m['titre_humain']} v{m['version']}]"
        parts.append(f"--- Chunk {i} {ref} ---\n{c['text']}")
    return "\n\n".join(parts)


def append_log(state: AgentState, entry: dict) -> None:
    state["trace_log"].append(entry)


# ─────────────────────────────────────────────
# Nœud 1 : router
# ─────────────────────────────────────────────

def router(state: AgentState) -> AgentState:
    question = state["question_originale"]
    system = (
        "Tu es un classificateur de questions d'assurance. "
        "Détermine si la question comporte PLUSIEURS composantes distinctes qui nécessitent des articles différents pour répondre. "
        "Active Plan-and-Execute si la question : "
        "(1) mentionne explicitement deux garanties ou deux produits différents, "
        "(2) combine une définition ET un montant/barème, "
        "(3) pose 'ET' ou 'avec' entre deux sujets distincts (ex: 'franchise ET rente complémentaire'). "
        "Réponds avec {\"multi_composantes\": true/false, \"raison\": \"...\"}."
    )
    result = llm_json(
        [{"role": "user", "content": f"Question : {question}"}],
        system=system,
    )
    multi = result.get("multi_composantes", False)

    append_log(state, {
        "etape": "router",
        "sous_question": question,
        "chunks_recus": 0,
        "decision": "plan_and_execute" if multi else "react_simple",
        "raison": result.get("raison", ""),
        "action_suivante": "planner" if multi else "retrieve",
    })
    # Si mono-composante : créer une seule sous-question
    if not multi:
        state["sous_questions"] = [{"texte": question, "doc_cible_probable": state.get("produit_filtre")}]
    return state


def route_after_router(state: AgentState) -> str:
    log = state["trace_log"][-1]
    return "planner" if log["decision"] == "plan_and_execute" else "retrieve"


# ─────────────────────────────────────────────
# Nœud 2 : planner
# ─────────────────────────────────────────────

def planner(state: AgentState) -> AgentState:
    question = state["question_originale"]
    system = (
        "Tu es un planificateur RAG d'assurance. Décompose la question en 2-4 sous-questions autonomes. "
        "Chaque sous-question doit être répondable indépendamment avec un seul article contractuel. "
        "Pour chaque sous-question, indique le doc_cible_probable UNIQUEMENT parmi ces options exactes :\n"
        "- CG-PREV-INV-2024 : invalidité, ITT, IPT, IPP, arrêt de travail, prévoyance, rente invalidité\n"
        "- CG-AV-MULTI-2024 : assurance vie, Patrimoine+, fonds euros, UC, rachat, avance, versement, fiscalité AV\n"
        "- BAR-IARD-2024-V2 : MRH, habitation, auto, RC Pro, franchise auto, sinistres IARD\n"
        "- ACPR-REC-2024-12 : devoir de conseil, DRIB, KYC, formation DDA, traçabilité réglementaire\n"
        "- null : si incertain\n"
        "Format attendu : {\"sous_questions\": [{\"texte\": \"...\", \"doc_cible_probable\": \"CG-PREV-INV-2024\"}]}"
    )
    result = llm_json(
        [{"role": "user", "content": f"Question à décomposer : {question}"}],
        system=system,
    )
    sous_questions = result.get("sous_questions", [{"texte": question, "doc_cible_probable": None}])
    if len(sous_questions) > MAX_SUBQUESTIONS:
        log.error(
            "PLANNER troncature: %d -> %d sous-questions, horodatage=%s",
            len(sous_questions), MAX_SUBQUESTIONS, datetime.now(timezone.utc).isoformat(),
        )
        sous_questions = sous_questions[:MAX_SUBQUESTIONS]

    append_log(state, {
        "etape": "planner",
        "sous_question": question,
        "chunks_recus": 0,
        "decision": f"{len(sous_questions)} sous-questions",
        "raison": f"Décomposition : {[sq['texte'] for sq in sous_questions]}",
        "action_suivante": "retrieve",
    })
    state["sous_questions"] = sous_questions
    return state


# ─────────────────────────────────────────────
# Nœud 3 : retrieve
# ─────────────────────────────────────────────

def retrieve(state: AgentState) -> AgentState:
    if not state.get("resultats"):
        state["resultats"] = []

    for sq in state["sous_questions"]:
        # Ne pas re-retriever si déjà traité
        already = next((r for r in state["resultats"] if r["sous_question"] == sq["texte"]), None)
        if already and already.get("suffisant"):
            continue

        texte = sq["texte"]
        doc_cible = sq.get("doc_cible_probable") or state.get("produit_filtre")
        chunks = retrieve_chunks(texte, doc_filter=doc_cible)

        existing = next((r for r in state["resultats"] if r["sous_question"] == texte), None)
        if existing is None:
            state["resultats"].append({
                "sous_question": texte,
                "chunks": chunks,
                "suffisant": False,
                "tentatives": 1,
                "methode_reformulation": None,
            })
        else:
            existing["chunks"] = chunks
            existing["tentatives"] = existing.get("tentatives", 0) + 1

        append_log(state, {
            "etape": "retrieve",
            "sous_question": texte,
            "chunks_recus": len(chunks),
            "decision": f"top chunk: [{chunks[0]['metadata']['source_doc']}] Art.{chunks[0]['metadata']['article_num']}" if chunks else "aucun",
            "raison": f"filtre doc={doc_cible}",
            "action_suivante": "evaluate",
        })
    return state


# ─────────────────────────────────────────────
# Nœud 4 : evaluate
# ─────────────────────────────────────────────

def evaluate_sufficiency(sous_question: str, chunks: list[dict]) -> dict:
    chunks_text = format_chunks_for_prompt(chunks)
    system = "Tu évalues si des chunks documentaires permettent de répondre à une question précise."
    result = llm_json(
        [{
            "role": "user",
            "content": (
                f"Question : {sous_question}\n\n"
                f"Chunks disponibles :\n{chunks_text}\n\n"
                "Ces chunks permettent-ils de répondre précisément à la question ?\n"
                "Réponds avec {\"suffisant\": true/false, \"raison\": \"...\"}"
            ),
        }],
        system=system,
    )
    return result


def evaluate(state: AgentState) -> AgentState:
    for res in state["resultats"]:
        if res.get("suffisant"):
            continue

        eval_result = evaluate_sufficiency(res["sous_question"], res["chunks"])
        llm_suffisant = eval_result.get("suffisant", False)
        raison = eval_result.get("raison", "")

        tentatives = res.get("tentatives", 1)
        if llm_suffisant:
            res["suffisant"] = True
            action = "synthesize"
            decision = "suffisant"
        elif tentatives < 3:  # autorise jusqu'à 2 reformulations (niveau 1 + niveau 2)
            action = f"reformulate_niveau_{tentatives}"
            decision = "insuffisant"
        else:
            res["suffisant"] = True   # marquer terminé pour sortir de la boucle
            res["non_trouve"] = True
            action = "non_trouve"
            decision = "non_trouve"

        log.info(
            "EVALUATE sq=%r tentatives=%d decision=%s raison=%r",
            res["sous_question"][:60], tentatives, decision, raison[:80],
        )
        append_log(state, {
            "etape": "evaluate",
            "sous_question": res["sous_question"],
            "chunks_recus": len(res["chunks"]),
            "decision": decision,
            "raison": raison,
            "action_suivante": action,
        })
    return state


def route_after_evaluate(state: AgentState) -> str:
    """Décide si on reformule (jusqu'à 2 tentatives) ou synthétise."""
    needs_reformulation = any(
        not r.get("suffisant") and r.get("tentatives", 1) < 3
        for r in state.get("resultats", [])
    )
    if needs_reformulation:
        return "reformulate"
    return "synthesize"


# ─────────────────────────────────────────────
# Nœud 5 : reformulate
# ─────────────────────────────────────────────

def _hyde_retrieve(question: str, doc_cible: str | None) -> list[dict]:
    """HyDE : génère un passage hypothétique et l'utilise comme vecteur de recherche."""
    import math as _math
    system = (
        "Tu es expert en rédaction de conditions générales d'assurance. "
        "Génère un court extrait de contrat (3-6 lignes) qui répondrait à la question ci-dessous. "
        "Utilise le style des CG : numérotation d'article, valeurs chiffrées précises, "
        "termes techniques assurantiels (franchise, délai de carence, ITT, IPT, etc.). "
        "L'extrait doit ressembler à un vrai paragraphe de conditions générales. "
        "Réponds avec {\"passage_hypothetique\": \"...\"}."
    )
    result = llm_json([{"role": "user", "content": f"Question : {question}"}], system=system)
    passage = result.get("passage_hypothetique", question)
    # Le passage hypothétique est encodé comme un chunk : son vecteur est plus proche des chunks réels
    global _turn_encode_seq
    _turn_encode_seq += 1
    seq = _turn_encode_seq
    vec = embed_texts([passage])[0]
    norm = _math.sqrt(sum(x * x for x in vec))
    log.info("HyDE passage='%s...' norm=%.4f", passage[:80], norm)
    col = get_chroma_col()
    where = {"source_doc": doc_cible} if doc_cible else None
    results = col.query(
        query_embeddings=[vec],
        n_results=RETRIEVAL_K,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({"text": doc, "metadata": meta, "distance": dist})
    top3 = [(c["metadata"]["source_doc"], c["metadata"]["article_num"], round(c["distance"], 4)) for c in chunks[:3]]
    log.info("HyDE RETRIEVE top3=%s", top3)
    return chunks


def reformulate(state: AgentState) -> AgentState:
    for res in state["resultats"]:
        if res.get("suffisant"):
            continue

        tentatives = res.get("tentatives", 1)
        sq = res["sous_question"]
        doc_cible = next(
            (s.get("doc_cible_probable") for s in state["sous_questions"] if s["texte"] == sq),
            state.get("produit_filtre"),
        )

        if tentatives == 1:
            # Niveau 1 : HyDE (Hypothetical Document Embedding)
            # L'embedding d'un passage contractuel hypothétique est plus proche des chunks réels
            # que l'embedding de la question originale, ce qui améliore le recall.
            append_log(state, {
                "etape": "reformulate",
                "sous_question": sq,
                "decision": "niveau 1 — HyDE",
                "raison": "Hypothetical Document Embedding (extrait contractuel)",
                "action_suivante": "evaluate",
            })
            chunks = _hyde_retrieve(sq, doc_cible)
            res["methode_reformulation"] = "niveau_1_hyde"

        else:
            # Niveau 2 : requête originale sans filtre document
            append_log(state, {
                "etape": "reformulate",
                "sous_question": sq,
                "decision": "niveau 2 — filtre document retiré",
                "raison": "Élargissement corpus (filtre doc retiré)",
                "action_suivante": "evaluate",
            })
            log.info("REFORMULATE niveau 2: filtre doc retiré, query='%s'", sq[:60])
            chunks = retrieve_chunks(sq, doc_filter=None)
            res["methode_reformulation"] = "niveau_2_elargissement"

        res["chunks"] = chunks
        res["tentatives"] = tentatives + 1

    return state


# ─────────────────────────────────────────────
# Nœud 6 : synthesize
# ─────────────────────────────────────────────

def synthesize(state: AgentState) -> AgentState:
    resultats = state.get("resultats", [])
    question = state["question_originale"]

    # Construire le contexte
    parts = []
    non_trouves = []
    for res in resultats:
        if res.get("non_trouve"):
            non_trouves.append(res["sous_question"])
        else:
            parts.append(
                f"[Sous-question : {res['sous_question']}]\n"
                + format_chunks_for_prompt(res["chunks"])
            )

    context = "\n\n".join(parts)
    non_trouve_note = ""
    if non_trouves:
        non_trouve_note = (
            "\n\nATTENTION : Les sous-questions suivantes n'ont pas de réponse dans les documents : "
            + ", ".join(non_trouves)
            + "\nPour ces points, utilise la phrase exacte : "
            '"Je ne trouve pas cette information dans les documents disponibles. '
            "Je vous recommande de contacter votre référent produit ou le service technique de ARESIA Assurances.\""
        )

    prompt = (
        f"Question de l'utilisateur : {question}\n\n"
        f"Documents pertinents trouvés :\n{context}"
        f"{non_trouve_note}\n\n"
        "Réponds en respectant strictement le format 3 blocs : "
        "**Réponse directe** / **Source(s)** / **Point d'attention**"
    )

    reponse = llm_call([{"role": "user", "content": prompt}])
    state["reponse_finale"] = reponse

    append_log(state, {
        "etape": "synthesize",
        "sous_question": question,
        "chunks_recus": sum(len(r.get("chunks", [])) for r in resultats),
        "decision": "reponse_generee",
        "raison": f"{len(resultats)} sous-question(s) traitée(s), {len(non_trouves)} non trouvée(s)",
        "action_suivante": "end",
    })
    return state


# ─────────────────────────────────────────────
# Construction du graphe
# ─────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("router", router)
    graph.add_node("planner", planner)
    graph.add_node("retrieve", retrieve)
    graph.add_node("evaluate", evaluate)
    graph.add_node("reformulate", reformulate)
    graph.add_node("synthesize", synthesize)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", route_after_router, {"planner": "planner", "retrieve": "retrieve"})
    graph.add_edge("planner", "retrieve")
    graph.add_edge("retrieve", "evaluate")
    graph.add_conditional_edges("evaluate", route_after_evaluate, {"reformulate": "reformulate", "synthesize": "synthesize"})
    graph.add_edge("reformulate", "evaluate")
    graph.add_edge("synthesize", END)

    return graph.compile()


# ─────────────────────────────────────────────
# Interface publique
# ─────────────────────────────────────────────

_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_agent(question: str, produit_filtre: str | None = None) -> AgentState:
    global _turn_counter, _current_turn, _turn_llm_seq, _turn_encode_seq
    _check_daily_limit()
    _turn_counter += 1
    _current_turn = _turn_counter
    _turn_llm_seq = 0
    _turn_encode_seq = 0

    graph = get_graph()
    initial_state: AgentState = {
        "question_originale": question,
        "produit_filtre": produit_filtre,
        "sous_questions": [],
        "resultats": [],
        "reponse_finale": "",
        "trace_log": [],
        "usage": {},
    }

    # Tracker neuf par question, via ContextVar (pas de variable globale) —
    # voir le commentaire au-dessus de la classe UsageTracker pour la
    # justification (propagation confirmée dans les nœuds LangGraph malgré le
    # thread pool interne).
    tracker = UsageTracker()
    token = _usage_ctx.set(tracker)
    try:
        t0 = time.perf_counter()
        result = graph.invoke(initial_state)
        latence_s = time.perf_counter() - t0
    finally:
        # Le reset doit TOUJOURS avoir lieu, y compris si graph.invoke() lève
        # (ex. LLMResponseError, DailyLimitExceeded en amont, erreur SDK).
        _usage_ctx.reset(token)

    # Atteint uniquement en cas de succès : sur exception, la ligne ci-dessus
    # a déjà relevé le finally et propagé l'erreur — aucun "usage" partiel.
    result["usage"] = {
        "n_appels": tracker.n_appels,
        "tokens_in": tracker.tokens_in,
        "tokens_out": tracker.tokens_out,
        "latence_s": latence_s,
        "cout_usd": estimer_cout_usd(tracker.tokens_in, tracker.tokens_out),
    }
    return result


# ─────────────────────────────────────────────
# Test rapide
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?"
    print(f"Question : {q}\n")

    result = run_agent(q)

    print("=== RÉPONSE ===")
    print(result["reponse_finale"])
    print("\n=== TRACE LOG ===")
    for entry in result["trace_log"]:
        print(f"[{entry['etape']}] {entry['decision']} — {entry['raison'][:80]}")

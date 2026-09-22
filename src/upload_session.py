"""
Session d'upload éphémère de contrat visiteur (lot 2a.1).

Architecture validée par deux tests préalables (sous-lot 2a.0, scratchpad, non
commités) : plusieurs EphemeralClient() vivants simultanément dans le même
process ne sont PAS isolés entre eux (fuite en lecture, list_collections() et
get_collection() croisés) — mais à UN SEUL EphemeralClient vivant à la fois
dans le process, avec purge systématique de toutes les collections éphémères
à l'ACQUISITION du verrou (pas seulement en fin de session) et
delete_collection() explicite en fin de session normale, l'étanchéité est
complète. Une session abandonnée sans delete_collection() laisse ses données
lisibles sans limite de temps observée — d'où l'exigence de purge à
l'acquisition plutôt que de compter sur un nettoyage en fin de session.

Ce module ne touche à aucun moment agent.get_chroma_col() / agent.retrieve_chunks()
/ agent.run_agent() / agent.build_graph() — la collection globale persistante et
le graphe LangGraph du chat principal restent entièrement séparés de l'index
éphémère créé ici. Seules des fonctions partagées et sans effet de bord sur la
collection globale sont réutilisées depuis agent.py : get_embed_model(),
llm_call(), format_chunks_for_prompt(), SYSTEM_PROMPT, MODEL_NAME.

Aucune dépendance à Streamlit ici : testable sans serveur, l'intégration UI
(file_uploader, session_id via streamlit.runtime.scriptrunner.get_script_run_ctx(),
affichage de UPLOAD_BUSY_MESSAGE) reste à faire dans app.py — non couverte par
ce sous-lot, voir le rapport.
"""
from __future__ import annotations

import gc
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import chromadb
import pdfplumber

import extract_chunks
from agent import (
    MODEL_NAME,
    SYSTEM_PROMPT,
    format_chunks_for_prompt,
    get_embed_model,
    llm_call,
)

log = logging.getLogger("upload_session")

# ─────────────────────────────────────────────
# Garde-fous (Partie C — valeurs proposées, À VALIDER, voir rapport)
# ─────────────────────────────────────────────

# Le modèle intfloat/multilingual-e5-large tronque silencieusement au-delà de
# 512 tokens (confirmé sous-lot 2a.0 : model card HuggingFace + max_seq_length
# mesuré localement = 512). Choix retenu : TRONQUER le chunk fautif avec
# avertissement explicite (log serveur + remonté à l'appelant pour affichage
# visiteur), plutôt que rejeter tout le document pour un seul article trop
# long — un vrai contrat peut avoir un article dense (barème, tableau de
# garanties) sans que le reste du document soit en cause. Alternative non
# retenue : rejet total du document, plus strict mais moins utile pour une
# démo dont l'objectif est de montrer le pipeline sur un document réel.
MAX_CHUNK_TOKENS = 512

# Corpus fictif actuel (mesuré, sous-lot 2a.0/2a.1) : 5 à 10 pages, 12 à 23 Ko
# par document. Un vrai contrat "conditions générales" peut être plus long que
# ces extraits de démo.
# - MAX_FILE_SIZE_BYTES = 10 Mo : très généreux vs les 12-23 Ko observés
#   (couvre un PDF scanné/image-lourd), tout en bornant le temps d'extraction
#   pdfplumber et la mémoire du process (Cloud Run : 1 CPU / 3 GiB).
# - MAX_PAGES = 40 : ~4x le plus gros document du corpus (10 pages) — au-delà,
#   probablement plusieurs documents agrégés en un seul PDF, hors du cas
#   d'usage "un contrat visiteur à la fois".
# Ni l'une ni l'autre valeur n'a été mesurée en conditions réelles (temps
# d'extraction/embedding sur un document de cette taille) — extrapolation
# linéaire uniquement, à partir de la mesure sous-lot 2a.0 (~1,2s d'embedding
# CPU pour un document taille corpus réel).
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_PAGES = 40

# Timeout d'inactivité du verrou (Partie A — À VALIDER, voir rapport) :
# démarrage à froid ~90s (lot 0/1, mesuré) + latence de réponse observée
# 12-25s une fois l'instance chaude (golden set, lot 1) + temps
# d'upload/extraction/embedding (~1-3s pour un document taille corpus, mesuré
# sous-lot 2a.0) + temps de lecture humaine de la réponse avant une éventuelle
# question de relance sur le même document. 300s (5 min) proposé : large
# marge pour 2-3 échanges espacés de lecture, sans bloquer indéfiniment le
# visiteur suivant en cas d'abandon (fermeture d'onglet sans nettoyage — cf.
# sous-lot 2a.0, résidu sans limite de temps observée sans ce timeout).
UPLOAD_LOCK_TIMEOUT_S = 300

UPLOAD_COLLECTION_PREFIX = "upload_session_"

# Texte proposé (Partie A — À VALIDER) pour le visiteur qui arrive pendant
# qu'une session d'upload est active. Pas un blocage silencieux ni une erreur
# brute : explique la contrainte (une seule analyse à la fois) et donne un
# ordre de grandeur d'attente concret.
UPLOAD_BUSY_MESSAGE = (
    "Un autre visiteur teste déjà un document en ce moment — une seule analyse "
    "à la fois sur cette démo, pour garantir qu'aucune donnée d'un contrat ne "
    "soit jamais visible par un autre visiteur. Réessayez dans quelques "
    "minutes : la session en cours se libère automatiquement au bout de "
    "5 minutes d'inactivité."
)


class UploadSessionBusyError(Exception):
    """Levée par try_acquire() quand une autre session détient déjà le verrou (non expiré)."""

    def __init__(self, held_since_s: float):
        self.held_since_s = held_since_s
        super().__init__(f"Verrou d'upload détenu depuis {held_since_s:.0f}s par une autre session.")


class NoStructureDetectedError(Exception):
    """Levée quand aucun marqueur Article/Section/Titre/Chapitre n'est détecté dans le document."""


class FileTooLargeError(Exception):
    """Levée quand le fichier dépasse MAX_FILE_SIZE_BYTES."""


class TooManyPagesError(Exception):
    """Levée quand le document dépasse MAX_PAGES."""


@dataclass
class UploadSessionHandle:
    session_id: str
    client: chromadb.ClientAPI
    collection: chromadb.Collection
    acquired_at: float


# ─────────────────────────────────────────────
# Partie A — Verrou de process
# ─────────────────────────────────────────────
# Verrou au niveau du PROCESS (pas par session Streamlit) : même pattern que
# agent._chroma_lock / agent._daily_lock — un threading.Lock() module-level,
# pas de coordination multi-instance (non pertinent ici : Cloud Run reste à
# 1 instance, voir MAINTENANCE-APPS-TKOIDRA.md).

_upload_lock = threading.Lock()
_active: dict | None = None  # {"session_id", "client", "collection", "acquired_at", "last_activity"}


def _purge_all_ephemeral_collections(client: chromadb.ClientAPI) -> list[str]:
    """
    Supprime TOUTES les collections visibles depuis ce client — pas seulement
    celle au nom attendu. Nécessaire car les EphemeralClient() du même process
    partagent un backend commun (validé sous-lot 2a.0, test_chroma_isolation.py) :
    une session abandonnée peut avoir laissé une collection sous n'importe quel
    nom, invisible si on ne purge que le nom qu'on s'apprête à utiliser.
    """
    names = [c.name for c in client.list_collections()]
    for name in names:
        try:
            client.delete_collection(name)
        except Exception:
            log.warning("PURGE échec delete_collection(%r)", name)
    return names


def _release_locked(reason: str) -> None:
    """Libère `_active`. Doit être appelé avec `_upload_lock` déjà tenu."""
    global _active
    if _active is None:
        return
    try:
        _active["client"].delete_collection(_active["collection"].name)
    except Exception:
        log.warning("RELEASE(%s) échec delete_collection session_id=%s", reason, _active["session_id"])
    log.info("UPLOAD_LOCK release session_id=%s reason=%s", _active["session_id"], reason)
    _active = None
    gc.collect()


def try_acquire(session_id: str) -> UploadSessionHandle:
    """
    Acquiert le verrou de process pour `session_id`.

    Lève UploadSessionBusyError si une autre session le détient encore (pas
    expirée). Purge SYSTÉMATIQUEMENT toutes les collections éphémères
    existantes avant de créer la nouvelle — y compris si aucune session
    n'était "officiellement" active côté `_active` (résidu d'un abandon
    antérieur, ou d'un redémarrage partiel).
    """
    global _active
    with _upload_lock:
        now = time.monotonic()
        if _active is not None:
            elapsed = now - _active["last_activity"]
            if elapsed < UPLOAD_LOCK_TIMEOUT_S:
                raise UploadSessionBusyError(now - _active["acquired_at"])
            log.warning(
                "UPLOAD_LOCK timeout: session_id=%s inactive depuis %.0fs (>%ds) — libération automatique",
                _active["session_id"], elapsed, UPLOAD_LOCK_TIMEOUT_S,
            )
            _release_locked(reason="timeout")

        client = chromadb.EphemeralClient()
        purged = _purge_all_ephemeral_collections(client)
        if purged:
            log.info("UPLOAD_LOCK purge à l'acquisition (session_id=%s) : %s", session_id, purged)

        collection = client.get_or_create_collection(
            name=f"{UPLOAD_COLLECTION_PREFIX}{session_id}",
            metadata={"hnsw:space": "cosine", "model_name": MODEL_NAME},
        )
        _active = {
            "session_id": session_id,
            "client": client,
            "collection": collection,
            "acquired_at": now,
            "last_activity": now,
        }
        log.info("UPLOAD_LOCK acquire session_id=%s", session_id)
        return UploadSessionHandle(session_id, client, collection, now)


def touch(session_id: str) -> None:
    """Heartbeat — à appeler à chaque interaction utilisateur dans la session active."""
    with _upload_lock:
        if _active is not None and _active["session_id"] == session_id:
            _active["last_activity"] = time.monotonic()


def release(session_id: str) -> None:
    """
    Fin de session normale (upload traité, réponse donnée) : delete_collection()
    explicite. Défense en profondeur — s'ajoute à la purge systématique de
    try_acquire(), ne la remplace pas (cf. docstring du module : une session
    abandonnée sans cet appel reste couverte par la purge côté session suivante).
    """
    with _upload_lock:
        if _active is not None and _active["session_id"] == session_id:
            _release_locked(reason="fin_normale")


def check_and_release_if_stale() -> bool:
    """
    Libère le verrou s'il est resté inactif au-delà de UPLOAD_LOCK_TIMEOUT_S,
    sans attendre qu'une nouvelle session tente de l'acquérir.

    En usage normal, le chemin qui compte est la libération paresseuse dans
    try_acquire() (le verrou n'a d'effet qu'au moment où quelqu'un veut
    l'acquérir — un visiteur seul sur la démo n'a jamais besoin d'une
    libération "spontanée"). Cette fonction est exposée séparément pour
    pouvoir tester le mécanisme de timeout indépendamment d'une tentative
    d'acquisition (partie D, test 3).
    """
    with _upload_lock:
        if _active is None:
            return False
        elapsed = time.monotonic() - _active["last_activity"]
        if elapsed >= UPLOAD_LOCK_TIMEOUT_S:
            log.warning("UPLOAD_LOCK timeout (vérification directe) : inactif depuis %.0fs", elapsed)
            _release_locked(reason="timeout_direct")
            return True
        return False


def is_busy() -> bool:
    with _upload_lock:
        return _active is not None


# ─────────────────────────────────────────────
# Partie B — Pipeline d'upload
# ─────────────────────────────────────────────

def validate_pdf_constraints(pdf_path: Path) -> int:
    """Vérifie taille et nombre de pages. Retourne le nombre de pages si OK,
    lève FileTooLargeError / TooManyPagesError sinon."""
    size = pdf_path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"Fichier trop volumineux : {size / 1024 / 1024:.1f} Mo "
            f"(limite {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} Mo)."
        )
    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
    if n_pages > MAX_PAGES:
        raise TooManyPagesError(f"Trop de pages : {n_pages} (limite {MAX_PAGES}).")
    return n_pages


def _chunk_lines_or_reject(lines: list[str], source_doc_id: str) -> list[dict]:
    """
    Cœur testable du découpage (séparé de la lecture PDF pour pouvoir tester
    sans fichier PDF réel — cf. tests/test_upload_session.py).

    Rejet EXPLICITE si aucun marqueur Article/Section/Titre/Chapitre n'est
    détecté dans le document — contrairement au repli actuel de
    extract_chunks.split_into_chunks() pour le corpus fixe, qui produit
    silencieusement un unique chunk "tout le texte" quand aucun marqueur
    n'apparaît (comportement voulu pour le corpus fixe, déjà contrôlé
    manuellement ; pas acceptable pour un document visiteur non vérifié).
    """
    has_marker = any(extract_chunks.ARTICLE_PATTERN.match(line.strip()) for line in lines)
    if not has_marker:
        raise NoStructureDetectedError(
            "Aucune structure d'article détectée dans ce document (marqueurs attendus : "
            "Article, Section, Titre ou Chapitre). Cette démo ne peut analyser que des "
            "documents contractuels structurés par articles — merci d'essayer avec un "
            "autre document."
        )

    meta = {
        "source_doc": source_doc_id,
        "version": "upload",
        "titre_humain": f"Document visiteur ({source_doc_id})",
    }
    chunks = extract_chunks.split_into_chunks(lines, meta)
    if not chunks:
        # Cas résiduel : marqueur(s) présent(s) mais aucun chunk exploitable
        # (ex. articles tous < 150 caractères, filtre de extract_chunks.flush()).
        raise NoStructureDetectedError(
            "Structure d'articles détectée mais aucun contenu exploitable n'en a été extrait "
            "(articles trop courts, ou document dominé par une table des matières)."
        )
    return chunks


def extract_and_chunk_pdf(pdf_path: Path, source_doc_id: str) -> list[dict]:
    """Lecture PDF (pdfplumber, déjà utilisé en lecture ailleurs dans le projet)
    + découpage. Lève NoStructureDetectedError si pas de structure d'articles."""
    lines = extract_chunks.extract_text_from_pdf(pdf_path)
    return _chunk_lines_or_reject(lines, source_doc_id)


def _truncate_chunk_if_needed(chunk: dict, tokenizer) -> tuple[dict, dict | None]:
    text = chunk["text"]
    ids = tokenizer(text, truncation=False)["input_ids"]
    if len(ids) <= MAX_CHUNK_TOKENS:
        return chunk, None

    truncated_ids = tokenizer(text, truncation=True, max_length=MAX_CHUNK_TOKENS)["input_ids"]
    truncated_text = tokenizer.decode(truncated_ids, skip_special_tokens=True)
    warning = {
        "article_num": chunk["metadata"].get("article_num"),
        "tokens_original": len(ids),
        "tokens_conserves": len(truncated_ids),
    }
    log.warning(
        "UPLOAD chunk tronqué : article=%s %d tokens -> %d tokens (limite modèle e5 = %d)",
        warning["article_num"], warning["tokens_original"], warning["tokens_conserves"], MAX_CHUNK_TOKENS,
    )
    new_chunk = {
        "text": truncated_text,
        "metadata": {**chunk["metadata"], "tronque": True, "tokens_original": len(ids)},
    }
    return new_chunk, warning


def apply_length_guard(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Contrôle explicite par chunk avant l'embedding (partie C) : tronque
    proprement à MAX_CHUNK_TOKENS avec avertissement, au lieu de laisser le
    modèle tronquer silencieusement à l'encode() (cf. constante MAX_CHUNK_TOKENS
    ci-dessus pour la justification du choix troncature vs rejet).

    Retourne (chunks_ajustés, avertissements) — avertissements = liste de
    dicts {article_num, tokens_original, tokens_conserves}, destinée à être
    affichée au visiteur (transparence) en plus du log serveur.
    """
    model = get_embed_model()
    tokenizer = model.tokenizer
    adjusted = []
    warnings = []
    for c in chunks:
        new_c, warning = _truncate_chunk_if_needed(c, tokenizer)
        adjusted.append(new_c)
        if warning is not None:
            warnings.append(warning)
    return adjusted, warnings


def embed_and_index(collection: chromadb.Collection, chunks: list[dict]) -> None:
    """Encode et indexe `chunks` dans `collection` (la collection éphémère de
    LA session courante, jamais agent.get_chroma_col()). Réutilise le même
    modèle chargé en mémoire par get_embed_model() (partagé avec le chat
    principal — un seul modèle en RAM pour tout le process, pas de rechargement)."""
    model = get_embed_model()
    texts = ["passage: " + c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    gc.collect()

    ids = [f"upload_{i}_{c['metadata'].get('article_num', '') or 'na'}" for i, c in enumerate(chunks)]
    collection.upsert(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )


def retrieve_from_upload(collection: chromadb.Collection, query: str, k: int = 10) -> list[dict]:
    """
    Interroge UNIQUEMENT la collection éphémère passée en paramètre.

    Ne passe JAMAIS par agent.get_chroma_col() ni agent.retrieve_chunks() —
    ces deux fonctions, non modifiées par ce sous-lot, restent strictement
    réservées à la collection globale persistante interrogée par le graphe
    LangGraph du chat principal (agent.build_graph() / agent.run_agent()).
    """
    model = get_embed_model()
    vec = model.encode(["query: " + query], show_progress_bar=False, normalize_embeddings=True).tolist()[0]
    gc.collect()
    results = collection.query(
        query_embeddings=[vec],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    chunks = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        chunks.append({"text": doc, "metadata": meta, "distance": dist})
    return chunks


def answer_question_on_upload(collection: chromadb.Collection, question: str) -> str:
    """
    Réponse mono-appel LLM sur la collection éphémère de la session — pas le
    graphe LangGraph complet d'agent.py (pas de plan-and-execute ni de
    reformulation HyDE pour ce MVP d'upload, un seul document donc pas besoin
    de routage multi-documents). Réutilise SYSTEM_PROMPT / llm_call /
    format_chunks_for_prompt d'agent.py tels quels, sans les modifier.
    """
    chunks = retrieve_from_upload(collection, question)
    prompt = (
        f"Question de l'utilisateur : {question}\n\n"
        f"Documents pertinents trouvés :\n{format_chunks_for_prompt(chunks)}\n\n"
        "Réponds en respectant strictement le format 3 blocs : "
        "**Réponse directe** / **Source(s)** / **Point d'attention**"
    )
    return llm_call([{"role": "user", "content": prompt}], system=SYSTEM_PROMPT)

"""
Agent RAG agentique — graphe LangGraph.
Étapes : router → (planner) → retrieve → evaluate → (reformulate) → synthesize → log
"""
from __future__ import annotations

import gc
import json
import logging
import os
from pathlib import Path
from typing import TypedDict

import anthropic
import chromadb
import torch
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from sentence_transformers import SentenceTransformer

log = logging.getLogger("agent")

load_dotenv()

ROOT = Path(__file__).parent.parent
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "assur_docs"
MODEL_NAME = "intfloat/multilingual-e5-large"
CLAUDE_MODEL = "claude-sonnet-4-6"
RETRIEVAL_K = 10

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


# ─────────────────────────────────────────────
# Ressources partagées (chargées une fois)
# ─────────────────────────────────────────────

_embed_model: SentenceTransformer | None = None
_chroma_client: chromadb.PersistentClient | None = None  # référence forte pour éviter le GC
_chroma_col: chromadb.Collection | None = None
_anthropic_client: anthropic.Anthropic | None = None


def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        # bfloat16 réduit les poids de ~1.34 Go (float32) à ~670 Mo sur CPU.
        # Sur Apple Silicon MPS, le warm-up encode() est toujours nécessaire pour
        # forcer la compilation Metal et éviter un premier vecteur incorrect.
        _embed_model = SentenceTransformer(MODEL_NAME, model_kwargs={"torch_dtype": torch.bfloat16})
        _ = _embed_model.encode(["query: warm-up"], normalize_embeddings=True)
        gc.collect()
        log.info("EMBED_MODEL loaded (bfloat16) + warm-up done, device=%s", _embed_model.device)
    return _embed_model


def get_chroma_col() -> chromadb.Collection:
    global _chroma_client, _chroma_col
    if _chroma_col is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _chroma_col = _chroma_client.get_collection(COLLECTION_NAME)
        log.info(
            "CHROMA loaded: collection=%r count=%d id=%s",
            _chroma_col.name,
            _chroma_col.count(),
            _chroma_col.id,
        )
    return _chroma_col


def get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _anthropic_client


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

def llm_call(messages: list[dict], system: str = SYSTEM_PROMPT) -> str:
    client = get_anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def llm_json(messages: list[dict], system: str) -> dict:
    """Appel LLM avec sortie JSON stricte. temperature=0 pour la reproductibilité."""
    client = get_anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        temperature=0,
        system=system + "\n\nRéponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans explication.",
        messages=messages,
    )
    text = response.content[0].text.strip()
    # Nettoyer les balises markdown si présentes
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def embed_query(text: str) -> list[float]:
    import math
    model = get_embed_model()
    vec = model.encode(["query: " + text], normalize_embeddings=True).tolist()[0]
    gc.collect()  # libère les tenseurs torch intermédiaires dès que le vecteur est en liste Python
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
    # Embed avec le préfixe "passage:" — le vecteur d'un passage est plus proche des chunks réels
    model = get_embed_model()
    vec = model.encode(["passage: " + passage], normalize_embeddings=True).tolist()[0]
    gc.collect()  # libère les tenseurs torch intermédiaires dès que le vecteur est en liste Python
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
    graph = get_graph()
    initial_state: AgentState = {
        "question_originale": question,
        "produit_filtre": produit_filtre,
        "sous_questions": [],
        "resultats": [],
        "reponse_finale": "",
        "trace_log": [],
    }
    return graph.invoke(initial_state)


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

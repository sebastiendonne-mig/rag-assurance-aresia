"""
Interface Streamlit — RAG agentique assurance ARESIA
Colonne gauche : chat  |  Colonne droite : trace du graphe LangGraph
"""
import json
import logging
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent import get_embed_model, get_chroma_col, get_anthropic, get_graph, run_agent

ROOT = Path(__file__).parent

# Log fichier pour debug — visible même depuis le process Streamlit
LOG_PATH = ROOT / "data" / "streamlit_debug.log"
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,
)
log = logging.getLogger("streamlit_app")


# ─────────────────────────────────────────────
# Config page  (DOIT être le 1er appel Streamlit)
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="AssurConseil 365 — RAG agentique",
    page_icon="🛡️",
    layout="wide",
)


@st.cache_resource(show_spinner="Chargement du modèle d'embeddings…")
def _warm_up():
    """Charge les ressources une seule fois pour toute la durée de vie du serveur."""
    get_embed_model()
    get_chroma_col()
    get_anthropic()
    get_graph()
    return True


_warm_up()

st.markdown("""
<style>
.trace-header { font-size: 0.82rem; font-weight: 600; color: #555; }
.trace-decision-ok   { color: #1a7f37; font-weight: 600; }
.trace-decision-nok  { color: #cf222e; font-weight: 600; }
.trace-decision-warn { color: #9a6700; font-weight: 600; }
.etape-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 0.75rem;
    font-weight: 700;
    color: white;
    margin-right: 6px;
}
.badge-router     { background: #6f42c1; }
.badge-planner    { background: #0d6efd; }
.badge-retrieve   { background: #0ca678; }
.badge-evaluate   { background: #f76707; }
.badge-reformulate{ background: #d63384; }
.badge-synthesize { background: #198754; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_trace" not in st.session_state:
    st.session_state.last_trace = []

with st.sidebar:
    st.header("Conversation")
    if st.button("🗑️ Vider la conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_trace = []
        st.rerun()
    st.caption(f"Messages : {len(st.session_state.messages)}")
    if LOG_PATH.exists():
        with st.expander("📋 Log debug (dernier appel)"):
            lines = LOG_PATH.read_text().strip().split("\n")
            st.code("\n".join(lines[-30:]), language="text")

# ─────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────

col_chat, col_trace = st.columns([3, 2], gap="large")

# ─────────────────────────────────────────────
# Colonne gauche — Chat
# ─────────────────────────────────────────────

_DEMO_QUESTIONS = [
    (
        "Quelle est la franchise ITT sur le contrat prévoyance invalidité ?",
        "Question simple : recherche directe dans les documents.",
    ),
    (
        "Quelle est la garantie obsèques incluse dans le contrat prévoyance ?",
        "Garde-fou anti-hallucination : cette garantie n'existe pas dans les documents — "
        "observez la trace à droite (reformulations puis « non trouvé »).",
    ),
    (
        "Quelle indemnisation pour une invalidité partielle suite à un accident, "
        "avec une rente complémentaire ?",
        "Plan-and-Execute : question décomposée en sous-questions traitées séparément. "
        "Peut prendre 30 à 40 secondes — c'est normal.",
    ),
]

_PDF_SOURCES = [
    ("CG Prévoyance Invalidité (v4.2)",          "CG-prevoyance-invalidite.pdf"),
    ("CG Assurance Vie Multisupport (v3.1)",      "CG-assurance-vie.pdf"),
    ("Barème Garanties IARD 2024 (v2.0)",         "bareme-garanties-iard.pdf"),
    ("Circulaire ACPR devoir de conseil (fictive)", "circulaire-acpr-conseil.pdf"),
]

with col_chat:
    st.title("🛡️ AssurConseil 365")
    st.caption("Agent RAG — Contrats ARESIA Assurances | Plan-and-Execute + ReAct")

    st.markdown(
        "Démonstration d'un agent RAG agentique (recherche augmentée par génération) "
        "sur des contrats d'assurance fictifs, illustrant les patterns **Plan-and-Execute** "
        "et **ReAct** avec traçabilité complète du raisonnement (panneau de droite)."
    )

    st.warning(
        "⚠️ Tous les documents et contrats utilisés dans cette démo sont entièrement "
        "fictifs (société « ARESIA Assurances » imaginaire), créés uniquement à des fins "
        "de démonstration technique. Aucune valeur contractuelle ou réglementaire réelle."
    )

    # ── Documents sources téléchargeables ──
    with st.expander("📄 Documents sources (fictifs) — cliquez pour télécharger"):
        c1, c2 = st.columns(2)
        for i, (label, fname) in enumerate(_PDF_SOURCES):
            fpath = ROOT / fname
            col = c1 if i % 2 == 0 else c2
            with col:
                if fpath.exists():
                    st.download_button(
                        label=label,
                        data=fpath.read_bytes(),
                        file_name=fname,
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"dl_{i}",
                    )
                else:
                    st.caption(f"_(fichier introuvable : {fname})_")
        st.caption(
            "Ces documents constituent la base documentaire complète de l'agent — "
            "toute réponse peut être vérifiée par recoupement avec leur contenu."
        )

    # ── Questions de test cliquables ──
    st.markdown("**🧪 Questions de test suggérées**")
    pending: str | None = None
    for i, (question, legende) in enumerate(_DEMO_QUESTIONS):
        col_btn, col_leg = st.columns([5, 4])
        with col_btn:
            if st.button(question, key=f"demo_q_{i}", use_container_width=True):
                pending = question
        with col_leg:
            st.caption(f"↑ {legende}")

    st.divider()

    # ── Historique de la conversation ──
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Zone de saisie (chat_input + boutons de démo) ──
    chat_prompt = st.chat_input("Posez votre question sur les contrats ARESIA…")
    prompt = pending or chat_prompt

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Recherche en cours…"):
                try:
                    log.info("RUN_AGENT question=%r", prompt[:80])
                    state = run_agent(prompt)
                    reponse = state["reponse_finale"]
                    st.session_state.last_trace = state["trace_log"]
                    trace_summary = [(e["etape"], e.get("decision", "")[:40]) for e in state["trace_log"]]
                    log.info("RUN_AGENT done trace=%s reponse_start=%r", trace_summary, reponse[:80])
                except Exception as e:
                    log.exception("RUN_AGENT exception: %s", e)
                    reponse = f"❌ Erreur : {e}"
                    st.session_state.last_trace = []

            st.markdown(reponse)

        st.session_state.messages.append({"role": "assistant", "content": reponse})
        st.rerun()

# ─────────────────────────────────────────────
# Colonne droite — Trace LangGraph
# ─────────────────────────────────────────────

BADGE = {
    "router":      ("badge-router",      "ROUTER"),
    "planner":     ("badge-planner",     "PLANNER"),
    "retrieve":    ("badge-retrieve",    "RETRIEVE"),
    "evaluate":    ("badge-evaluate",    "EVALUATE"),
    "reformulate": ("badge-reformulate", "REFORMULATE"),
    "synthesize":  ("badge-synthesize",  "SYNTHESIZE"),
}

DECISION_ICONS = {
    "react_simple":     ("✦", "trace-decision-ok"),
    "plan_and_execute": ("⚡", "trace-decision-ok"),
    "suffisant":        ("✅", "trace-decision-ok"),
    "insuffisant":      ("⚠️",  "trace-decision-warn"),
    "non_trouve":       ("❌", "trace-decision-nok"),
    "reponse_generee":  ("✅", "trace-decision-ok"),
}

with col_trace:
    st.subheader("🔍 Traçabilité du raisonnement")

    trace = st.session_state.last_trace

    if not trace:
        st.info("La trace du graphe apparaîtra ici après votre première question.")
    else:
        etapes = [e["etape"] for e in trace]
        nb_reformulations = sum(1 for e in trace if e["etape"] == "reformulate")
        has_planner = any(e["etape"] == "planner" for e in trace)

        cols = st.columns(3)
        cols[0].metric("Étapes", len(trace))
        cols[1].metric("Mode", "Plan+Execute" if has_planner else "ReAct simple")
        cols[2].metric("Reformulations", nb_reformulations)

        st.divider()

        for i, entry in enumerate(trace):
            etape = entry["etape"]
            badge_cls, badge_label = BADGE.get(etape, ("badge-router", etape.upper()))
            decision = entry.get("decision", "")
            raison = entry.get("raison", "")
            chunks_recus = entry.get("chunks_recus", 0)
            action_suivante = entry.get("action_suivante", "")
            sous_q = entry.get("sous_question", "")

            for key, (icon, cls) in DECISION_ICONS.items():
                if key in decision.lower():
                    decision_display = f'<span class="{cls}">{icon} {decision}</span>'
                    break
            else:
                decision_display = f'<span class="trace-decision-warn">◆ {decision}</span>'

            label = f"{'⚡ ' if etape == 'planner' else ''}{badge_label} — {decision[:50]}"
            with st.expander(label, expanded=(i == 0)):
                st.markdown(
                    f'<span class="etape-badge {badge_cls}">{badge_label}</span>'
                    f'<span class="trace-header">Étape {i+1}/{len(trace)}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Décision :** {decision_display}", unsafe_allow_html=True)

                if sous_q and etape != "router":
                    st.markdown(f"**Sous-question :** _{sous_q[:120]}_")

                if chunks_recus:
                    st.markdown(f"**Chunks reçus :** {chunks_recus}")

                if raison:
                    st.markdown(f"**Raison :** {raison[:300]}")

                if action_suivante:
                    st.markdown(f"**→ Action suivante :** `{action_suivante}`")

        with st.expander("📋 JSON brut du trace_log"):
            st.code(json.dumps(trace, ensure_ascii=False, indent=2), language="json")

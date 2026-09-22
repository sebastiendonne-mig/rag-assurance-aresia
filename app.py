"""
Interface Streamlit — RAG agentique assurance ARESIA
Colonne gauche : chat  |  Colonne droite : trace du graphe LangGraph
"""
import base64
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent import (
    CLAUDE_MODEL,
    PRIX_INPUT_USD_PAR_MTOK,
    PRIX_OUTPUT_USD_PAR_MTOK,
    configure_stdout_logging,
    exceeds_max_length,
    format_user_error,
    get_embed_model,
    get_chroma_col,
    get_anthropic,
    get_graph,
    run_agent,
)
import upload_session

MAX_INPUT_CHARS = int(os.environ.get("MAX_INPUT_CHARS", "500"))

# Texte de consentement (lot 2a.1 sous-lot suivant) — brouillon fourni tel quel,
# PAS encore validé pour affichage définitif en prod (voir rapport du sous-lot).
UPLOAD_CONSENT_TEXT = (
    "Ce document sera envoyé à Claude (API Anthropic) pour générer une réponse. Anthropic "
    "conserve automatiquement les données envoyées jusqu'à 30 jours (délai de suppression par "
    "défaut, aucune option de conservation zéro sur ce type de compte). Cette démo ne stocke "
    "rien de façon permanente de son côté : l'index créé pour analyser votre document est "
    "supprimé automatiquement à la fin de la session ou après quelques minutes d'inactivité.\n\n"
    "Merci d'utiliser un document fictif, ou dont vous acceptez le partage dans ces conditions."
)

ROOT = Path(__file__).parent

# Log fichier pour debug — visible même depuis le process Streamlit.
# Guard : logging.root.handlers est non vide après le premier configure ; on évite
# ainsi de créer un nouveau FileHandler à chaque rerun Streamlit (fuite de handles).
LOG_PATH = ROOT / "data" / "streamlit_debug.log"
if not logging.root.handlers:
    from logging.handlers import RotatingFileHandler
    _handler = RotatingFileHandler(
        str(LOG_PATH),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=1,
        encoding="utf-8",
    )
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.root.addHandler(_handler)
    logging.root.setLevel(logging.INFO)
log = logging.getLogger("streamlit_app")

# WARNING et au-dessus en plus sur stdout (Cloud Logging capture stdout/stderr
# du conteneur, jamais un fichier local) — voir agent.configure_stdout_logging.
configure_stdout_logging()


# ─────────────────────────────────────────────
# Config page  (DOIT être le 1er appel Streamlit)
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="AssurConseil 365 · TKoidra",
    page_icon="🛡️",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def _load_pdf_bytes(path: str) -> bytes:
    """Lit un PDF une seule fois et met en cache les bytes pour toute la session."""
    return Path(path).read_bytes()


@st.cache_data(show_spinner=False)
def _load_svg_b64(filename: str) -> str:
    """Encode un SVG du brand-kit en base64 pour l'injecter en data URI (pas de serveur statique requis)."""
    return base64.b64encode((ROOT / "assets" / filename).read_bytes()).decode()


def _format_usage_caption(usage: dict) -> str:
    """Formate la ligne de synthèse usage/coût affichée sous une réponse."""
    return (
        f"⏱️ {usage['latence_s']:.1f}s · {usage['n_appels']} appel(s) LLM · "
        f"{usage['tokens_in']}+{usage['tokens_out']} tokens (entrée+sortie) · "
        f"≈{usage['cout_usd']:.4f}\\$ *(estimation)*"
    )


@st.cache_resource(show_spinner="Chargement du modèle d'embeddings… (jusqu'à 90 secondes au premier chargement)")
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
.stApp, .stApp [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif; }

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

/* ── Header / footer TKoidra (brand-kit) ── */
.tk-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 0 1rem 0;
    border-bottom: 1px solid #E2E8F0;
    margin-bottom: 1.5rem;
}
.tk-header img { display: block; }
.tk-back-link {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 0.875rem;
    font-weight: 500;
    color: #475569;
    text-decoration: none;
    transition: color 0.15s;
}
.tk-back-link:hover { color: #0D1F40; }

.tk-footer {
    background: #0D1F40;
    margin-top: 2.5rem;
    padding: 1.5rem;
    border-radius: 12px;
}
.tk-footer-inner {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    text-align: center;
}
.tk-footer-nav { display: flex; gap: 1.5rem; }
.tk-footer-nav a {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 0.8125rem;
    font-weight: 500;
    color: #00B4D8;
    text-decoration: none;
    transition: color 0.15s;
}
.tk-footer-nav a:hover { color: #38C4E0; }
.tk-footer-copy {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.4);
    margin: 0;
}
</style>
""", unsafe_allow_html=True)

_logo_navy = _load_svg_b64("logo-horizontal.svg")
st.markdown(f"""
<div class="tk-header">
  <a href="https://tkoidra.com" target="_blank" rel="noopener noreferrer">
    <img src="data:image/svg+xml;base64,{_logo_navy}" height="32" alt="TKoidra">
  </a>
  <a href="https://tkoidra.com" target="_blank" rel="noopener noreferrer" class="tk-back-link">← Portfolio</a>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_trace" not in st.session_state:
    st.session_state.last_trace = []
if "last_usage" not in st.session_state:
    st.session_state.last_usage = None

# ── Session d'upload de document visiteur (lot 2a.1 suite) ──
if "upload_consent" not in st.session_state:
    st.session_state.upload_consent = False
if "upload_active" not in st.session_state:
    st.session_state.upload_active = False
if "upload_collection" not in st.session_state:
    st.session_state.upload_collection = None
if "upload_doc_name" not in st.session_state:
    st.session_state.upload_doc_name = None
if "upload_warnings" not in st.session_state:
    st.session_state.upload_warnings = []
if "upload_last_processed_file_id" not in st.session_state:
    st.session_state.upload_last_processed_file_id = None

_upload_session_id = upload_session.get_or_create_session_id()

with st.sidebar:
    st.header("Conversation")
    if st.button("🗑️ Vider la conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_trace = []
        st.session_state.last_usage = None
        st.rerun()
    st.caption(f"Messages : {len(st.session_state.messages)}")

# ─────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────

col_chat, col_trace = st.columns([3, 2], gap="large")

# ─────────────────────────────────────────────
# Colonne gauche — Chat
# ─────────────────────────────────────────────

_DEMO_QUESTIONS = [
    (
        "Quelles sont les options de franchise disponibles sur le contrat prévoyance invalidité ?",
        "Question simple : recherche directe dans les documents.",
    ),
    (
        "Quel est le montant minimum pour un versement complémentaire sur ARESIA Patrimoine+ ?",
        "Autre document : contrat d'assurance vie.",
    ),
    (
        "Dans quel délai doit-on déclarer un cambriolage à son assureur ?",
        "Autre document : garanties IARD (habitation).",
    ),
    (
        "Combien d'heures de formation continue un conseiller doit-il suivre par an au titre de la DDA ?",
        "Autre document : conformité réglementaire (ACPR).",
    ),
    (
        "Quelle est la garantie obsèques incluse dans le contrat prévoyance ?",
        "Garde-fou anti-hallucination : cette garantie n'existe pas dans les documents — "
        "observez la trace à droite (reformulations puis « non trouvé »).",
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
                        data=_load_pdf_bytes(str(fpath)),
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

    # ── Choix et limites ──
    with st.expander("ℹ️ Choix et limites de cette démo"):
        st.markdown(
            "**Ce que fait cette démo**\n"
            "Cette démo interroge un corpus de 4 documents fictifs (prévoyance invalidité, "
            "assurance vie, garanties IARD, conformité réglementaire — explicitement fictifs, "
            "créés pour cette démonstration) via un pipeline RAG piloté par LangGraph."
        )
        st.markdown(
            "**Modèle utilisé aujourd'hui**\n"
            f"`{CLAUDE_MODEL}`. Toutes les décisions du pipeline (routage, évaluation, "
            "génération) passent par deux points d'entrée uniques dans le code — c'est "
            "cette couture qui rend un changement de modèle possible sans réécrire le pipeline."
        )
        st.markdown(
            "**Portabilité : conçue, pas testée**\n"
            "Le message central de cette démo est la portabilité — la même architecture "
            "pourrait fonctionner avec un autre modèle, propriétaire ou open source. C'est "
            "vérifiable dans le code, mais non testé avec un autre fournisseur à ce jour : "
            "les prompts et le format JSON attendu pourraient demander des ajustements."
        )
        st.markdown(
            "**Garde-fous actifs**\n"
            "- Question limitée à 500 caractères\n"
            "- Plafond quotidien de questions\n"
            "- Une réponse au format invalide échoue proprement plutôt que de planter"
        )
        st.markdown(
            "**Ce qu'un test de 20 questions mesure — et ne mesure pas**\n"
            "Il vérifie que l'article de référence attendu est bien cité. Il ne mesure ni "
            "la qualité rédactionnelle ni l'exactitude complète des réponses — seulement "
            "la présence de la bonne citation."
        )

    # ── Session d'upload de document visiteur (lot 2a.1 suite) ──
    with st.expander("📎 Tester avec votre propre document (PDF)", expanded=st.session_state.upload_active):
        if st.session_state.upload_active:
            st.success(f"📄 Mode document uploadé actif : **{st.session_state.upload_doc_name}**")
            st.caption(
                "Les questions posées ci-dessous portent uniquement sur ce document — "
                "le corpus ARESIA habituel n'est pas interrogé tant que ce mode est actif."
            )
            for w in st.session_state.upload_warnings:
                st.caption(
                    f"⚠️ Article {w['article_num']} tronqué : {w['tokens_original']} → "
                    f"{w['tokens_conserves']} tokens conservés (limite du modèle d'embeddings)."
                )
            if st.button("📄 Nouveau document", use_container_width=True):
                upload_session.release(_upload_session_id)
                st.session_state.upload_active = False
                st.session_state.upload_collection = None
                st.session_state.upload_doc_name = None
                st.session_state.upload_warnings = []
                st.session_state.upload_last_processed_file_id = None
                st.rerun()
        elif not st.session_state.upload_consent:
            st.markdown(UPLOAD_CONSENT_TEXT)
            if st.button("J'ai compris, je continue", key="upload_consent_btn"):
                st.session_state.upload_consent = True
                st.rerun()
        elif upload_session.is_busy():
            st.warning(upload_session.UPLOAD_BUSY_MESSAGE)
        else:
            uploaded = st.file_uploader(
                "Document PDF à analyser (contrat structuré par articles)",
                type=["pdf"],
                key="upload_pdf_uploader",
            )
            if uploaded is not None and uploaded.file_id != st.session_state.upload_last_processed_file_id:
                st.session_state.upload_last_processed_file_id = uploaded.file_id
                try:
                    handle = upload_session.try_acquire(_upload_session_id)
                except upload_session.UploadSessionBusyError:
                    # Défense en profondeur : la vérification is_busy() ci-dessus laisse une
                    # fenêtre de course entre deux sessions ; try_acquire() reste la source
                    # de vérité (verrou réel), voir sa docstring dans upload_session.py.
                    st.warning(upload_session.UPLOAD_BUSY_MESSAGE)
                else:
                    with st.spinner("Analyse du document…"):
                        tmp_path = Path(tempfile.gettempdir()) / f"upload_{_upload_session_id}.pdf"
                        try:
                            tmp_path.write_bytes(uploaded.getvalue())
                            upload_session.validate_pdf_constraints(tmp_path)
                            chunks = upload_session.extract_and_chunk_pdf(
                                tmp_path, source_doc_id=f"UPLOAD-{_upload_session_id[:8]}"
                            )
                            chunks, warnings = upload_session.apply_length_guard(chunks)
                            upload_session.embed_and_index(handle.collection, chunks)
                        except (upload_session.FileTooLargeError, upload_session.NoStructureDetectedError) as exc:
                            upload_session.release(_upload_session_id)
                            st.error(str(exc))
                        except Exception as exc:
                            # Erreur inattendue (ex. PDF corrompu) : message neutre au visiteur,
                            # même logique que format_user_error() pour le chat principal —
                            # jamais str(exc) affiché (voir agent.format_user_error).
                            upload_session.release(_upload_session_id)
                            log.error(
                                "UPLOAD_PIPELINE exception type=%s horodatage=%s",
                                type(exc).__name__,
                                datetime.now(timezone.utc).isoformat(),
                            )
                            st.error("Une erreur technique est survenue pendant l'analyse du document. Merci de réessayer.")
                        else:
                            st.session_state.upload_active = True
                            st.session_state.upload_collection = handle.collection
                            st.session_state.upload_doc_name = uploaded.name
                            st.session_state.upload_warnings = warnings
                            st.rerun()
                        finally:
                            tmp_path.unlink(missing_ok=True)

    # ── Questions de test cliquables (masquées en mode document uploadé) ──
    pending: str | None = None
    if not st.session_state.upload_active:
        st.markdown("**🧪 Questions de test suggérées**")
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
            if msg.get("mode") == "upload":
                st.caption(f"📄 Réponse basée sur le document uploadé : {msg.get('doc_name', '')}")
            st.markdown(msg["content"])
            if "usage" in msg:
                st.caption(_format_usage_caption(msg["usage"]))

    # ── Zone de saisie (chat_input + boutons de démo) ──
    chat_prompt = st.chat_input(
        "Posez votre question sur le document uploadé…"
        if st.session_state.upload_active
        else "Posez votre question sur les contrats ARESIA…",
        max_chars=MAX_INPUT_CHARS,
        # Clé explicite et stable : sans elle, Streamlit dérive la clé du widget de
        # son placeholder (qui varie avec le mode) — changer de mode entre deux
        # reruns romprait alors l'identité du widget (valeur perdue en cours de
        # saisie au moment précis où le mode bascule).
        key="main_chat_input",
    )
    prompt = pending or chat_prompt

    if prompt:
        # Garde-fou de longueur : conservé même si le widget limite déjà la saisie
        # clavier (chat_prompt), car `pending` (boutons de démo) contourne le widget.
        if exceeds_max_length(prompt, MAX_INPUT_CHARS):
            st.error(f"Votre question dépasse la limite de {MAX_INPUT_CHARS} caractères. Merci de la raccourcir.")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        upload_mode = st.session_state.upload_active
        with st.chat_message("assistant"):
            with st.spinner("Recherche en cours…"):
                try:
                    if upload_mode:
                        # Chemin dédié (Partie C) : mono-appel LLM sur la collection éphémère
                        # de la session, SANS passer par run_agent()/le graphe LangGraph (pas
                        # de planner, pas de HyDE) et SANS jamais interroger get_chroma_col()
                        # (la collection globale) — voir upload_session.answer_question_on_upload
                        # et le rapport du sous-lot pour la justification de ce chemin séparé.
                        upload_session.touch(_upload_session_id)
                        log.info("RUN_UPLOAD question=%r doc=%r", prompt[:80], st.session_state.upload_doc_name)
                        reponse = upload_session.answer_question_on_upload(
                            st.session_state.upload_collection, prompt
                        )
                        st.session_state.last_trace = []
                        # Pas de suivi d'usage/coût dans ce chemin : answer_question_on_upload()
                        # appelle llm_call() hors du ContextVar positionné par run_agent(), donc
                        # aucun UsageTracker actif — pas de caption coût affichée pour ces
                        # réponses (limite connue, voir rapport).
                        st.session_state.last_usage = None
                    else:
                        log.info("RUN_AGENT question=%r", prompt[:80])
                        state = run_agent(prompt)
                        reponse = state["reponse_finale"]
                        st.session_state.last_trace = state["trace_log"]
                        st.session_state.last_usage = state.get("usage")
                        trace_summary = [(e["etape"], e.get("decision", "")[:40]) for e in state["trace_log"]]
                        log.info("RUN_AGENT done trace=%s reponse_start=%r", trace_summary, reponse[:80])
                except Exception as e:
                    # Log serveur minimal : type, status_code éventuel (ex. 401/429 d'un
                    # anthropic.APIStatusError), TYPE de la cause éventuelle (__cause__,
                    # jamais son message), et horodatage. Jamais le message brut de e.
                    status_code = getattr(e, "status_code", None)
                    cause_type = type(e.__cause__).__name__ if e.__cause__ is not None else None
                    log.error(
                        "%s exception type=%s status_code=%s cause_type=%s horodatage=%s",
                        "RUN_UPLOAD" if upload_mode else "RUN_AGENT",
                        type(e).__name__,
                        status_code,
                        cause_type,
                        datetime.now(timezone.utc).isoformat(),
                    )
                    reponse = format_user_error(e)
                    st.session_state.last_trace = []
                    st.session_state.last_usage = None  # aucun affichage d'usage sur erreur

            st.markdown(reponse)

        # La clé "usage" est réservée à l'affichage (caption sous la réponse,
        # via la boucle d'historique) ; ne jamais envoyer
        # st.session_state.messages tel quel à l'API Anthropic (le SDK
        # n'écarte pas les clés inconnues, vérifié dans la source installée).
        assistant_msg = {"role": "assistant", "content": reponse}
        if upload_mode:
            assistant_msg["mode"] = "upload"
            assistant_msg["doc_name"] = st.session_state.upload_doc_name
        if st.session_state.last_usage is not None:
            assistant_msg["usage"] = st.session_state.last_usage
        st.session_state.messages.append(assistant_msg)
        st.session_state.messages = st.session_state.messages[-40:]
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

    if st.session_state.upload_active:
        st.info(
            "📄 Mode document uploadé : la réponse est générée par un unique appel LLM sur "
            "la collection éphémère de ce document (pas de planner, pas de reformulation — "
            "inutile sur un document unique). Ce chemin ne passe pas par le graphe LangGraph "
            "du corpus principal, donc aucune trace à afficher ici pour ce mode."
        )
    elif not trace:
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

        usage = st.session_state.last_usage
        if usage is not None:
            with st.expander("💰 Détail de l'estimation"):
                st.markdown(f"**Modèle :** `{CLAUDE_MODEL}`")
                st.markdown(
                    f"**Tarif utilisé :** {PRIX_INPUT_USD_PAR_MTOK:.0f}\\$/MTok en entrée, "
                    f"{PRIX_OUTPUT_USD_PAR_MTOK:.0f}\\$/MTok en sortie "
                    "(source : [claude.com/pricing](https://claude.com/pricing), relevé le 21/09/2026 — "
                    "non garanti, susceptible de changer sans préavis)."
                )
                st.caption(
                    "Les tentatives automatiques du SDK en cas d'erreur réseau ne sont pas "
                    "visibles dans ce comptage : en cas de retry, cette estimation est donc "
                    "un plancher (le nombre réel d'appels/tokens peut être supérieur)."
                )

        with st.expander("📋 JSON brut du trace_log"):
            st.code(json.dumps(trace, ensure_ascii=False, indent=2), language="json")

# ─────────────────────────────────────────────
# Footer TKoidra
# ─────────────────────────────────────────────

_logo_white = _load_svg_b64("logo-horizontal-white.svg")
st.markdown(f"""
<div class="tk-footer">
  <div class="tk-footer-inner">
    <img src="data:image/svg+xml;base64,{_logo_white}" height="24" alt="TKoidra">
    <nav class="tk-footer-nav">
      <a href="https://tkoidra.com" target="_blank" rel="noopener noreferrer">Portfolio</a>
      <a href="https://www.linkedin.com/in/sebastiendonne/" target="_blank" rel="noopener noreferrer">LinkedIn ↗</a>
      <a href="https://tkoidra.com/fr/legal" target="_blank" rel="noopener noreferrer">Mentions légales</a>
    </nav>
    <p class="tk-footer-copy">© 2026 TKoidra · Documents fictifs · Démonstration technique · Corpus ARESIA Assurances</p>
  </div>
</div>
""", unsafe_allow_html=True)

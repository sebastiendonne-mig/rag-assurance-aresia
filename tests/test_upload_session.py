"""
Tests locaux du sous-lot 2a.1 — session d'upload éphémère de contrat visiteur.

Aucun appel réseau, aucune clé API : llm_call est monkeypatché (jamais de vrai
appel Anthropic, même dans le test de bout en bout). L'embedding, lui, est réel
(modèle intfloat/multilingual-e5-large, déjà en cache HF local) — c'est le
comportement exact de chromadb (EphemeralClient/PersistentClient) et du
tokenizer du modèle qui sont sous test ici, pas des doublures.

chroma_db/ (la vraie collection globale du dépôt) n'est jamais touché par ces
tests : agent.get_chroma_col() n'est appelé nulle part, ni directement ni par
upload_session (vérifié par grep, voir rapport du sous-lot).
"""
import sys
import threading
import time
from pathlib import Path

import pdfplumber
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent
import upload_session

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _reset_upload_lock_state():
    """Isole chaque test : force le module dans un état neutre avant et après."""
    upload_session._active = None
    yield
    # Best-effort : si un test a laissé un verrou actif (échec en cours de
    # route), on le libère pour ne pas polluer le test suivant.
    if upload_session._active is not None:
        try:
            upload_session._active["client"].delete_collection(
                upload_session._active["collection"].name
            )
        except Exception:
            pass
        upload_session._active = None


def _md5(path: Path) -> str:
    import hashlib
    return hashlib.md5(path.read_bytes()).hexdigest()


# ─────────────────────────────────────────────
# Test 1 — Verrou : deux sessions concurrentes
# ─────────────────────────────────────────────

def test_1_verrou_deux_sessions_concurrentes_une_seule_gagne():
    results = {}
    barrier = threading.Barrier(2)

    def worker(session_id):
        barrier.wait()  # départ synchronisé pour maximiser la collision
        try:
            handle = upload_session.try_acquire(session_id)
            results[session_id] = ("acquired", handle)
        except upload_session.UploadSessionBusyError as exc:
            results[session_id] = ("busy", str(exc))

    t1 = threading.Thread(target=worker, args=("session_A",))
    t2 = threading.Thread(target=worker, args=("session_B",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    outcomes = [results["session_A"][0], results["session_B"][0]]
    n_acquired = outcomes.count("acquired")
    n_busy = outcomes.count("busy")

    assert n_acquired == 1, f"attendu 1 seule acquisition, obtenu {n_acquired} — outcomes={outcomes}"
    assert n_busy == 1, f"attendu 1 seul refus, obtenu {n_busy} — outcomes={outcomes}"

    # Le message d'attente prévu (UX, partie A) doit être récupérable par
    # l'appelant côté session refusée.
    busy_session = "session_A" if results["session_A"][0] == "busy" else "session_B"
    assert "Verrou d'upload détenu depuis" in results[busy_session][1]
    assert upload_session.UPLOAD_BUSY_MESSAGE  # le texte proposé existe et est non vide

    # Nettoyage
    winner = "session_A" if results["session_A"][0] == "acquired" else "session_B"
    upload_session.release(winner)


# ─────────────────────────────────────────────
# Test 2 — Purge à l'acquisition
# ─────────────────────────────────────────────

def test_2_purge_a_lacquisition_supprime_le_residu_abandonne():
    import chromadb

    # Simule une session "abandonnée" du sous-lot 2a.0 : un EphemeralClient
    # indépendant, jamais passé par upload_session, jamais delete_collection()é.
    abandoned_client = chromadb.EphemeralClient()
    abandoned_col = abandoned_client.get_or_create_collection("upload_session_ABANDONED")
    abandoned_col.upsert(
        ids=["r1"],
        embeddings=[[0.1] * 8],
        documents=["RESIDU_SESSION_ABANDONNEE"],
        metadatas=[{"source_doc": "RESIDU"}],
    )
    del abandoned_client
    del abandoned_col
    import gc
    gc.collect()

    # Nouvelle session : try_acquire() doit purger le résidu avant de créer sa
    # propre collection.
    handle = upload_session.try_acquire("session_purge_test")

    names = [c.name for c in handle.client.list_collections()]
    assert "upload_session_ABANDONED" not in names, f"résidu toujours visible : {names}"
    assert names == [f"upload_session_session_purge_test"], f"état inattendu après purge+création : {names}"

    with pytest.raises(Exception):
        handle.client.get_collection("upload_session_ABANDONED")

    upload_session.release("session_purge_test")


# ─────────────────────────────────────────────
# Test 3 — Timeout d'inactivité
# ─────────────────────────────────────────────

def test_3_timeout_liberation_automatique(monkeypatch):
    monkeypatch.setattr(upload_session, "UPLOAD_LOCK_TIMEOUT_S", 0.2)

    handle = upload_session.try_acquire("session_timeout_test")
    assert upload_session.is_busy() is True

    # Avant expiration : le verrou tient toujours, une autre session est refusée.
    with pytest.raises(upload_session.UploadSessionBusyError):
        upload_session.try_acquire("session_intruse")

    time.sleep(0.3)  # dépasse le timeout de test (0.2s)

    # 3a — vérification directe (check_and_release_if_stale), sans tentative d'acquisition
    handle2 = upload_session.try_acquire("session_timeout_test_bis")
    # try_acquire() lui-même libère paresseusement le verrou expiré : on
    # revérifie le mécanisme "direct" séparément, sur un nouveau cycle.
    upload_session.release("session_timeout_test_bis")

    handle3 = upload_session.try_acquire("session_timeout_test_ter")
    upload_session.touch("session_timeout_test_ter")
    time.sleep(0.3)
    released = upload_session.check_and_release_if_stale()
    assert released is True
    assert upload_session.is_busy() is False

    # Après libération automatique, une nouvelle session peut acquérir sans erreur.
    handle4 = upload_session.try_acquire("session_apres_timeout")
    assert handle4.session_id == "session_apres_timeout"
    upload_session.release("session_apres_timeout")


# ─────────────────────────────────────────────
# Test 4 — Upload réel de bout en bout
# ─────────────────────────────────────────────

def test_4_upload_bout_en_bout_ne_touche_pas_la_collection_globale(monkeypatch):
    real_chroma_db = ROOT / "chroma_db" / "chroma.sqlite3"
    md5_avant = _md5(real_chroma_db)

    # Sentinel : si retrieve_from_upload() ou embed_and_index() appelaient par
    # erreur agent.get_chroma_col(), ce sentinel le détecterait immédiatement.
    def _fail_if_called(*a, **k):
        raise AssertionError("agent.get_chroma_col() a été appelé pendant le pipeline d'upload — fuite de routage")

    monkeypatch.setattr(agent, "get_chroma_col", _fail_if_called)

    # Réutilise un PDF fictif existant du corpus comme fixture "document visiteur".
    pdf_path = ROOT / "CG-prevoyance-invalidite.pdf"
    assert pdf_path.exists()

    handle = upload_session.try_acquire("session_e2e_test")

    upload_session.validate_pdf_constraints(pdf_path)  # ne lève pas : fichier sous 15 Mo

    chunks = upload_session.extract_and_chunk_pdf(pdf_path, source_doc_id="UPLOAD-TEST")
    assert len(chunks) > 0

    chunks, warnings = upload_session.apply_length_guard(chunks)
    assert isinstance(warnings, list)

    upload_session.embed_and_index(handle.collection, chunks)
    assert handle.collection.count() == len(chunks)

    fake_answer = "**Réponse directe** : test.\n**Source(s)** : [Article 4 — test]\n**Point d'attention** : aucun."
    captured_prompt = {}

    def _fake_llm_call(messages, system=None):
        captured_prompt["messages"] = messages
        captured_prompt["system"] = system
        return fake_answer

    monkeypatch.setattr(upload_session, "llm_call", _fake_llm_call)

    reponse = upload_session.answer_question_on_upload(
        handle.collection, "Quelles sont les options de franchise ?"
    )
    assert reponse == fake_answer
    assert "messages" in captured_prompt  # le prompt a bien été construit et envoyé au "LLM"

    upload_session.release("session_e2e_test")

    md5_apres = _md5(real_chroma_db)
    assert md5_avant == md5_apres, "la collection globale chroma_db/ a été modifiée pendant l'upload"


# ─────────────────────────────────────────────
# Test 5 — Garde-fou de longueur (512 tokens)
# ─────────────────────────────────────────────

def test_5_garde_fou_longueur_tronque_avec_avertissement():
    long_chunk = {
        "text": "mot " * 2000,  # bien au-delà de 512 tokens
        "metadata": {"source_doc": "UPLOAD-TEST", "article_num": "99", "version": "upload", "titre_humain": "t"},
    }
    short_chunk = {
        "text": "Ceci est un article court, largement sous la limite de tokens.",
        "metadata": {"source_doc": "UPLOAD-TEST", "article_num": "1", "version": "upload", "titre_humain": "t"},
    }

    adjusted, warnings = upload_session.apply_length_guard([long_chunk, short_chunk])

    assert len(adjusted) == 2
    assert len(warnings) == 1
    assert warnings[0]["article_num"] == "99"
    assert warnings[0]["tokens_original"] > upload_session.MAX_CHUNK_TOKENS
    assert warnings[0]["tokens_conserves"] <= upload_session.MAX_CHUNK_TOKENS

    # Le chunk tronqué reste non vide et strictement plus court que l'original.
    truncated_text = adjusted[0]["text"]
    assert 0 < len(truncated_text) < len(long_chunk["text"])
    assert adjusted[0]["metadata"]["tronque"] is True

    # Le chunk court n'est pas altéré.
    assert adjusted[1]["text"] == short_chunk["text"]
    assert "tronque" not in adjusted[1]["metadata"]

    # Vérification indépendante avec le vrai tokenizer : le texte tronqué
    # rentre bien sous la limite une fois ré-encodé.
    model = agent.get_embed_model()
    ids_after = model.tokenizer(truncated_text, truncation=False)["input_ids"]
    assert len(ids_after) <= upload_session.MAX_CHUNK_TOKENS


# ─────────────────────────────────────────────
# Test 6 — Rejet de structure
# ─────────────────────────────────────────────

def test_6_rejet_document_sans_structure_articles():
    lines_sans_structure = [
        "Ceci est un document libre, sans aucune numérotation d'article.",
        "Il contient plusieurs paragraphes de texte ordinaire.",
        "Aucun marqueur Article, Section, Titre ou Chapitre n'apparaît nulle part.",
        "Ce document devrait donc être rejeté explicitement par le pipeline d'upload.",
    ] * 5  # assez de texte pour dépasser le seuil de 150 caractères par "chunk" s'il y en avait un

    with pytest.raises(upload_session.NoStructureDetectedError) as exc_info:
        upload_session._chunk_lines_or_reject(lines_sans_structure, "UPLOAD-SANS-STRUCTURE")

    assert "Aucune structure d'article détectée" in str(exc_info.value)


def test_6b_document_avec_structure_nest_pas_rejete():
    lines_avec_structure = [
        "Article 1 — Objet du contrat",
        "Texte de l'article 1, suffisamment long pour dépasser le seuil minimal de cent "
        "cinquante caractères imposé par le filtre existant de extract_chunks.split_into_chunks.",
    ]
    chunks = upload_session._chunk_lines_or_reject(lines_avec_structure, "UPLOAD-AVEC-STRUCTURE")
    assert len(chunks) == 1
    assert chunks[0]["metadata"]["article_num"] == "1"


# ─────────────────────────────────────────────
# Test 7 — Plafond de taille (15 Mo), et absence de plafond de pages
# (ajout sous-lot 2a.1 suite : 10 Mo -> 15 Mo, plafond de pages supprimé)
# ─────────────────────────────────────────────

def test_7a_fichier_16mo_rejete(tmp_path):
    # validate_pdf_constraints() ne vérifie plus que la taille (st_size) — le
    # contenu n'a pas besoin d'être un PDF valide pour ce test.
    big_file = tmp_path / "faux_contrat_16mo.pdf"
    big_file.write_bytes(b"0" * (16 * 1024 * 1024))

    with pytest.raises(upload_session.FileTooLargeError) as exc_info:
        upload_session.validate_pdf_constraints(big_file)
    assert "16.0 Mo" in str(exc_info.value)
    assert "15 Mo" in str(exc_info.value)


def test_7b_fichier_15mo_accepte(tmp_path):
    exact_file = tmp_path / "faux_contrat_15mo.pdf"
    exact_file.write_bytes(b"0" * upload_session.MAX_FILE_SIZE_BYTES)  # exactement à la limite

    upload_session.validate_pdf_constraints(exact_file)  # ne doit pas lever


def test_7c_document_beaucoup_de_pages_sous_15mo_non_rejete_pour_ce_motif(tmp_path):
    # Construit un vrai PDF à grand nombre de pages (300, en dupliquant les
    # pages d'un document du corpus via pypdf, déjà dans requirements.txt)
    # mais très léger en octets — pour prouver qu'aucun plafond de pages ne
    # s'applique plus, seul le poids compte désormais.
    from pypdf import PdfReader, PdfWriter

    source = ROOT / "CG-prevoyance-invalidite.pdf"
    reader = PdfReader(source)
    writer = PdfWriter()
    n_pages_cible = 300
    for i in range(n_pages_cible):
        writer.add_page(reader.pages[i % len(reader.pages)])

    many_pages_pdf = tmp_path / "contrat_300_pages.pdf"
    with open(many_pages_pdf, "wb") as f:
        writer.write(f)

    size = many_pages_pdf.stat().st_size
    assert size < upload_session.MAX_FILE_SIZE_BYTES, (
        f"le PDF de test fait {size / 1024 / 1024:.2f} Mo — ajuster n_pages_cible pour rester "
        "sous 15 Mo, sinon le test ne prouve plus ce qu'il doit prouver"
    )

    with pdfplumber.open(many_pages_pdf) as pdf:
        assert len(pdf.pages) == n_pages_cible  # confirme que c'est bien un document à 300 pages

    upload_session.validate_pdf_constraints(many_pages_pdf)  # ne doit PAS lever pour le nombre de pages


def test_7d_aucun_plafond_de_pages_ne_subsiste_dans_le_module():
    # Vérification directe (pas seulement comportementale) : la classe
    # d'exception et la constante de plafond de pages n'existent plus du tout.
    assert not hasattr(upload_session, "TooManyPagesError")
    assert not hasattr(upload_session, "MAX_PAGES")

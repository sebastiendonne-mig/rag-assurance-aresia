"""
Tests unitaires de la garde d'indexation (build_index, src/index_chroma.py).
Aucun réseau, aucun modèle réel — build_index() ne calcule plus d'embeddings,
il lit des fichiers embeddings.npy/embeddings.meta.json pré-générés (ici :
fabriqués par les tests eux-mêmes, jamais un vrai calcul). Aucun appel API
Anthropic. CHUNKS_PATH/EMBEDDINGS_PATH/META_PATH/CHROMA_PATH sont toujours
redirigés vers tmp_path — jamais le dossier réel du dépôt (force_reset=True
supprime la collection).
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import index_chroma

DIM = 8  # dimension bidon, sans rapport avec le vrai modèle (1024) — accélère les tests


def _make_chunk(i, source_doc="DOC-TEST", article_num=None, text=None):
    return {
        "text": text if text is not None else f"Texte du chunk numéro {i}, contenu de test suffisamment long.",
        "metadata": {
            "source_doc": source_doc,
            "version": "1.0",
            "titre_humain": "Document de test",
            "chapitre_titre": "",
            "article_num": str(article_num if article_num is not None else i),
        },
    }


def _setup(tmp_path, monkeypatch, chunks, *, embeddings=None, meta_overrides=None):
    """
    Écrit chunks.json + embeddings.npy + embeddings.meta.json dans tmp_path et
    redirige les chemins du module vers ces fichiers. Par défaut, les fichiers
    sont mutuellement cohérents (cas valide) ; `meta_overrides`/`embeddings`
    permettent de casser volontairement la cohérence pour tester les gardes.
    """
    chunks_path = tmp_path / "chunks.json"
    chunks_bytes = json.dumps(chunks).encode("utf-8")
    chunks_path.write_bytes(chunks_bytes)

    embeddings_path = tmp_path / "embeddings.npy"
    meta_path = tmp_path / "embeddings.meta.json"

    if embeddings is None:
        embeddings = np.random.rand(len(chunks), DIM).astype("float32")
    np.save(embeddings_path, embeddings)

    meta = {
        "model_name": "fake-model",
        "dimension": DIM,
        "n_chunks": len(chunks),
        "chunks_sha256": hashlib.sha256(chunks_bytes).hexdigest(),
        "chunk_ids": [index_chroma.chunk_id(c) for c in chunks],
    }
    if meta_overrides:
        meta.update(meta_overrides)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    monkeypatch.setattr(index_chroma, "CHUNKS_PATH", chunks_path)
    monkeypatch.setattr(index_chroma, "EMBEDDINGS_PATH", embeddings_path)
    monkeypatch.setattr(index_chroma, "META_PATH", meta_path)
    monkeypatch.setattr(index_chroma, "CHROMA_PATH", tmp_path / "chroma_db")


def test_build_index_fichiers_valides_pas_d_exception(tmp_path, monkeypatch):
    chunks = [_make_chunk(i, article_num=i) for i in range(5)]
    _setup(tmp_path, monkeypatch, chunks)

    collection = index_chroma.build_index(force_reset=True)

    assert collection.count() == 5


def test_build_index_sha256_modifie_leve_erreur_explicite(tmp_path, monkeypatch):
    # meta référence un sha256 qui ne correspond plus à chunks.json (simule un
    # chunks.json modifié après la génération des embeddings).
    chunks = [_make_chunk(i, article_num=i) for i in range(5)]
    _setup(tmp_path, monkeypatch, chunks, meta_overrides={"chunks_sha256": "0" * 64})

    with pytest.raises(RuntimeError, match=r"precompute_embeddings\.py"):
        index_chroma.build_index(force_reset=True)


def test_build_index_chunk_ids_incoherents_leve_erreur_explicite(tmp_path, monkeypatch):
    chunks = [_make_chunk(i, article_num=i) for i in range(5)]
    _setup(tmp_path, monkeypatch, chunks, meta_overrides={"chunk_ids": ["id-invalide"] * 5})

    with pytest.raises(RuntimeError, match=r"precompute_embeddings\.py"):
        index_chroma.build_index(force_reset=True)


def test_build_index_mauvaise_forme_leve_erreur_explicite(tmp_path, monkeypatch):
    chunks = [_make_chunk(i, article_num=i) for i in range(5)]
    # 4 lignes seulement pour 5 chunks : forme (4, DIM) au lieu de (5, DIM).
    wrong_shape_embeddings = np.random.rand(4, DIM).astype("float32")
    _setup(tmp_path, monkeypatch, chunks, embeddings=wrong_shape_embeddings)

    with pytest.raises(RuntimeError, match=r"[Ff]orme"):
        index_chroma.build_index(force_reset=True)


def test_build_index_ids_dupliques_entre_batches_leve_une_exception(tmp_path, monkeypatch):
    # 52 chunks pour forcer 2 batches (batch_size=50 dans build_index) : le
    # chunk 51 duplique exactement le chunk 0 (même source_doc/article_num/
    # texte des 50 premiers caractères -> même chunk_id). Les deux IDs
    # dupliqués tombent dans des appels upsert() DIFFÉRENTS (pas le même
    # batch) : chromadb ne lève pas DuplicateIDError (qui ne détecte que les
    # doublons DANS un même appel) - upsert traite le second comme une mise à
    # jour de l'id existant, donc count() reste à 51 alors que len(chunks)=52.
    # C'est exactement le cas que notre garde count()!=len(chunks) doit attraper.
    base_text = "Texte identique pour forcer une collision d'ID de chunk."
    chunks = [_make_chunk(i, article_num=i) for i in range(51)]
    chunks[0]["text"] = base_text
    duplicate_of_chunk_0 = _make_chunk(51, source_doc="DOC-TEST", article_num=0, text=base_text)
    chunks.append(duplicate_of_chunk_0)  # 52 chunks, chunks[51] duplique chunks[0]

    assert index_chroma.chunk_id(chunks[0]) == index_chroma.chunk_id(chunks[51])
    _setup(tmp_path, monkeypatch, chunks)

    with pytest.raises(RuntimeError, match=r"51 documents indexés, 52 attendus"):
        index_chroma.build_index(force_reset=True)


def test_duplicate_id_dans_le_meme_batch_leve_l_erreur_native_chroma(tmp_path, monkeypatch):
    # Si le doublon tombe DANS le même appel upsert() (ici : 2 chunks
    # identiques parmi les 5 premiers, batch unique car < 50), c'est chromadb
    # lui-même qui lève AVANT d'atteindre notre garde - à ne pas confondre
    # avec le cas ci-dessus.
    import chromadb

    base_text = "Texte identique, même batch cette fois."
    chunks = [_make_chunk(i, article_num=i) for i in range(3)]
    chunks[1] = _make_chunk(1, source_doc=chunks[0]["metadata"]["source_doc"],
                             article_num=chunks[0]["metadata"]["article_num"], text=base_text)
    chunks[0]["text"] = base_text
    assert index_chroma.chunk_id(chunks[0]) == index_chroma.chunk_id(chunks[1])
    _setup(tmp_path, monkeypatch, chunks)

    with pytest.raises(chromadb.errors.DuplicateIDError):
        index_chroma.build_index(force_reset=True)


def test_build_index_fichiers_absents_leve_erreur_explicite(tmp_path, monkeypatch):
    chunks = [_make_chunk(i, article_num=i) for i in range(5)]
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(json.dumps(chunks), encoding="utf-8")
    monkeypatch.setattr(index_chroma, "CHUNKS_PATH", chunks_path)
    monkeypatch.setattr(index_chroma, "EMBEDDINGS_PATH", tmp_path / "absent.npy")
    monkeypatch.setattr(index_chroma, "META_PATH", tmp_path / "absent.meta.json")
    monkeypatch.setattr(index_chroma, "CHROMA_PATH", tmp_path / "chroma_db")

    with pytest.raises(RuntimeError, match=r"precompute_embeddings\.py"):
        index_chroma.build_index(force_reset=True)

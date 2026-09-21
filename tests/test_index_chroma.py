"""
Tests unitaires de la garde d'indexation (build_index, src/index_chroma.py).
Aucun réseau, aucun modèle réel (encode() est mocké), aucun appel API Anthropic.
CHROMA_PATH et CHUNKS_PATH sont toujours redirigés vers tmp_path — jamais le
dossier réel du dépôt (build_index(force_reset=True) supprime la collection).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import index_chroma


class _FakeEmbedModel:
    """Modèle bidon : encode() renvoie un tableau numpy de la bonne forme, sans calcul réel."""

    def encode(self, texts, show_progress_bar=False, normalize_embeddings=True):
        return np.random.rand(len(texts), 8).astype("float32")


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


def _setup(tmp_path, monkeypatch, chunks):
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(json.dumps(chunks), encoding="utf-8")
    monkeypatch.setattr(index_chroma, "CHUNKS_PATH", chunks_path)
    monkeypatch.setattr(index_chroma, "CHROMA_PATH", tmp_path / "chroma_db")
    monkeypatch.setattr(index_chroma, "_load_embed_model", lambda: _FakeEmbedModel())


def test_build_index_chunks_valides_pas_d_exception(tmp_path, monkeypatch):
    chunks = [_make_chunk(i, article_num=i) for i in range(5)]
    _setup(tmp_path, monkeypatch, chunks)

    collection = index_chroma.build_index(force_reset=True)

    assert collection.count() == 5


def test_build_index_ids_dupliques_leve_une_exception(tmp_path, monkeypatch):
    # 52 chunks pour forcer 2 batches (batch_size=50 dans build_index) :
    # le chunk 51 duplique exactement le chunk 0 (même source_doc/article_num/
    # texte des 50 premiers caractères -> même chunk_id). Comme les deux IDs
    # dupliqués tombent dans des appels upsert() DIFFÉRENTS (pas le même batch),
    # chromadb ne lève PAS DuplicateIDError (qui ne détecte que les doublons
    # DANS un même appel) - upsert traite le second comme une mise à jour de
    # l'id existant, donc count() reste à 51 alors que len(chunks)=52.
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
    # Si le doublon tombe DANS le même appel upsert() (ici : 2 chunks identiques
    # parmi les 5 premiers, batch unique car < 50), c'est chromadb lui-même qui
    # lève AVANT d'atteindre notre garde - à ne pas confondre avec le cas ci-dessus.
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

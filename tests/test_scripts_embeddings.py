"""
Tests hors ligne des scripts src/precompute_embeddings.py et
src/test_retrieval.py (sous-lot 2.1). Aucun appel API : agent.embed_texts est
toujours remplacé par un double. Tous les chemins sont redirigés vers tmp_path.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import agent
import index_chroma
import precompute_embeddings
import test_retrieval


def _faux_embed(appels):
    def _embed(texts):
        appels.append(list(texts))
        out = []
        for t in texts:
            v = np.zeros(agent.EMBED_DIMENSION, dtype=np.float32)
            v[hash(t) % agent.EMBED_DIMENSION] = 1.0
            out.append(v.tolist())
        return out

    return _embed


def test_precompute_ecrit_des_fichiers_acceptes_par_index_chroma(tmp_path, monkeypatch):
    chunks = json.loads((ROOT / "data" / "chunks" / "chunks.json").read_text(encoding="utf-8"))[:5]
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(json.dumps(chunks), encoding="utf-8")
    appels = []
    monkeypatch.setattr(agent, "embed_texts", _faux_embed(appels))
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "eu")
    for module in (precompute_embeddings, index_chroma):
        monkeypatch.setattr(module, "CHUNKS_PATH", chunks_path)
        monkeypatch.setattr(module, "EMBEDDINGS_PATH", tmp_path / "embeddings.npy")
        monkeypatch.setattr(module, "META_PATH", tmp_path / "embeddings.meta.json")
    monkeypatch.setattr(index_chroma, "CHROMA_PATH", tmp_path / "chroma_db")

    precompute_embeddings.main()

    assert appels == [[c["text"] for c in chunks]]  # texte brut, sans préfixe
    meta = json.loads((tmp_path / "embeddings.meta.json").read_text(encoding="utf-8"))
    assert meta["model_name"] == "mistral-embed"
    assert meta["dimension"] == 1024
    assert meta["mistral_server"] == "eu"
    assert not any(k.startswith(("torch", "sentence", "transformers")) for k in meta)
    # La garde du build accepte ces fichiers.
    assert index_chroma.build_index(force_reset=True).count() == 5


def test_precompute_echec_api_n_ecrit_rien(tmp_path, monkeypatch):
    def _echec(texts):
        raise agent.EmbeddingServiceError("x")

    monkeypatch.setattr(agent, "embed_texts", _echec)
    monkeypatch.setattr(precompute_embeddings, "EMBEDDINGS_PATH", tmp_path / "embeddings.npy")
    monkeypatch.setattr(precompute_embeddings, "META_PATH", tmp_path / "embeddings.meta.json")

    with pytest.raises(agent.EmbeddingServiceError):
        precompute_embeddings.main()
    assert not (tmp_path / "embeddings.npy").exists()
    assert not (tmp_path / "embeddings.meta.json").exists()


def test_cache_des_questions_n_appelle_l_api_que_pour_les_absentes(tmp_path, monkeypatch):
    appels = []
    monkeypatch.setattr(agent, "embed_texts", _faux_embed(appels))
    monkeypatch.setattr(test_retrieval, "CACHE_PATH", tmp_path / "cache.json")

    premiers = test_retrieval._vecteurs_questions("mistral-embed", ["q1", "q2"])
    seconds = test_retrieval._vecteurs_questions("mistral-embed", ["q1", "q2", "q3"])

    assert appels == [["q1", "q2"], ["q3"]]
    assert seconds[:2] == premiers
    # La clé dépend du modèle : un autre modèle ne réutilise pas les vecteurs.
    test_retrieval._vecteurs_questions("autre-modele", ["q1"])
    assert appels[-1] == ["q1"]


def test_test_retrieval_refuse_un_index_d_un_autre_modele(tmp_path, monkeypatch):
    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path / "chroma_db"))
    client.get_or_create_collection(
        name=test_retrieval.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "model_name": "intfloat/multilingual-e5-large"},
    )
    monkeypatch.setattr(test_retrieval, "CHROMA_PATH", tmp_path / "chroma_db")
    monkeypatch.setattr(agent, "embed_texts", lambda texts: pytest.fail("aucun encodage attendu"))

    with pytest.raises(SystemExit, match="Reconstruisez l'index"):
        test_retrieval.run_retrieval_tests()


def test_test_retrieval_affiche_rangs_et_scores(tmp_path, monkeypatch, capsys):
    """Index factice où chaque article attendu est le plus proche de sa question."""
    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path / "chroma_db"))
    col = client.get_or_create_collection(
        name=test_retrieval.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "model_name": agent.MODEL_NAME},
    )
    avec_cible = [t for t in test_retrieval.TESTS if t["expected_article"] is not None]

    def _vec(i):
        v = [0.0] * agent.EMBED_DIMENSION
        v[i] = 1.0
        return v

    col.upsert(
        ids=[f"c{i}" for i in range(len(avec_cible))],
        embeddings=[_vec(i) for i in range(len(avec_cible))],
        metadatas=[{"source_doc": t["expected_doc"], "article_num": t["expected_article"]} for t in avec_cible],
        documents=["d"] * len(avec_cible),
    )
    position = {t["question"]: i for i, t in enumerate(avec_cible)}

    def _embed(texts):
        return [_vec(position[t]) if t in position else _vec(agent.EMBED_DIMENSION - 1) for t in texts]

    monkeypatch.setattr(agent, "embed_texts", _embed)
    monkeypatch.setattr(test_retrieval, "CHROMA_PATH", tmp_path / "chroma_db")
    monkeypatch.setattr(test_retrieval, "CACHE_PATH", tmp_path / "cache.json")

    test_retrieval.run_retrieval_tests()
    sortie = capsys.readouterr().out
    n = len(avec_cible)
    assert f"top-1: {n}/{n}" in sortie
    assert f"top-10: {n}/{n}" in sortie
    assert "rang=1" in sortie
    assert "Q20 top-1 dist:" in sortie

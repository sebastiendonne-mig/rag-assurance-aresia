"""
Indexation Chroma : lit les embeddings PRÉ-CALCULÉS (data/chunks/embeddings.npy
+ embeddings.meta.json, générés localement par src/precompute_embeddings.py)
plutôt que de les calculer ici. Le calcul (model.encode) au build faisait
expirer le build Cloud Build (30 min) — voir src/precompute_embeddings.py
pour régénérer ces fichiers après tout changement de data/chunks/chunks.json.

Convention e5 : passages préfixés "passage: ", requêtes préfixées "query: ".

Aucun import de sentence_transformers/torch ici : ce module est utilisé au
build de l'image Docker et ne doit jamais charger de modèle ni calculer
d'embedding.
"""
import hashlib
import json
from pathlib import Path

import chromadb
import numpy as np

ROOT = Path(__file__).parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.json"
EMBEDDINGS_PATH = ROOT / "data" / "chunks" / "embeddings.npy"
META_PATH = ROOT / "data" / "chunks" / "embeddings.meta.json"
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "assur_docs"
MODEL_NAME = "intfloat/multilingual-e5-large"


def chunk_id(chunk: dict) -> str:
    """ID déterministe basé sur source + article + hash du texte."""
    key = f"{chunk['metadata']['source_doc']}_{chunk['metadata']['article_num']}_{chunk['text'][:50]}"
    return hashlib.md5(key.encode()).hexdigest()


def _load_precomputed_embeddings(chunks: list[dict]) -> np.ndarray:
    """
    Charge embeddings.npy et vérifie sa cohérence avec chunks.json actuel.
    Ne calcule JAMAIS d'embedding ici — au moindre écart (fichiers absents,
    chunks.json modifié depuis la génération, chunk_id différents, forme
    inattendue), lève une erreur explicite. Aucun repli vers model.encode().
    """
    if not EMBEDDINGS_PATH.exists() or not META_PATH.exists():
        raise RuntimeError(
            f"{EMBEDDINGS_PATH.name} ou {META_PATH.name} introuvable dans "
            f"{EMBEDDINGS_PATH.parent}. Lancez `python src/precompute_embeddings.py` "
            "en local, committez les deux fichiers, puis relancez le build."
        )

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))

    actual_sha256 = hashlib.sha256(CHUNKS_PATH.read_bytes()).hexdigest()
    expected_sha256 = meta.get("chunks_sha256")
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "data/chunks/chunks.json a changé depuis la génération des embeddings "
            f"(sha256 attendu={expected_sha256!r}, actuel={actual_sha256!r}). "
            "Lancez `python src/precompute_embeddings.py` en local pour régénérer, "
            "committez, puis relancez le build."
        )

    expected_ids = [chunk_id(c) for c in chunks]
    if meta.get("chunk_ids") != expected_ids:
        raise RuntimeError(
            "Les chunk_id recalculés depuis chunks.json ne correspondent pas à "
            "ceux enregistrés dans embeddings.meta.json. "
            "Lancez `python src/precompute_embeddings.py` en local pour régénérer, "
            "committez, puis relancez le build."
        )

    embeddings = np.load(EMBEDDINGS_PATH)
    expected_shape = (len(chunks), meta.get("dimension"))
    if embeddings.shape != expected_shape:
        raise RuntimeError(
            f"Forme des embeddings inattendue : {embeddings.shape}, "
            f"attendu {expected_shape}. Lancez `python src/precompute_embeddings.py` "
            "en local pour régénérer, committez, puis relancez le build."
        )

    return embeddings


def build_index(force_reset: bool = False) -> chromadb.Collection:
    print("Chargement chunks...")
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"  {len(chunks)} chunks à indexer")

    print("Chargement des embeddings pré-calculés (aucun calcul au build)...")
    embeddings = _load_precomputed_embeddings(chunks)
    print(f"  Embeddings chargés : shape {embeddings.shape}")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    if force_reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print("Collection existante supprimée (force_reset=True)")
        except Exception:
            pass

    # Chroma gère ses propres embeddings via la fonction add(),
    # mais on fournit les embeddings précalculés pour contrôler le préfixe e5
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "model_name": MODEL_NAME},
    )

    ids = [chunk_id(c) for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    embeddings_list = embeddings.tolist()

    # Upsert par batch de 50
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            embeddings=embeddings_list[i : i + batch_size],
            documents=documents[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )
    indexed_count = collection.count()
    print(f"Upsert terminé — {indexed_count} documents dans la collection")
    if indexed_count != len(chunks):
        raise RuntimeError(
            f"Indexation incomplète : {indexed_count} documents indexés, "
            f"{len(chunks)} attendus (collision d'ID ou upsert partiel)."
        )
    return collection


if __name__ == "__main__":
    import sys

    print("=== Indexation Chroma (depuis embeddings pré-calculés) ===\n")
    col = build_index(force_reset=True)
    print(f"\nCollection '{COLLECTION_NAME}' prête : {col.count()} chunks indexés")
    if col.count() == 0:
        print("ERREUR : collection vide après indexation — build en échec.", file=sys.stderr)
        sys.exit(1)

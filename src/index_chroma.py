"""
Indexation Chroma : embeddings multilingual-e5-large + upsert avec métadonnées.
Convention e5 : passages préfixés "passage: ", requêtes préfixées "query: ".
"""
import json
import hashlib
from pathlib import Path

import chromadb
import torch
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.json"
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "assur_docs"
MODEL_NAME = "intfloat/multilingual-e5-large"


def chunk_id(chunk: dict) -> str:
    """ID déterministe basé sur source + article + hash du texte."""
    key = f"{chunk['metadata']['source_doc']}_{chunk['metadata']['article_num']}_{chunk['text'][:50]}"
    return hashlib.md5(key.encode()).hexdigest()


def build_index(force_reset: bool = False) -> chromadb.Collection:
    print(f"Chargement modèle : {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME, model_kwargs={"torch_dtype": torch.bfloat16})

    print("Chargement chunks...")
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"  {len(chunks)} chunks à indexer")

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

    # Préfixe e5 obligatoire pour les passages
    texts_to_embed = ["passage: " + c["text"] for c in chunks]

    print("Calcul des embeddings (peut prendre 1-2 min)...")
    embeddings = model.encode(texts_to_embed, show_progress_bar=True, normalize_embeddings=True)
    print(f"  Embeddings calculés : shape {embeddings.shape}")

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
    print(f"Upsert terminé — {collection.count()} documents dans la collection")
    return collection


if __name__ == "__main__":
    print("=== Indexation Chroma ===\n")
    col = build_index(force_reset=True)
    print(f"\nCollection '{COLLECTION_NAME}' prête : {col.count()} chunks indexés")

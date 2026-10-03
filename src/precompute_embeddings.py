"""
Génère data/chunks/embeddings.npy + embeddings.meta.json à partir de
data/chunks/chunks.json.

Script de GÉNÉRATION LOCALE UNIQUEMENT — jamais exécuté au build Docker.
src/index_chroma.py lit les fichiers produits ici au lieu de calculer les
embeddings au build (le build n'a pas de clé d'API).

À relancer chaque fois que data/chunks/chunks.json change, ou que le modèle
d'embeddings change.

Usage : python src/precompute_embeddings.py
Prérequis : MISTRAL_API_KEY dans l'environnement (ou le .env local, lu par
agent.py). APPELS RÉELS à l'API d'embeddings Mistral : un par lot de
agent.EMBED_BATCH_SIZE chunks. Les fichiers ne sont écrits qu'après le succès
de tous les lots.
"""
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.json"
EMBEDDINGS_PATH = ROOT / "data" / "chunks" / "embeddings.npy"
META_PATH = ROOT / "data" / "chunks" / "embeddings.meta.json"


def chunk_id(chunk: dict) -> str:
    """ID déterministe basé sur source + article + hash du texte.
    Dupliqué volontairement depuis index_chroma.chunk_id : ce script de
    génération ne doit dépendre d'aucun module du chemin de build."""
    key = f"{chunk['metadata']['source_doc']}_{chunk['metadata']['article_num']}_{chunk['text'][:50]}"
    return hashlib.md5(key.encode()).hexdigest()


def main() -> None:
    from importlib.metadata import version

    import numpy as np

    sys.path.insert(0, str(ROOT / "src"))
    import agent
    import index_chroma

    if agent.MODEL_NAME != index_chroma.MODEL_NAME:
        sys.exit(
            f"ERREUR : MISTRAL_EMBED_MODEL={agent.MODEL_NAME!r} diffère du modèle attendu par "
            f"src/index_chroma.py ({index_chroma.MODEL_NAME!r}) : le build refuserait ces fichiers."
        )

    print("Chargement chunks...")
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"  {len(chunks)} chunks à encoder")

    chunks_sha256 = hashlib.sha256(CHUNKS_PATH.read_bytes()).hexdigest()
    ids = [chunk_id(c) for c in chunks]

    print(
        f"Encodage via l'API Mistral : modèle {agent.MODEL_NAME}, serveur {agent.MISTRAL_SERVER} "
        f"({agent.mistral_endpoint_host()}), lots de {agent.EMBED_BATCH_SIZE}..."
    )
    embeddings = np.asarray(agent.embed_texts([c["text"] for c in chunks]), dtype=np.float32)
    normes = np.linalg.norm(embeddings, axis=1)
    print(f"  Embeddings calculés : shape {embeddings.shape}, dtype {embeddings.dtype}")
    print(f"  Normes : min={normes.min():.4f} max={normes.max():.4f} (1 attendu d'après la doc Mistral)")

    np.save(EMBEDDINGS_PATH, embeddings)

    meta = {
        "model_name": agent.MODEL_NAME,
        "dimension": int(embeddings.shape[1]),
        "n_chunks": int(embeddings.shape[0]),
        "chunks_sha256": chunks_sha256,
        "chunk_ids": ids,
        "mistral_server": agent.MISTRAL_SERVER,
        "mistral_endpoint_host": agent.mistral_endpoint_host(),
        "mistralai_version": version("mistralai"),
        "platform_machine": platform.machine(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Écrit : {EMBEDDINGS_PATH}")
    print(f"Écrit : {META_PATH}")


if __name__ == "__main__":
    main()

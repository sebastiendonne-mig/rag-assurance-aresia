"""
Génère data/chunks/embeddings.npy + embeddings.meta.json à partir de
data/chunks/chunks.json.

Script de GÉNÉRATION LOCALE UNIQUEMENT — jamais exécuté au build Docker.
src/index_chroma.py lit les fichiers produits ici au lieu de calculer les
embeddings au build (le calcul via model.encode() faisait expirer le build
Cloud Build à 30 min).

À relancer chaque fois que data/chunks/chunks.json change.

Usage : python src/precompute_embeddings.py
Prérequis : le modèle intfloat/multilingual-e5-large doit être présent en
cache HF local (ou pré-téléchargé dans models/e5-large-fp32). Lancer avec
HF_HUB_OFFLINE=1 pour garantir qu'aucun téléchargement n'est tenté.
"""
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.json"
EMBEDDINGS_PATH = ROOT / "data" / "chunks" / "embeddings.npy"
META_PATH = ROOT / "data" / "chunks" / "embeddings.meta.json"
MODEL_NAME = "intfloat/multilingual-e5-large"
# Même chemin que agent.py:EMBED_MODEL_LOCAL_PATH — si ce script tourne après
# l'étape de pré-téléchargement du Dockerfile (ou un téléchargement local
# équivalent), on réutilise ces poids plutôt que de retélécharger le modèle.
# fp32 (précision native) depuis le 23/09/2026 — voir agent.py pour le
# contexte du passage bf16 -> fp32 (lenteur ~25x en bf16 sur CPU Cloud Run).
EMBED_MODEL_LOCAL_PATH = ROOT / "models" / "e5-large-fp32"


def chunk_id(chunk: dict) -> str:
    """ID déterministe basé sur source + article + hash du texte.
    Dupliqué volontairement depuis index_chroma.chunk_id : ce script de
    génération ne doit dépendre d'aucun module du chemin de build."""
    key = f"{chunk['metadata']['source_doc']}_{chunk['metadata']['article_num']}_{chunk['text'][:50]}"
    return hashlib.md5(key.encode()).hexdigest()


def _load_embed_model():
    from sentence_transformers import SentenceTransformer

    if EMBED_MODEL_LOCAL_PATH.exists():
        print(f"Chargement modèle (fp32 pré-téléchargé) : {EMBED_MODEL_LOCAL_PATH}")
        return SentenceTransformer(str(EMBED_MODEL_LOCAL_PATH))
    print(f"Chargement modèle : {MODEL_NAME} (pas de poids pré-téléchargés trouvés)")
    return SentenceTransformer(MODEL_NAME)


def main() -> None:
    import numpy as np
    import sentence_transformers
    import torch
    import transformers

    print("Chargement chunks...")
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"  {len(chunks)} chunks à encoder")

    chunks_sha256 = hashlib.sha256(CHUNKS_PATH.read_bytes()).hexdigest()
    ids = [chunk_id(c) for c in chunks]

    model = _load_embed_model()

    # Préfixe e5 obligatoire pour les passages
    texts_to_embed = ["passage: " + c["text"] for c in chunks]

    print("Calcul des embeddings (peut prendre 1-2 min)...")
    embeddings = model.encode(texts_to_embed, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype=np.float32)
    print(f"  Embeddings calculés : shape {embeddings.shape}, dtype {embeddings.dtype}")

    np.save(EMBEDDINGS_PATH, embeddings)

    meta = {
        "model_name": MODEL_NAME,
        "dimension": int(embeddings.shape[1]),
        "n_chunks": int(embeddings.shape[0]),
        "chunks_sha256": chunks_sha256,
        "chunk_ids": ids,
        "sentence_transformers_version": sentence_transformers.__version__,
        "transformers_version": transformers.__version__,
        "torch_version": torch.__version__,
        "platform_machine": platform.machine(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Écrit : {EMBEDDINGS_PATH}")
    print(f"Écrit : {META_PATH}")


if __name__ == "__main__":
    main()

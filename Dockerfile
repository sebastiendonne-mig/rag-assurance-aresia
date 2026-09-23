FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV HF_HOME=/app/.cache/huggingface

# Télécharge le modèle et le sauvegarde dans l'image (/app/models/e5-large-fp32,
# précision native, pas de cast), puis supprime le cache HF (~2.24 Go, doublon
# de la copie sauvegardée) pour n'en garder qu'une seule dans l'image.
# fp32 depuis le 23/09/2026 — un essai en bfloat16 (21-22/09, pour réduire la
# RAM à ~1.07 Go au lieu de ~2.24 Go) s'est révélé ~25x plus lent au calcul sur
# le vCPU Cloud Run (pas de support matériel bf16 natif) : un upload de
# document prenait ~8 min au lieu de quelques secondes (mesuré : 287s bf16 vs
# 11s fp32 pour 21 chunks, CPU forcé/1 thread). Voir agent.py:EMBED_MODEL_LOCAL_PATH
# et MAINTENANCE-APPS-TKOIDRA.md section 8 pour l'investigation complète.
RUN python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('intfloat/multilingual-e5-large'); m.save('/app/models/e5-large-fp32')" \
    && rm -rf /app/.cache/huggingface

COPY app.py .
COPY src/ ./src/
COPY data/ ./data/
COPY assets/ ./assets/
COPY .streamlit/ ./.streamlit/
COPY *.pdf ./

# Construit l'index Chroma au build, à partir des embeddings PRÉ-CALCULÉS
# committés (data/chunks/embeddings.npy + .meta.json, générés en local par
# src/precompute_embeddings.py — jamais calculés ici : le calcul via
# model.encode() à cette étape faisait expirer le build Cloud Build à 30 min).
# chroma_db/ n'est pas copié depuis le disque local (voir .gitignore/.gcloudignore) :
# l'image est reproductible depuis git seul, sans dépendre d'un état local non commité.
# Échoue le build si les embeddings pré-calculés sont absents/incohérents avec
# chunks.json, ou si la collection reste vide/incomplète.
RUN python src/index_chroma.py

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true"]

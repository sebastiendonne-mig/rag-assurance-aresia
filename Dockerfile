FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV HF_HOME=/app/.cache/huggingface

# Télécharge le modèle, le convertit en bfloat16 et le sauvegarde dans l'image
# (/app/models/e5-large-bf16), puis supprime le cache HF fp32 (~2.24 Go) pour ne
# garder que la version finale bf16 (~1.07 Go) dans l'image. Évite aussi le pic
# mémoire au runtime causé par le chargement fp32 + cast a posteriori.
RUN python -c "import torch; from sentence_transformers import SentenceTransformer; m = SentenceTransformer('intfloat/multilingual-e5-large', model_kwargs={'torch_dtype': torch.bfloat16}); m.save('/app/models/e5-large-bf16')" \
    && rm -rf /app/.cache/huggingface

COPY app.py .
COPY src/ ./src/
COPY data/ ./data/
COPY chroma_db/ ./chroma_db/
COPY assets/ ./assets/
COPY .streamlit/ ./.streamlit/
COPY *.pdf ./

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true"]

FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY src/ ./src/
COPY data/ ./data/
COPY assets/ ./assets/
COPY .streamlit/ ./.streamlit/
COPY *.pdf ./

# Construit l'index Chroma au build, à partir des embeddings PRÉ-CALCULÉS
# committés (data/chunks/embeddings.npy + .meta.json, générés en local par
# src/precompute_embeddings.py via l'API Mistral — jamais calculés ici : le build
# n'a pas de clé d'API. Plus aucun modèle local (torch, sentence-transformers)
# dans l'image depuis le sous-lot 2.3).
# chroma_db/ n'est pas copié depuis le disque local (voir .gitignore/.gcloudignore) :
# l'image est reproductible depuis git seul, sans dépendre d'un état local non commité.
# Échoue le build si les embeddings pré-calculés sont absents/incohérents avec
# chunks.json, ou si la collection reste vide/incomplète.
RUN python src/index_chroma.py

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true"]

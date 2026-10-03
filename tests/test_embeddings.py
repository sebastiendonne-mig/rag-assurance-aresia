"""
Tests unitaires de l'encodage via l'API d'embeddings Mistral (sous-lot 2.1).
Aucun réseau, aucune clé, aucun appel API réel : le client Mistral est
toujours remplacé par un double, et time.sleep est mocké pour qu'aucun test
n'attende réellement le délai de réessai.
"""
import ast
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import agent

DIM = agent.EMBED_DIMENSION


def _vecteur(valeur: float, dim: int = DIM) -> list[float]:
    return [valeur] * dim


class _FakeEmbeddingResponse:
    def __init__(self, vecteurs: list[list[float]], ordre: list[int] | None = None):
        indices = ordre if ordre is not None else list(range(len(vecteurs)))
        self.data = [SimpleNamespace(embedding=vecteurs[i], index=i) for i in indices]
        self.id = "emb-fake-0001"
        self.model = "mistral-embed"
        self.usage = SimpleNamespace(prompt_tokens=1, total_tokens=1)


class _FakeMistralError(Exception):
    """Double de MistralError : une seule classe, un attribut .status_code."""

    def __init__(self, status_code: int | None = None, headers: dict | None = None):
        super().__init__(f"fake mistral error {status_code}")
        self.status_code = status_code
        self.headers = headers or {}


class _FakeEmbeddingsClient:
    """
    Double du client Mistral : embeddings.create renvoie, pour chaque lot, un
    vecteur constant par texte (valeur = rang global du texte), sauf si la
    file `erreurs` fournit une exception à lever pour cet appel.
    """

    def __init__(self, erreurs: list | None = None, dim: int = DIM):
        self.lots: list[list[str]] = []
        self.kwargs: list[dict] = []
        self._erreurs = list(erreurs or [])
        self._dim = dim
        self._rang = 0
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.kwargs.append(kwargs)
        if self._erreurs:
            erreur = self._erreurs.pop(0)
            if erreur is not None:
                raise erreur
        lot = list(kwargs["inputs"])
        self.lots.append(lot)
        vecteurs = [_vecteur(float(self._rang + i), self._dim) for i in range(len(lot))]
        self._rang += len(lot)
        return _FakeEmbeddingResponse(vecteurs)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    dormi = []
    monkeypatch.setattr(agent.time, "sleep", lambda s: dormi.append(s))
    return dormi


@pytest.fixture(autouse=True)
def _cle_seule(monkeypatch):
    """Clé factice, et SURTOUT pas de MISTRAL_MODEL : l'encodage ne doit exiger que la clé."""
    monkeypatch.setenv("MISTRAL_API_KEY", "dummy-not-a-real-key")
    monkeypatch.setattr(agent, "MISTRAL_MODEL", None)
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "eu")
    monkeypatch.setattr(agent, "_mistral_client", None)
    yield
    monkeypatch.setattr(agent, "_mistral_client", None)


def _brancher(monkeypatch, client: _FakeEmbeddingsClient) -> _FakeEmbeddingsClient:
    monkeypatch.setattr(agent, "_get_mistral_client", lambda: client)
    return client


# ─────────────────────────────────────────────
# Appel nominal
# ─────────────────────────────────────────────

def test_lots_ordre_et_modele(monkeypatch):
    client = _brancher(monkeypatch, _FakeEmbeddingsClient())
    textes = [f"texte {i}" for i in range(40)]

    vecteurs = agent.embed_texts(textes)

    assert [len(l) for l in client.lots] == [16, 16, 8]
    assert [t for lot in client.lots for t in lot] == textes
    assert all(k["model"] == "mistral-embed" for k in client.kwargs)
    assert len(vecteurs) == 40
    assert [v[0] for v in vecteurs] == [float(i) for i in range(40)]


def test_aucun_prefixe_e5(monkeypatch):
    client = _brancher(monkeypatch, _FakeEmbeddingsClient())
    agent.embed_texts(["Quelle franchise ?", "Article 4.1 — Franchise."])
    assert client.lots == [["Quelle franchise ?", "Article 4.1 — Franchise."]]


def test_liste_vide_aucun_appel(monkeypatch):
    client = _brancher(monkeypatch, _FakeEmbeddingsClient())
    assert agent.embed_texts([]) == []
    assert client.lots == []


def test_ordre_retabli_selon_index(monkeypatch):
    class _Desordre(_FakeEmbeddingsClient):
        def _create(self, **kwargs):
            lot = list(kwargs["inputs"])
            return _FakeEmbeddingResponse([_vecteur(float(i)) for i in range(len(lot))], ordre=[2, 0, 1])

    _brancher(monkeypatch, _Desordre())
    vecteurs = agent.embed_texts(["a", "b", "c"])
    assert [v[0] for v in vecteurs] == [0.0, 1.0, 2.0]


def test_modele_configurable_par_variable(monkeypatch):
    client = _brancher(monkeypatch, _FakeEmbeddingsClient())
    monkeypatch.setattr(agent, "MISTRAL_EMBED_MODEL", "autre-modele-embed")
    agent.embed_texts(["x"])
    assert client.kwargs[0]["model"] == "autre-modele-embed"


def test_modele_par_defaut_mistral_embed():
    import os

    if not os.environ.get("MISTRAL_EMBED_MODEL"):
        assert agent.MISTRAL_EMBED_MODEL == "mistral-embed"
        assert agent.MODEL_NAME == "mistral-embed"


# ─────────────────────────────────────────────
# Dimension
# ─────────────────────────────────────────────

def test_dimension_1024():
    assert agent.EMBED_DIMENSION == 1024


def test_vecteurs_de_dimension_1024_acceptes(monkeypatch):
    _brancher(monkeypatch, _FakeEmbeddingsClient())
    vecteurs = agent.embed_texts(["a", "b"])
    assert all(len(v) == 1024 for v in vecteurs)


@pytest.mark.parametrize("dim", [768, 1023, 1025, 3072])
def test_dimension_inattendue_leve_et_journalise(monkeypatch, caplog, dim):
    _brancher(monkeypatch, _FakeEmbeddingsClient(dim=dim))
    with caplog.at_level(logging.WARNING, logger="agent"):
        with pytest.raises(agent.EmbeddingServiceError):
            agent.embed_texts(["texte secret du visiteur"])
    assert "EMBED_DIMENSION_INATTENDUE" in caplog.text
    assert "texte secret du visiteur" not in caplog.text


def test_nombre_de_vecteurs_incoherent_leve(monkeypatch):
    class _Manque(_FakeEmbeddingsClient):
        def _create(self, **kwargs):
            return _FakeEmbeddingResponse([_vecteur(0.0)])

    _brancher(monkeypatch, _Manque())
    with pytest.raises(agent.EmbeddingServiceError):
        agent.embed_texts(["a", "b"])


# ─────────────────────────────────────────────
# Disponibilité : la clé seule
# ─────────────────────────────────────────────

def test_disponible_avec_la_cle_seule_sans_mistral_model():
    assert agent.MISTRAL_MODEL is None
    assert agent.mistral_embeddings_disponible() is True
    assert agent.mistral_disponible() is False  # le moteur de chat, lui, reste indisponible


def test_client_construit_sans_mistral_model(monkeypatch):
    """_get_mistral_client() ne lève pas sans MISTRAL_MODEL, contrairement à get_mistral()."""
    client = agent._get_mistral_client()
    assert client is not None
    with pytest.raises(agent.MistralUnavailableError):
        agent.get_mistral()


def test_sans_cle_leve_sans_appel(monkeypatch, caplog):
    client = _brancher(monkeypatch, _FakeEmbeddingsClient())
    monkeypatch.delenv("MISTRAL_API_KEY")
    assert agent.mistral_embeddings_disponible() is False
    with caplog.at_level(logging.WARNING, logger="agent"):
        with pytest.raises(agent.EmbeddingServiceError):
            agent.embed_texts(["a"])
    assert client.lots == []
    assert "EMBED_INDISPONIBLE" in caplog.text


# ─────────────────────────────────────────────
# Erreurs et réessai (politique du moteur de chat)
# ─────────────────────────────────────────────

@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_erreur_reessayable_puis_succes(monkeypatch, status_code):
    client = _brancher(monkeypatch, _FakeEmbeddingsClient(erreurs=[_FakeMistralError(status_code)]))
    vecteurs = agent.embed_texts(["a"])
    assert len(vecteurs) == 1
    assert len(client.kwargs) == 2


def test_deux_echecs_reessayables_levent_apres_deux_appels(monkeypatch):
    client = _brancher(
        monkeypatch, _FakeEmbeddingsClient(erreurs=[_FakeMistralError(503), _FakeMistralError(503)])
    )
    with pytest.raises(agent.EmbeddingServiceError) as info:
        agent.embed_texts(["a"])
    assert len(client.kwargs) == 2
    assert isinstance(info.value.__cause__, _FakeMistralError)


@pytest.mark.parametrize("status_code", [400, 401, 403, 422])
def test_erreur_non_reessayable_un_seul_appel(monkeypatch, status_code):
    client = _brancher(monkeypatch, _FakeEmbeddingsClient(erreurs=[_FakeMistralError(status_code)]))
    with pytest.raises(agent.EmbeddingServiceError):
        agent.embed_texts(["a"])
    assert len(client.kwargs) == 1


def test_erreur_sur_un_lot_interrompt_tout(monkeypatch):
    """Un lot refusé : aucun résultat partiel renvoyé."""
    client = _brancher(
        monkeypatch, _FakeEmbeddingsClient(erreurs=[None, _FakeMistralError(400)])
    )
    with pytest.raises(agent.EmbeddingServiceError):
        agent.embed_texts([f"t{i}" for i in range(20)])
    assert len(client.lots) == 1


def test_log_warning_sans_contenu(monkeypatch, caplog):
    _brancher(monkeypatch, _FakeEmbeddingsClient(erreurs=[_FakeMistralError(400)]))
    with caplog.at_level(logging.WARNING, logger="agent"):
        with pytest.raises(agent.EmbeddingServiceError):
            agent.embed_texts(["contenu confidentiel du contrat"])
    assert "EMBED_ERROR" in caplog.text
    assert "status_code=400" in caplog.text
    assert "contenu confidentiel" not in caplog.text


def test_audit_d_un_appel_reussi_sans_contenu(monkeypatch, caplog):
    _brancher(monkeypatch, _FakeEmbeddingsClient())
    with caplog.at_level(logging.INFO, logger=agent.AUDIT_LOGGER_NAME):
        monkeypatch.setattr(agent.audit_log, "propagate", True)
        agent.embed_texts(["question confidentielle"])
    assert "EMBED_CALL" in caplog.text
    assert "request_id=emb-fake-0001" in caplog.text
    assert "server=eu" in caplog.text
    assert "question confidentielle" not in caplog.text


# ─────────────────────────────────────────────
# Mistral indisponible -> message neutre, pas de repli
# ─────────────────────────────────────────────

def test_mistral_indisponible_message_neutre():
    message = agent.format_user_error(agent.EmbeddingServiceError("détail technique secret"))
    assert message == (
        "La recherche dans les documents est momentanément indisponible. Merci de "
        "réessayer dans quelques instants."
    )
    assert "secret" not in message
    assert "Mistral" not in message


def test_mistral_en_erreur_remonte_jusqu_a_retrieve_chunks(monkeypatch):
    """Pas de repli : l'échec d'encodage remonte du retrieval du mode corpus, avec le message neutre."""

    class _Col:
        name, id = "assur_docs", "x"

        def count(self):
            return 51

        def query(self, **kwargs):
            raise AssertionError("aucune requête Chroma sans vecteur")

    monkeypatch.setattr(agent, "get_chroma_col", lambda: _Col())
    _brancher(monkeypatch, _FakeEmbeddingsClient(erreurs=[_FakeMistralError(401)]))
    with pytest.raises(agent.EmbeddingServiceError) as info:
        agent.retrieve_chunks("question")
    assert "momentanément indisponible" in agent.format_user_error(info.value)


# ─────────────────────────────────────────────
# Reconstruction Chroma au runtime : signalée en WARNING
# ─────────────────────────────────────────────

def test_reconstruction_runtime_signalee_en_warning(monkeypatch, caplog, tmp_path):
    import chromadb

    client_chroma = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    client_chroma.get_or_create_collection(
        name=agent.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "model_name": "intfloat/multilingual-e5-large"},
    )
    monkeypatch.setattr(agent, "CHROMA_PATH", tmp_path / "chroma")
    monkeypatch.setattr(agent, "_chroma_col", None)
    monkeypatch.setattr(agent, "_chroma_client", None)
    _brancher(monkeypatch, _FakeEmbeddingsClient())

    with caplog.at_level(logging.WARNING, logger="agent"):
        col = agent.get_chroma_col()

    assert col.metadata["model_name"] == agent.MODEL_NAME
    assert col.count() > 0
    assert "CHROMA rebuild au runtime" in caplog.text
    assert "modele_index=intfloat/multilingual-e5-large" in caplog.text
    monkeypatch.setattr(agent, "_chroma_col", None)
    monkeypatch.setattr(agent, "_chroma_client", None)


def test_reconstruction_runtime_echec_api_conserve_l_index(monkeypatch, tmp_path):
    """Encodage avant suppression : si l'API échoue, l'ancienne collection n'est pas détruite."""
    import chromadb

    client_chroma = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    ancienne = client_chroma.get_or_create_collection(
        name=agent.COLLECTION_NAME, metadata={"hnsw:space": "cosine", "model_name": "ancien"}
    )
    ancienne.upsert(ids=["a"], embeddings=[[0.1] * 4], documents=["d"])
    _brancher(monkeypatch, _FakeEmbeddingsClient(erreurs=[_FakeMistralError(401)]))

    with pytest.raises(agent.EmbeddingServiceError):
        agent._rebuild_chroma_index(client_chroma, "test")
    assert client_chroma.get_collection(agent.COLLECTION_NAME).count() == 1


# ─────────────────────────────────────────────
# Plus aucun modèle local dans le code de production
# ─────────────────────────────────────────────

@pytest.mark.parametrize("fichier", ["app.py", "src/agent.py", "src/upload_session.py", "src/index_chroma.py"])
def test_aucun_import_de_modele_local(fichier):
    arbre = ast.parse((ROOT / fichier).read_text(encoding="utf-8"))
    modules = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            modules.add(noeud.module.split(".")[0])
    assert not modules & {"torch", "sentence_transformers", "transformers"}


def test_plus_de_get_embed_model():
    assert not hasattr(agent, "get_embed_model")
    assert not hasattr(agent, "EMBED_MODEL_LOCAL_PATH")

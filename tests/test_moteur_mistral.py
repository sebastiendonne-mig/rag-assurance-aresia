"""
Tests unitaires du moteur Mistral sur le chemin upload (lot 3.1).
Aucun réseau, aucune clé, aucun appel API réel : le client Mistral est
toujours remplacé par un double, et time.sleep est mocké pour qu'aucun test
n'attende réellement le délai de réessai.
"""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import agent


class _FakeMistralUsage:
    """Forme Mistral : prompt_tokens/completion_tokens (pas input/output)."""

    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeMistralResponse:
    def __init__(self, text: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]
        self.usage = _FakeMistralUsage(prompt_tokens, completion_tokens)


class _FakeMistralError(Exception):
    """Double de MistralError : une seule classe, un attribut .status_code."""

    def __init__(self, status_code: int | None = None, headers: dict | None = None):
        super().__init__(f"fake mistral error {status_code}")
        self.status_code = status_code
        self.headers = headers or {}


class _QueueMistralClient:
    """Renvoie les éléments de la file dans l'ordre ; lève ceux qui sont des exceptions."""

    def __init__(self, resultats: list):
        self._resultats = list(resultats)
        self.call_count = 0
        self.chat = SimpleNamespace(complete=self._complete)
        self.derniers_messages = None

    def _complete(self, **kwargs):
        self.derniers_messages = kwargs.get("messages")
        resultat = self._resultats[self.call_count]
        self.call_count += 1
        if isinstance(resultat, Exception):
            raise resultat
        return resultat


@pytest.fixture(autouse=True)
def _reset_usage_ctx():
    """Isole chaque test : le ContextVar ne doit jamais fuiter d'un test à l'autre."""
    token = agent._usage_ctx.set(None)
    yield
    agent._usage_ctx.reset(token)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Aucune attente réelle : les délais de réessai sont enregistrés, pas dormis."""
    dormi = []
    monkeypatch.setattr(agent.time, "sleep", lambda s: dormi.append(s))
    return dormi


@pytest.fixture(autouse=True)
def _mistral_configure(monkeypatch):
    """Moteur Mistral considéré comme configuré, sans jamais lire de vraie clé."""
    monkeypatch.setenv("MISTRAL_API_KEY", "dummy-not-a-real-key")
    monkeypatch.delenv("MISTRAL_SERVER", raising=False)
    monkeypatch.setattr(agent, "MISTRAL_MODEL", "fake-model-for-tests")
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "eu")
    monkeypatch.setattr(agent, "_mistral_client", None)
    yield
    monkeypatch.setattr(agent, "_mistral_client", None)


# ─────────────────────────────────────────────
# Appel nominal et comptabilisation
# ─────────────────────────────────────────────

def test_llm_call_mistral_renvoie_le_texte_et_compte_les_tokens(monkeypatch):
    fake = _QueueMistralClient([
        _FakeMistralResponse("réponse mistral", prompt_tokens=120, completion_tokens=30),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    tracker = agent.UsageTracker()
    token = agent._usage_ctx.set(tracker)
    try:
        texte = agent.llm_call(
            [{"role": "user", "content": "q"}], system="s", engine=agent.ENGINE_MISTRAL
        )
    finally:
        agent._usage_ctx.reset(token)

    assert texte == "réponse mistral"
    assert fake.call_count == 1
    assert tracker.n_appels == 1
    assert tracker.tokens_in == 120
    assert tracker.tokens_out == 30


def test_llm_call_mistral_passe_le_system_en_premier_message(monkeypatch):
    fake = _QueueMistralClient([_FakeMistralResponse("ok")])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    agent.llm_call(
        [{"role": "user", "content": "q"}], system="consigne", engine=agent.ENGINE_MISTRAL
    )

    assert fake.derniers_messages[0] == {"role": "system", "content": "consigne"}
    assert fake.derniers_messages[1] == {"role": "user", "content": "q"}


def test_llm_call_defaut_reste_anthropic(monkeypatch):
    """Sans paramètre engine, le chemin Anthropic historique est emprunté."""
    monkeypatch.setattr(
        agent,
        "get_mistral",
        lambda: pytest.fail("get_mistral ne doit pas être appelé par défaut"),
    )
    fake_anthropic = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(
                content=[SimpleNamespace(text="réponse claude")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=2),
                stop_reason="end_turn",
            )
        )
    )
    monkeypatch.setattr(agent, "get_anthropic", lambda: fake_anthropic)

    assert agent.llm_call([{"role": "user", "content": "q"}]) == "réponse claude"


def test_llm_call_moteur_inconnu_leve(monkeypatch):
    with pytest.raises(ValueError):
        agent.llm_call([{"role": "user", "content": "q"}], engine="gemini")


# ─────────────────────────────────────────────
# Réessai unique — catégories reprises du SDK anthropic
# ─────────────────────────────────────────────

@pytest.mark.parametrize("status_code", [408, 409, 429, 500, 503])
def test_retry_sur_erreur_reessayable_puis_succes(monkeypatch, status_code):
    fake = _QueueMistralClient([
        _FakeMistralError(status_code=status_code),
        _FakeMistralResponse("ok après réessai", prompt_tokens=10, completion_tokens=5),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    tracker = agent.UsageTracker()
    token = agent._usage_ctx.set(tracker)
    try:
        texte = agent.llm_call(
            [{"role": "user", "content": "q"}], engine=agent.ENGINE_MISTRAL
        )
    finally:
        agent._usage_ctx.reset(token)

    assert texte == "ok après réessai"
    assert fake.call_count == 2
    # Seule la tentative réussie est comptabilisée : le réessai ne double rien.
    assert tracker.n_appels == 1
    assert tracker.tokens_in == 10
    assert tracker.tokens_out == 5


def test_deux_echecs_reessayables_remontent_apres_exactement_deux_appels(monkeypatch):
    fake = _QueueMistralClient([
        _FakeMistralError(status_code=429),
        _FakeMistralError(status_code=429),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    with pytest.raises(_FakeMistralError):
        agent.llm_call([{"role": "user", "content": "q"}], engine=agent.ENGINE_MISTRAL)

    assert fake.call_count == agent.MISTRAL_MAX_ATTEMPTS == 2


def test_erreur_reessayable_produit_un_message_neutre(monkeypatch):
    """Le visiteur ne voit jamais le détail de l'erreur, seulement un message neutre."""
    message = agent.format_user_error(_FakeMistralError(status_code=429))
    assert "Une erreur technique est survenue" in message
    assert "429" not in message


@pytest.mark.parametrize("status_code", [400, 401, 422])
def test_erreur_non_reessayable_un_seul_appel(monkeypatch, status_code):
    fake = _QueueMistralClient([
        _FakeMistralError(status_code=status_code),
        _FakeMistralResponse("ne doit jamais être atteint"),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    with pytest.raises(_FakeMistralError):
        agent.llm_call([{"role": "user", "content": "q"}], engine=agent.ENGINE_MISTRAL)

    assert fake.call_count == 1


def test_erreurs_de_connexion_et_timeout_sont_reessayees(monkeypatch):
    import httpx

    for exc in (httpx.ConnectError("boom"), httpx.ReadTimeout("boom")):
        fake = _QueueMistralClient([exc, _FakeMistralResponse("ok")])
        monkeypatch.setattr(agent, "get_mistral", lambda f=fake: f)

        texte = agent.llm_call(
            [{"role": "user", "content": "q"}], engine=agent.ENGINE_MISTRAL
        )

        assert texte == "ok"
        assert fake.call_count == 2


# ─────────────────────────────────────────────
# Délai de réessai
# ─────────────────────────────────────────────

def test_retry_after_present_est_respecte(monkeypatch, _no_real_sleep):
    fake = _QueueMistralClient([
        _FakeMistralError(status_code=429, headers={"retry-after": "2"}),
        _FakeMistralResponse("ok"),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    agent.llm_call([{"role": "user", "content": "q"}], engine=agent.ENGINE_MISTRAL)

    assert _no_real_sleep == [2.0]


def test_retry_after_au_dessus_du_plafond_est_plafonne(monkeypatch, _no_real_sleep):
    fake = _QueueMistralClient([
        _FakeMistralError(status_code=429, headers={"retry-after": "9999"}),
        _FakeMistralResponse("ok"),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    agent.llm_call([{"role": "user", "content": "q"}], engine=agent.ENGINE_MISTRAL)

    assert _no_real_sleep == [agent.MISTRAL_RETRY_AFTER_CAP_S]


def test_sans_retry_after_delai_fixe(monkeypatch, _no_real_sleep):
    fake = _QueueMistralClient([
        _FakeMistralError(status_code=500),
        _FakeMistralResponse("ok"),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    agent.llm_call([{"role": "user", "content": "q"}], engine=agent.ENGINE_MISTRAL)

    assert _no_real_sleep == [agent.MISTRAL_RETRY_DELAY_S]


def test_log_warning_par_retry_sans_contenu(monkeypatch, caplog):
    fake = _QueueMistralClient([
        _FakeMistralError(status_code=503),
        _FakeMistralResponse("réponse confidentielle"),
    ])
    monkeypatch.setattr(agent, "get_mistral", lambda: fake)

    with caplog.at_level("WARNING", logger="agent"):
        agent.llm_call(
            [{"role": "user", "content": "question confidentielle"}],
            engine=agent.ENGINE_MISTRAL,
        )

    messages = [r.getMessage() for r in caplog.records]
    retry_logs = [m for m in messages if "LLM_RETRY" in m]
    assert len(retry_logs) == 1
    assert "moteur=mistral" in retry_logs[0]
    assert "status_code=503" in retry_logs[0]
    assert "tentative=1/2" in retry_logs[0]
    # Jamais de contenu de question ni de réponse dans les logs (règle du lot 1).
    assert "confidentielle" not in retry_logs[0]


# ─────────────────────────────────────────────
# Disponibilité du moteur
# ─────────────────────────────────────────────

def test_mistral_indisponible_sans_cle(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    assert agent.mistral_disponible() is False
    with pytest.raises(agent.MistralUnavailableError):
        agent.get_mistral()


def test_mistral_indisponible_sans_modele(monkeypatch):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", None)
    assert agent.mistral_disponible() is False
    with pytest.raises(agent.MistralUnavailableError):
        agent.get_mistral()


def test_message_neutre_si_moteur_indisponible():
    message = agent.format_user_error(agent.MistralUnavailableError("peu importe"))
    assert "n'est pas disponible" in message
    assert "MISTRAL" not in message


# ─────────────────────────────────────────────
# Tarifs par moteur
# ─────────────────────────────────────────────

@pytest.fixture
def _modele_tarife(monkeypatch):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", agent.MISTRAL_PRICED_MODEL)


def test_le_modele_tarife_est_large_3():
    assert agent.MISTRAL_PRICED_MODEL == "mistral-large-2512"


@pytest.mark.parametrize("serveur", ["eu", "us"])
def test_tarifs_effectifs_regionaux(monkeypatch, _modele_tarife, serveur):
    """0.5 x 1.1 et 1.5 x 1.1 : jamais de == sur ces flottants, toujours approx."""
    monkeypatch.setattr(agent, "MISTRAL_SERVER", serveur)
    tarif_in, tarif_out = agent.mistral_tarifs_usd_par_mtok()
    assert tarif_in == pytest.approx(0.55)
    assert tarif_out == pytest.approx(1.65)


def test_tarifs_effectifs_global_au_tarif_catalogue(monkeypatch, _modele_tarife):
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "global")
    tarif_in, tarif_out = agent.mistral_tarifs_usd_par_mtok()
    assert tarif_in == pytest.approx(0.5)
    assert tarif_out == pytest.approx(1.5)


@pytest.mark.parametrize("serveur, attendu", [("eu", 2.20), ("us", 2.20), ("global", 2.00)])
def test_cout_mistral_complet_selon_l_endpoint(monkeypatch, _modele_tarife, serveur, attendu):
    """1 M tokens en entrée + 1 M en sortie : (0.5 + 1.5) x multiplicateur."""
    monkeypatch.setattr(agent, "MISTRAL_SERVER", serveur)
    cout = agent.estimer_cout_usd(1_000_000, 1_000_000, agent.ENGINE_MISTRAL)
    assert cout == pytest.approx(attendu)


def test_le_multiplicateur_suit_l_endpoint_sans_reglage_separe(monkeypatch, _modele_tarife):
    """Une seule source de vérité : changer MISTRAL_SERVER change le tarif."""
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "eu")
    eu = agent.estimer_cout_usd(1_000_000, 0, agent.ENGINE_MISTRAL)
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "global")
    glob = agent.estimer_cout_usd(1_000_000, 0, agent.ENGINE_MISTRAL)
    assert eu == pytest.approx(glob * 1.1)


@pytest.mark.parametrize(
    "modele",
    [
        "fake-model-for-tests",
        "mistral-large-latest",
        "mistral-large-2512-x",
        "Mistral-Large-2512",
        " mistral-large-2512",
        "mistral-large-2411",
    ],
)
def test_modele_non_tarife_donne_un_cout_none(monkeypatch, modele):
    """Égalité stricte : aucune normalisation, aucun préfixe, aucun alias."""
    monkeypatch.setattr(agent, "MISTRAL_MODEL", modele)
    assert agent.mistral_tarifs_usd_par_mtok() is None
    assert agent.estimer_cout_usd(1000, 100, agent.ENGINE_MISTRAL) is None


def test_modele_absent_donne_un_cout_none(monkeypatch):
    monkeypatch.setattr(agent, "MISTRAL_MODEL", None)
    assert agent.estimer_cout_usd(1000, 100, agent.ENGINE_MISTRAL) is None


def test_plus_aucune_surcharge_de_tarif_par_environnement(monkeypatch, _modele_tarife):
    """PRIX_MISTRAL_* n'existent plus : ni symbole, ni lecture de l'environnement."""
    monkeypatch.setenv("PRIX_MISTRAL_INPUT_USD_PAR_MTOK", "99")
    monkeypatch.setenv("PRIX_MISTRAL_OUTPUT_USD_PAR_MTOK", "99")
    assert not any(nom.startswith("PRIX_MISTRAL") for nom in dir(agent))
    assert not hasattr(agent, "_prix_env")
    cout = agent.estimer_cout_usd(1_000_000, 1_000_000, agent.ENGINE_MISTRAL)
    assert cout == pytest.approx(2.20)  # inchangé malgré les variables posées


def test_cout_anthropic_inchange():
    """Le tarif Anthropic reste celui du lot 1, moteur par défaut compris."""
    attendu = 3.0 + 15.0
    assert agent.estimer_cout_usd(1_000_000, 1_000_000) == pytest.approx(attendu)
    assert agent.estimer_cout_usd(
        1_000_000, 1_000_000, agent.ENGINE_ANTHROPIC
    ) == pytest.approx(attendu)


def test_usage_tracker_record_tokens_est_thread_safe():
    """La primitive bas niveau reste correcte sous concurrence."""
    tracker = agent.UsageTracker()

    def worker():
        for _ in range(100):
            tracker.record_tokens(1, 1)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert tracker.n_appels == 800
    assert tracker.tokens_in == 800
    assert tracker.tokens_out == 800


# ─────────────────────────────────────────────
# Endpoint UE par défaut, jamais de repli silencieux sur "global"
# ─────────────────────────────────────────────

def test_serveur_absent_donne_eu(monkeypatch):
    monkeypatch.delenv("MISTRAL_SERVER", raising=False)
    assert agent._resolve_mistral_server() == "eu"


@pytest.mark.parametrize("valeur", ["", " ", "   ", "\t", " \n "])
def test_serveur_vide_ou_espaces_traite_comme_absent(monkeypatch, valeur):
    """Un server vide retomberait sur "global" côté SDK : il ne doit jamais lui être transmis."""
    monkeypatch.setenv("MISTRAL_SERVER", valeur)
    assert agent._resolve_mistral_server() == "eu"


@pytest.mark.parametrize("valeur", ["eu", "us", "global"])
def test_serveurs_explicites_acceptes(monkeypatch, valeur):
    monkeypatch.setenv("MISTRAL_SERVER", valeur)
    assert agent._resolve_mistral_server() == valeur


@pytest.mark.parametrize("valeur", ["EU", "Eu", " eu ", "eu ", " eu", "europe", "US", "Global", "api.eu.mistral.ai"])
def test_serveur_invalide_leve_sans_repli_sur_global(monkeypatch, valeur):
    """Minuscules strictes, sans normalisation : aucune tolérance, aucun repli."""
    monkeypatch.setenv("MISTRAL_SERVER", valeur)
    with pytest.raises(ValueError) as info:
        agent._resolve_mistral_server()
    message = str(info.value)
    assert "MISTRAL_SERVER invalide" in message
    assert "eu, us, global" in message
    assert "minuscules" in message


def test_le_defaut_n_est_pas_global():
    assert agent.MISTRAL_SERVER_DEFAUT == "eu"
    assert agent.MISTRAL_SERVER_DEFAUT != "global"


def test_liste_des_serveurs_alignee_sur_le_sdk():
    """Garde : une mise à jour du SDK qui ajoute/retire un serveur doit faire échouer la suite."""
    from mistralai.client.sdkconfiguration import SERVERS

    assert set(agent.MISTRAL_SERVERS_VALIDES) == set(SERVERS)


def test_get_mistral_construit_un_client_vers_l_ue(monkeypatch):
    """Résolution purement locale (get_server_details) : aucune requête émise."""
    client = agent.get_mistral()
    url, _ = client.sdk_configuration.get_server_details()
    assert url == "https://api.eu.mistral.ai"


@pytest.mark.parametrize(
    "serveur, attendu",
    [
        ("eu", "https://api.eu.mistral.ai"),
        ("us", "https://api.us.mistral.ai"),
        ("global", "https://api.mistral.ai"),
    ],
)
def test_get_mistral_suit_mistral_server(monkeypatch, serveur, attendu):
    monkeypatch.setattr(agent, "MISTRAL_SERVER", serveur)
    client = agent.get_mistral()
    assert client.sdk_configuration.get_server_details()[0] == attendu


def test_get_mistral_transmet_server_non_vide_et_jamais_server_url(monkeypatch):
    import mistralai.client

    recus = {}

    class _Enregistreur:
        def __init__(self, **kwargs):
            recus.update(kwargs)

    monkeypatch.setattr(mistralai.client, "Mistral", _Enregistreur)
    agent.get_mistral()

    assert recus["server"] == "eu"
    assert recus["server"].strip() != ""
    # server_url l'emporterait sur server (sdkconfiguration.py:52-53).
    assert "server_url" not in recus


def test_mistral_endpoint_host_derive_du_sdk(monkeypatch):
    assert agent.mistral_endpoint_host() == "api.eu.mistral.ai"
    monkeypatch.setattr(agent, "MISTRAL_SERVER", "global")
    assert agent.mistral_endpoint_host() == "api.mistral.ai"

"""
Tests du juge LLM (lot C) avec un FAUX client injecté : aucun réseau, aucun
appel Google. tests/conftest.py fait en plus échouer toute création d'un vrai
client google-genai.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import judge_upload_answers as juge

HERE = Path(__file__).resolve().parent
NOW = lambda: datetime(2026, 10, 20, 9, 30, tzinfo=timezone.utc)  # noqa: E731
ENV_OK = {
    "GOOGLE_CLOUD_PROJECT": "projet-factice-tests",
    "JUDGE_LOCATION": "eu",
    "JUDGE_MODEL": "gemini-3.8-flash",
    "JUDGE_ALLOW_REAL": "1",
}
INTERDITS = re.compile(r"claude|anthropic|sonnet|mistral|pi[èe]g|\bP(?:0[1-9]|10)\b", re.IGNORECASE)


# ─────────────────────────────────────────────
# Faux client
# ─────────────────────────────────────────────


def sortie_json(c1="oui", c2="oui", c3="sans objet", justification="Passage cité, article 4.1."):
    return json.dumps({c: {"justification": justification, "verdict": v} for c, v in (("C1", c1), ("C2", c2), ("C3", c3))},
                      ensure_ascii=False)


def reponse(texte, fin="STOP", tin=6000, tout=400, tthink=900):
    return SimpleNamespace(
        text=texte,
        usage_metadata=SimpleNamespace(prompt_token_count=tin, candidates_token_count=tout, thoughts_token_count=tthink),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=fin))],
        model_version="gemini-3.8-flash-faux",
        response_id="faux-id",
    )


class FauxClient:
    def __init__(self, fabrique=None, base_url="https://aiplatform.eu.rep.googleapis.com/"):
        self.appels = []
        self._fabrique = fabrique or (lambda n, contents: reponse(sortie_json()))
        self.models = SimpleNamespace(generate_content=self._generate)
        self._api_client = SimpleNamespace(_http_options=SimpleNamespace(base_url=base_url))

    def _generate(self, *, model, contents, config):
        self.appels.append({"model": model, "contents": contents, "config": config})
        r = self._fabrique(len(self.appels), contents)
        if isinstance(r, BaseException):
            raise r
        return r


class Fabrique:
    """client_factory injectable : compte les créations de client."""

    def __init__(self, client=None):
        self.client = client or FauxClient()
        self.creations = []

    def __call__(self, project, location):
        self.creations.append((project, location))
        return self.client


def lancer(argv, tmp_path, environ=None, fabrique=None, now=NOW):
    sorties = []
    fabrique = fabrique or Fabrique()
    code = juge.main(
        argv + ["--out-dir", str(tmp_path)],
        environ=ENV_OK if environ is None else environ,
        out=sorties.append,
        client_factory=fabrique,
        now=now,
        attente=lambda s: None,
    )
    return code, "\n".join(sorties), fabrique


def resultats(tmp_path):
    fichiers = sorted(tmp_path.glob("judge_upload_*.json"))
    assert len(fichiers) == 1
    return json.loads(fichiers[0].read_text(encoding="utf-8")), fichiers[0].with_suffix(".md").read_text(encoding="utf-8")


# ─────────────────────────────────────────────
# Garde-fous : refus sans aucun appel
# ─────────────────────────────────────────────


@pytest.mark.parametrize("manquante", juge.REQUIRED_ENV)
def test_variable_manquante_refus_sans_appel(tmp_path, manquante):
    env = {k: v for k, v in ENV_OK.items() if k != manquante}
    code, sortie, fab = lancer(["--yes"], tmp_path, environ=env)
    assert code == juge.EXIT_REFUSED
    assert manquante in sortie and fab.creations == [] and not list(tmp_path.iterdir())


def test_aucune_valeur_par_defaut_pour_le_modele(tmp_path):
    env = {k: v for k, v in ENV_OK.items() if k != "JUDGE_MODEL"}
    code, _, fab = lancer([], tmp_path, environ=env)
    assert code == juge.EXIT_REFUSED and fab.creations == []


@pytest.mark.parametrize("location", ["global", "europe-west2", "europe-west6", "us", "us-central1", ""])
def test_region_hors_ue_refusee(tmp_path, location):
    code, _, fab = lancer(["--yes"], tmp_path, environ={**ENV_OK, "JUDGE_LOCATION": location})
    assert code == juge.EXIT_REFUSED and fab.creations == []


def test_modele_sans_tarif_refuse(tmp_path):
    code, sortie, fab = lancer(["--yes"], tmp_path, environ={**ENV_OK, "JUDGE_MODEL": "gemini-3.5-flash"})
    assert code == juge.EXIT_REFUSED and "aucun tarif" in sortie and fab.creations == []


def test_tarif_promotionnel_expire_refuse(tmp_path):
    code, sortie, fab = lancer(["--yes"], tmp_path, now=lambda: datetime(2027, 1, 2, tzinfo=timezone.utc))
    assert code == juge.EXIT_REFUSED and "31/12/2026" in sortie and fab.creations == []


@pytest.mark.parametrize("cle", juge.CLES_API_INTERDITES)
def test_cle_api_google_refusee_sans_afficher_sa_valeur(tmp_path, cle):
    valeur = "valeur-secrete-de-test-123456"
    code, sortie, fab = lancer(["--yes"], tmp_path, environ={**ENV_OK, cle: valeur})
    assert code == juge.EXIT_REFUSED and cle in sortie and valeur not in sortie and fab.creations == []


@pytest.mark.parametrize("argv, env, manque", [
    ([], ENV_OK, "--yes"),
    (["--yes"], {k: v for k, v in ENV_OK.items() if k != "JUDGE_ALLOW_REAL"}, "JUDGE_ALLOW_REAL=1"),
    (["--yes"], {**ENV_OK, "JUDGE_ALLOW_REAL": "oui"}, "JUDGE_ALLOW_REAL=1"),
    (["--smoke"], {k: v for k, v in ENV_OK.items() if k != "JUDGE_ALLOW_REAL"}, "--yes et JUDGE_ALLOW_REAL=1"),
])
def test_appel_reel_exige_yes_et_allow_real(tmp_path, argv, env, manque):
    code, sortie, fab = lancer(argv, tmp_path, environ=env)
    assert code == juge.EXIT_REFUSED
    assert "Aucun appel effectué" in sortie and manque in sortie
    assert fab.creations == [] and fab.client.appels == [] and not list(tmp_path.iterdir())


def test_resume_affiche_le_cout_estime_avant_tout_appel(tmp_path):
    code, sortie, _ = lancer([], tmp_path)
    assert code == juge.EXIT_REFUSED
    assert "Coût estimé (BORNE HAUTE" in sortie and "50 jugement(s)" in sortie
    assert "Plafond dur d'appels : 60" in sortie
    assert "traité dans l'UE (multi-région eu, pays non précisé)" in sortie
    assert "projet-factice-tests" not in sortie


def test_vrai_client_bloque_par_le_conftest(tmp_path):
    """Même avec --yes et JUDGE_ALLOW_REAL=1, la vraie fabrique échoue pendant les tests."""
    with pytest.raises(RuntimeError, match="interdite pendant les tests"):
        juge.main(["--yes", "--smoke", "--out-dir", str(tmp_path)], environ=ENV_OK, out=lambda s: None, now=NOW)
    with pytest.raises(RuntimeError, match="interdite pendant les tests"):
        juge.creer_client_vertex("projet-factice-tests", "eu")


def test_endpoint_inattendu_refuse_sans_appel(tmp_path):
    fab = Fabrique(FauxClient(base_url="https://aiplatform.googleapis.com/"))
    code, sortie, _ = lancer(["--yes"], tmp_path, fabrique=fab)
    assert code == juge.EXIT_REFUSED and "endpoint" in sortie and fab.client.appels == []


@pytest.mark.parametrize("location, url", [
    ("eu", "https://aiplatform.eu.rep.googleapis.com/"),
    ("europe-west9", "https://europe-west9-aiplatform.googleapis.com/"),
])
def test_endpoint_attendu(location, url):
    assert juge.endpoint_attendu(location) == url


# ─────────────────────────────────────────────
# Run complet, fumée, répétitions, plafond
# ─────────────────────────────────────────────


def test_run_complet_cinquante_jugements_et_schema_des_resultats(tmp_path):
    code, _, fab = lancer(["--yes"], tmp_path)
    assert code == juge.EXIT_OK
    assert fab.creations == [("projet-factice-tests", "eu")]
    assert len(fab.client.appels) == 50
    rapport, md = resultats(tmp_path)
    h = rapport["en_tete"]
    assert h["modele"] == "gemini-3.8-flash" and h["location"] == "eu"
    assert h["endpoint"] == "https://aiplatform.eu.rep.googleapis.com/"
    assert h["empreintes"]["prompt_juge.md"] == juge.sha256_fichier(juge.PROMPT)
    assert set(h["git"]) == {"commit", "arbre_modifie"}
    assert h["temperature"] == 0.0 and h["thinking_level"] == "MEDIUM"
    assert len(rapport["correspondance"]) == 50 and len(rapport["jugements"]) == 50
    assert sum(1 for c in rapport["correspondance"] if c["source"] == "piege") == 10
    for j in rapport["jugements"]:
        assert set(j["verdicts"]) == {"C1", "C2", "C3"} and j["erreur"] is None
        assert j["tokens_in"] == 6000 and j["tokens_out"] == 400 and j["tokens_raisonnement"] == 900
    attendu = 50 * (6000 * 0.825 + 1300 * 4.125) / 1_000_000
    assert rapport["resume"]["cout_usd"] == pytest.approx(attendu, abs=1e-4)
    assert rapport["resume"]["appels_effectues"] == 50
    # Rapport .md : formulations exigées, jamais un pays, jamais le projet.
    assert "traité dans l'UE (multi-région eu, pays non précisé)" in md
    assert "tarif promotionnel jusqu'au 31/12/2026" in md and "aucune date de retrait publiée" in md
    assert juge.TARIF_SOURCE in md and "consultée le 13/10/2026" in md
    for pays in ("France", "Belgique", "Pays-Bas", "Allemagne", "Paris"):
        assert pays not in md
    contenu = md + json.dumps(rapport)
    assert "projet-factice-tests" not in contenu


def test_fichier_de_fumee_marque(tmp_path):
    lancer(["--yes", "--smoke"], tmp_path)
    rapport, _ = resultats(tmp_path)
    assert rapport["en_tete"]["mode"] == "fumée"
    # Le fichier de fumée est marqué comme tel.
    assert list(tmp_path.glob("judge_upload_*_smoke.json"))


def test_fumee_un_seul_appel(tmp_path):
    code, _, fab = lancer(["--yes", "--smoke"], tmp_path)
    assert code == juge.EXIT_OK and len(fab.client.appels) == 1
    config = fab.client.appels[0]["config"]
    assert config["temperature"] == 0.0
    assert config["response_mime_type"] == "application/json"
    assert config["thinking_config"] == {"thinking_level": "MEDIUM"}
    assert config["system_instruction"] == juge.charger_prompt_systeme()


@pytest.mark.parametrize("cible, source", [("P03", "piege"), ("Q01:mistral", "origine")])
def test_fumee_element_choisi(tmp_path, cible, source):
    code, _, fab = lancer(["--yes", "--smoke", cible], tmp_path)
    assert code == juge.EXIT_OK and len(fab.client.appels) == 1
    rapport, _ = resultats(tmp_path)
    assert rapport["jugements"][0]["source"] == source


def test_fumee_element_invalide_refuse(tmp_path):
    code, _, fab = lancer(["--yes", "--smoke", "Q99:anthropic"], tmp_path)
    assert code == juge.EXIT_REFUSED and fab.creations == []


def test_repetitions_2_cent_jugements(tmp_path):
    code, sortie, fab = lancer(["--yes", "--repetitions", "2"], tmp_path)
    assert code == juge.EXIT_OK and len(fab.client.appels) == 100
    assert "Plafond dur d'appels : 110" in sortie
    rapport, _ = resultats(tmp_path)
    assert sorted({j["repetition"] for j in rapport["jugements"]}) == [1, 2]


def test_repetitions_au_dela_de_2_refusees():
    with pytest.raises(SystemExit):
        juge.parse_args(["--repetitions", "3"])


@pytest.mark.parametrize("n, plafond", [(1, 2), (2, 4), (50, 60), (100, 110)])
def test_plafond(n, plafond):
    assert juge.plafond_appels(n) == plafond


def test_plafond_dur_jamais_depasse(tmp_path):
    """Un juge en panne permanente : chaque élément réessaie une fois, le plafond coupe à 60."""
    fab = Fabrique(FauxClient(lambda n, c: ConnectionError("panne")))
    code, _, _ = lancer(["--yes"], tmp_path, fabrique=fab)
    assert code == juge.EXIT_OK
    assert len(fab.client.appels) == 60
    rapport, _ = resultats(tmp_path)
    types_erreur = [j["erreur"]["type"] for j in rapport["jugements"]]
    assert len(types_erreur) == 50 and all(j["verdicts"] is None for j in rapport["jugements"])
    assert "erreur_technique" in types_erreur and "plafond_atteint" in types_erreur
    assert rapport["resume"]["appels_effectues"] == 60


def test_erreur_technique_reessayee_une_seule_fois():
    client = FauxClient(lambda n, c: ConnectionError("x") if n == 1 else reponse(sortie_json()))
    res = juge.juger(client, "m", {}, "msg", juge.Budget(10), juge.TARIFS_JUGE["gemini-3.8-flash"], attente=lambda s: None)
    assert len(client.appels) == 2 and res["verdicts"] and res["erreur"] is None
    assert res["tentatives"][0] == {"erreur_technique": "ConnectionError", "code": None}


def test_interruption_conserve_les_resultats(tmp_path):
    fab = Fabrique(FauxClient(lambda n, c: KeyboardInterrupt() if n == 3 else reponse(sortie_json())))
    code, _, _ = lancer(["--yes"], tmp_path, fabrique=fab)
    assert code == juge.EXIT_INTERRUPTED
    rapport, md = resultats(tmp_path)
    assert rapport["interrompu"] is True and len(rapport["jugements"]) == 2
    assert "RUN INTERROMPU" in md


def test_fichiers_en_creation_exclusive(tmp_path):
    lancer(["--yes", "--smoke"], tmp_path)
    lancer(["--yes", "--smoke"], tmp_path)
    noms = sorted(p.name for p in tmp_path.glob("judge_upload_*.json"))
    assert noms == ["judge_upload_20261020_093000_smoke.json", "judge_upload_20261020_093000_smoke_2.json"]


def test_secrets_masques_dans_les_resultats(tmp_path):
    # Valeur factice construite à l'exécution : aucune chaîne ressemblant à une clé dans le dépôt.
    secret = "-".join(["valeur", "factice", "masquee", "0123456789"])
    fab = Fabrique(FauxClient(lambda n, c: reponse(sortie_json(justification=f"écho {secret}"))))
    code, _, _ = lancer(["--yes", "--smoke"], tmp_path, environ={**ENV_OK, "ANTHROPIC_API_KEY": secret}, fabrique=fab)
    assert code == juge.EXIT_OK
    contenu = "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    assert secret not in contenu and "[REDACTED]" in contenu


# ─────────────────────────────────────────────
# Sortie du juge : schéma et erreurs
# ─────────────────────────────────────────────


def test_schema_justification_avant_verdict():
    s = juge.schema_sortie()
    assert s["property_ordering"] == ["C1", "C2", "C3"] and s["required"] == ["C1", "C2", "C3"]
    for c in ("C1", "C2", "C3"):
        assert s["properties"][c]["property_ordering"] == ["justification", "verdict"]
    assert s["properties"]["C1"]["properties"]["verdict"]["enum"] == ["oui", "non"]
    assert s["properties"]["C2"]["properties"]["verdict"]["enum"] == ["oui", "non", "sans objet"]
    assert s["properties"]["C3"]["properties"]["verdict"]["enum"] == ["oui", "non", "sans objet"]


def test_config_acceptee_par_le_sdk_si_installe():
    """Validation locale du dict de configuration par le SDK (aucun réseau)."""
    types = pytest.importorskip("google.genai.types")
    config = types.GenerateContentConfig(**juge.config_appel("système"))
    assert config.response_schema is not None and config.temperature == 0.0


@pytest.mark.parametrize("texte, motif", [
    (None, "réponse vide"),
    ("   ", "réponse vide"),
    ("pas du json", "JSON invalide"),
    ("[1, 2]", "objet attendu"),
    (json.dumps({"C1": {"justification": "x", "verdict": "oui"}, "C2": {"justification": "x", "verdict": "oui"}}), "C3 manquant"),
    (sortie_json(c1="sans objet"), "C1 : verdict"),
    (sortie_json(c2="Oui"), "C2 : verdict"),
    (sortie_json(c3="peut-être"), "C3 : verdict"),
    (sortie_json(justification="  "), "justification manquante"),
    (json.dumps({c: {"verdict": "oui"} for c in ("C1", "C2", "C3")}), "justification manquante"),
])
def test_sortie_invalide_jamais_convertie(texte, motif):
    with pytest.raises(juge.ReponseInvalide, match=motif):
        juge.valider_sortie(texte)


@pytest.mark.parametrize("rep, motif", [
    (reponse("pas du json"), "JSON invalide"),
    (reponse(sortie_json(c2="Non")), "C2 : verdict"),
    (reponse(sortie_json(), fin="MAX_TOKENS"), "arrêt anormal : MAX_TOKENS"),
    (reponse(sortie_json(), fin="SAFETY"), "arrêt anormal : SAFETY"),
])
def test_reponse_invalide_enregistree_comme_erreur(rep, motif):
    client = FauxClient(lambda n, c: rep)
    res = juge.juger(client, "m", {}, "msg", juge.Budget(10), juge.TARIFS_JUGE["gemini-3.8-flash"], attente=lambda s: None)
    assert len(client.appels) == 1, "une réponse invalide n'est pas réessayée"
    assert res["verdicts"] is None and res["verdict_global"] is None
    assert res["erreur"]["type"] == "reponse_invalide" and motif in res["erreur"]["motif"]
    assert res["erreur"]["texte_brut"] == rep.text


def test_reponse_vide_reessayee_une_fois_puis_erreur():
    client = FauxClient(lambda n, c: reponse(""))
    res = juge.juger(client, "m", {}, "msg", juge.Budget(10), juge.TARIFS_JUGE["gemini-3.8-flash"], attente=lambda s: None)
    assert len(client.appels) == 2 and res["erreur"]["motif"] == "réponse vide"


def test_tokens_inconnus_cout_non_invente():
    rep = reponse(sortie_json())
    rep.usage_metadata = None
    res = juge.juger(FauxClient(lambda n, c: rep), "m", {}, "msg", juge.Budget(10), juge.TARIFS_JUGE["gemini-3.8-flash"])
    assert res["verdicts"] and res["cout_usd"] is None


@pytest.mark.parametrize("verdicts, attendu", [
    ({"C1": "oui", "C2": "oui", "C3": "sans objet"}, "validée"),
    ({"C1": "oui", "C2": "sans objet", "C3": "sans objet"}, "validée"),
    ({"C1": "non", "C2": "oui", "C3": "sans objet"}, "rejetée"),
    ({"C1": "oui", "C2": "sans objet", "C3": "non"}, "rejetée"),
])
def test_verdict_global(verdicts, attendu):
    assert juge.verdict_global({c: {"verdict": v} for c, v in verdicts.items()}) == attendu


# ─────────────────────────────────────────────
# Aveuglement
# ─────────────────────────────────────────────


def _prompts():
    run = json.loads(juge.REFERENCE_RUN.read_text(encoding="utf-8"))
    pieges = json.loads(juge.PIEGES.read_text(encoding="utf-8"))["pieges"]
    elements = juge.charger_elements(run, pieges)
    contrats = {e.doc: juge.rendu_contrat(json.loads((juge.CONTRATS_DIR / f"{e.doc}.json").read_text(encoding="utf-8")))
                for e in elements}
    return elements, {e.id_interne: juge.message_juge(contrats[e.doc], e.question, e.reponse) for e in elements}


def test_aveuglement_des_cinquante_prompts():
    elements, messages = _prompts()
    assert len(messages) == 50
    systeme = juge.charger_prompt_systeme()
    for texte in [systeme, *messages.values()]:
        assert not INTERDITS.search(texte), INTERDITS.search(texte).group(0)
        assert not re.search(r"\bQ\d{2}\b", texte), "aucun code de question dans le prompt"
    assert juge.controle_aveuglement(systeme, messages) == []


def test_aveuglement_des_prompts_reellement_envoyes(tmp_path):
    _, _, fab = lancer(["--yes"], tmp_path)
    for appel in fab.client.appels:
        envoye = appel["contents"] + appel["config"]["system_instruction"]
        assert not INTERDITS.search(envoye)


def test_controle_aveuglement_refuse_le_lancement(tmp_path, monkeypatch):
    monkeypatch.setattr(juge, "message_juge", lambda c, q, r: "Réponse rédigée par Claude.")
    code, sortie, fab = lancer(["--yes"], tmp_path)
    assert code == juge.EXIT_REFUSED and "aveuglement" in sortie and fab.creations == []


def test_ordre_melange_deterministe_et_ids_neutres():
    elements, _ = _prompts()
    elements_bis, _ = _prompts()
    assert [e.correspondance() for e in elements] == [e.correspondance() for e in elements_bis]
    assert [e.id_interne for e in elements] == [f"J{i:02d}" for i in range(1, 51)]
    positions = [i for i, e in enumerate(elements) if e.source == "piege"]
    assert positions != list(range(40, 50)), "les pièges ne sont pas regroupés à la fin"


def test_prompt_egal_a_la_grille_aux_substitutions_declarees_pres():
    texte = juge.PROMPT.read_text(encoding="utf-8")
    entete, corps = texte.split(juge.MARQUEUR_PROMPT)
    substitutions = json.loads(re.search(r"```json\n(.*?)\n```", entete, re.S).group(1))
    grille = juge.GRILLE.read_text(encoding="utf-8")
    section = grille[grille.index("## Ce qui est jugé"):grille.index("## Calibration : copies piégées")].rstrip("\n")
    for s in substitutions:
        assert section.count(s["avant"]) == 1, s["avant"][:40]
        assert s["motif"]
        section = section.replace(s["avant"], s["apres"])
    assert section in corps
    assert "Calibration" not in corps


def test_le_juge_ne_lit_jamais_la_fiche_humaine():
    assert "annotation_humaine" not in (HERE / "judge_upload_answers.py").read_text(encoding="utf-8")

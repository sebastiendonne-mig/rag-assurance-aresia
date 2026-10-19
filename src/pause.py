"""
Pause d'inactivité (lot « pause d'inactivité », étape P1).

Pourquoi : une connexion WebSocket ouverte garde l'instance Cloud Run active, donc facturée
(doc Cloud Run « Using WebSockets » : une instance qui a une connexion WebSocket ouverte est
considérée active). Le client Streamlit se reconnecte à l'infini : aucune solution côté serveur
ne suffit. Seule voie : un script dans la page qui, après inactivité, quitte la page vers une
page de pause statique. Quitter la page ferme la connexion et supprime le code de reconnexion.

Ce module ne fait que lire la configuration et produire le bloc HTML/JS ; app.py le rend avec
st.html(..., unsafe_allow_javascript=True) (non placé dans une iframe en 1.58), uniquement une
fois l'agent prêt.

Bibliothèque standard uniquement : importé en tête de app.py, sans coût.
"""
import logging
import os

# Logger enfant de "streamlit_app" : ses avertissements remontent au handler stdout ajouté par
# agent.configure_stdout_logging() (donc à Cloud Logging) et au fichier de debug (root).
log = logging.getLogger("streamlit_app.pause")

# Chemin servi par server.enableStaticServing en Streamlit 1.58 (serveur Starlette, seul serveur
# de cette version) : route "app/static/{path:path}" (streamlit/web/server/starlette/
# starlette_routes.py, _ROUTE_APP_STATIC) sur le dossier static/ voisin de app.py
# (streamlit/file_util.py, APP_STATIC_FOLDER_NAME). Type servi : mimetypes, donc text/html.
CHEMIN_PAUSE = "/app/static/pause.html"

# Fréquence de vérification. Le temps écoulé est toujours mesuré avec Date.now() : dans un onglet
# caché, le navigateur ralentit les minuteries, mais l'heure reste juste.
VERIFICATION_MS = 15_000

_VRAI = {"true", "1", "yes", "on", "oui"}
_FAUX = {"false", "0", "no", "off", "non"}

# Un avertissement par (variable, valeur) et par processus : app.py relit la configuration à
# chaque exécution du script, il ne faut pas répéter la même ligne à chaque rerun.
_deja_signales: set[tuple[str, str]] = set()


def _avertir(nom: str, valeur: str, message: str) -> None:
    if (nom, valeur) in _deja_signales:
        return
    _deja_signales.add((nom, valeur))
    log.warning(message)


def lire_duree(nom: str, defaut: int, maximum: int = 60) -> int:
    """
    Durée en minutes lue dans la variable d'environnement `nom` : entier entre 1 et `maximum`.
    Absente ou vide : `defaut`, sans avertissement. Invalide : `defaut`, avec un avertissement
    (la valeur reçue n'est pas un secret, elle est citée tronquée pour le diagnostic).
    """
    brut = os.environ.get(nom, "").strip()
    if not brut:
        return defaut
    # isascii() d'abord : str.isdigit() accepte aussi « ² », que int() refuse.
    if brut.isascii() and brut.isdigit() and 1 <= int(brut) <= maximum:
        return int(brut)
    _avertir(
        nom,
        brut,
        f"PAUSE config invalide {nom}={brut[:20]!r} (entier de 1 à {maximum} attendu) : "
        f"valeur par défaut {defaut} utilisée",
    )
    return defaut


def pause_active() -> bool:
    """
    Interrupteur de secours PAUSE_ACTIVE (défaut : vrai). Faux : aucun script injecté.
    Valeur non reconnue : vrai, avec un avertissement.
    """
    brut = os.environ.get("PAUSE_ACTIVE", "").strip()
    if not brut:
        return True
    if brut.lower() in _VRAI:
        return True
    if brut.lower() in _FAUX:
        return False
    _avertir(
        "PAUSE_ACTIVE",
        brut,
        f"PAUSE config invalide PAUSE_ACTIVE={brut[:20]!r} (true/false attendu) : pause activée",
    )
    return True


def lire_config() -> dict[str, int]:
    """Les trois durées validées, en minutes."""
    return {
        "inactivite_min": lire_duree("PAUSE_INACTIVITE_MIN", 6),
        "masque_min": lire_duree("PAUSE_ONGLET_MASQUE_MIN", 3),
        "occupe_max_min": lire_duree("PAUSE_OCCUPE_MAX_MIN", 20, maximum=120),
    }


# Gabarit constant : seuls les jetons __...__ sont remplacés, par des entiers validés ou "0"/"1".
# Aucune donnée utilisateur n'entre jamais dans ce bloc.
#
# - Verrou window.__tkPause : Streamlit réinjecte le script quand le contenu du bloc change
#   (data-busy), il ne faut qu'un seul jeu d'écouteurs et une seule minuterie. Le premier script
#   installé reste donc seul actif : il relit data-busy DANS LE DOM à chaque vérification, jamais
#   une valeur capturée à l'installation.
# - Occupé = data-busy différent de "0", ou bloc absent (préchauffage après un redémarrage du
#   serveur, onglet resté ouvert). Pas de pause pendant un calcul : la réponse serait perdue.
#   Quand l'état repasse à libre, le compteur d'inactivité repart de zéro.
# - Plafond d'occupation : un état occupé qui dure plus de __OCCUPE_MAX_MS__ ms d'affilée est
#   ignoré (bloc définitivement absent après une exception, busy_task bloqué par un bug) : sans
#   lui, plus aucune pause ne serait possible.
# - Limite connue : détection par sondage. Une période occupée plus courte que l'intervalle de
#   vérification peut passer inaperçue ; le clic qui l'a déclenchée a de toute façon remis le
#   compteur à zéro.
_GABARIT = """<div id="tk-pause" data-busy="__OCCUPE__" hidden></div>
<script>
(function () {
  if (window.__tkPause) { return; }
  window.__tkPause = true;
  var INACTIVITE_MS = __INACTIVITE_MS__;
  var MASQUE_MS = __MASQUE_MS__;
  var OCCUPE_MAX_MS = __OCCUPE_MAX_MS__;
  var CIBLE = "__CIBLE__";
  var derniere = Date.now();
  var masqueDepuis = document.hidden ? Date.now() : null;
  var occupeDepuis = null;
  var etaitOccupe = false;
  var parti = false;
  function activite() { derniere = Date.now(); }
  ["mousemove", "pointerdown", "keydown", "wheel", "scroll", "touchstart"].forEach(function (type) {
    window.addEventListener(type, activite, { capture: true, passive: true });
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { masqueDepuis = Date.now(); }
    else { masqueDepuis = null; activite(); }
  });
  function occupe() {
    var bloc = document.getElementById("tk-pause");
    return !bloc || bloc.getAttribute("data-busy") !== "0";
  }
  function verifier() {
    if (parti) { return; }
    var maintenant = Date.now();
    if (occupe()) {
      if (occupeDepuis === null) { occupeDepuis = maintenant; }
      if (maintenant - occupeDepuis < OCCUPE_MAX_MS) { etaitOccupe = true; return; }
    } else {
      occupeDepuis = null;
      if (etaitOccupe) {
        etaitOccupe = false;
        derniere = maintenant;
        if (masqueDepuis !== null) { masqueDepuis = maintenant; }
        return;
      }
    }
    var inactif = maintenant - derniere >= INACTIVITE_MS;
    var masque = masqueDepuis !== null && maintenant - masqueDepuis >= MASQUE_MS;
    if (inactif || masque) {
      parti = true;
      window.location.replace(CIBLE);
    }
  }
  setInterval(verifier, __VERIFICATION_MS__);
})();
</script>"""


def bloc_html(occupe: bool, inactivite_min: int, masque_min: int, occupe_max_min: int) -> str:
    """Bloc HTML/JS de la pause. `occupe` : un calcul est en cours (busy_task posée)."""
    remplacements = {
        "__OCCUPE__": "1" if occupe else "0",
        "__INACTIVITE_MS__": str(int(inactivite_min) * 60_000),
        "__MASQUE_MS__": str(int(masque_min) * 60_000),
        "__OCCUPE_MAX_MS__": str(int(occupe_max_min) * 60_000),
        "__VERIFICATION_MS__": str(VERIFICATION_MS),
        "__CIBLE__": CHEMIN_PAUSE,
    }
    bloc = _GABARIT
    for jeton, valeur in remplacements.items():
        bloc = bloc.replace(jeton, valeur)
    return bloc

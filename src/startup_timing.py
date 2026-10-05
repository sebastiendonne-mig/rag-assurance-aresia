"""
Repères de démarrage horodatés (sous-lot 2.5, instrumentation).

Mesure où passent les secondes du démarrage à froid : une ligne courte sur
stdout (flush, comme log_memory), donc visible dans Cloud Logging, au préfixe
commun « startup-timing ».

Ne change aucun comportement de l'application : aucun import lourd, aucune
exception propagée, aucun contenu utilisateur (uniquement un nom d'étape fixe
et un temps). Ce module doit rester importable en tête de app.py, avant tout
import de bibliothèque tierce : il n'utilise que la bibliothèque standard.

Horloge de référence : l'import de ce module (donc le début de la première
exécution du script app.py). L'âge du processus à ce moment — le temps déjà
écoulé depuis son lancement — est ajouté à la première ligne, pour situer cette
référence dans la chronologie de l'instance.

Une seule émission par étape et par processus : Streamlit ré-exécute app.py à
chaque interaction, mais ce module, mis en cache dans sys.modules, ne l'est pas.
"""
import threading
import time

PREFIX = "startup-timing"

_T0 = time.perf_counter()
_lock = threading.Lock()
_emises: set[str] = set()


def _age_processus_s() -> str:
    """Secondes écoulées depuis la création du processus, ou « n/a » si indisponible."""
    try:
        import os

        import psutil

        return f"{time.time() - psutil.Process(os.getpid()).create_time():.3f}s"
    except Exception:
        return "n/a"


def mark(etape: str) -> None:
    """Émet « startup-timing <étape> +<secondes>s » une seule fois par étape et par processus."""
    try:
        with _lock:
            if etape in _emises:
                return
            premiere = not _emises
            _emises.add(etape)
        ligne = f"{PREFIX} {etape} +{time.perf_counter() - _T0:.3f}s"
        if premiere:
            ligne += f" (age_processus={_age_processus_s()})"
        print(ligne, flush=True)
    except Exception:
        # Un repère ne doit jamais faire échouer le démarrage.
        pass

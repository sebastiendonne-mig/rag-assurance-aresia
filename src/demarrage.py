"""
État de démarrage du processus (sous-lot 2.5, option 1 : page affichée avant
l'import de l'agent).

Indique si l'agent (imports lourds + préparation de _warm_up dans app.py) est
prêt dans CE processus. Sert à app.py pour décider, à chaque exécution du
script, s'il affiche d'abord une page sans agent (instance froide) ou la page
complète.

Pourquoi un module à part : les variables de app.py sont recréées à chaque
exécution du script, alors qu'un module importé reste en mémoire (sys.modules)
pour toute la vie du processus. On ne peut pas non plus tester
`"agent" in sys.modules` : Python y inscrit le module dès le DÉBUT de son
import, avant qu'il soit complet.

Bibliothèque standard uniquement (rien, en fait) : ce module doit rester
importable en tête de app.py, sans coût.
"""

_pret = False


def est_pret() -> bool:
    """Vrai une fois l'agent importé et préparé dans ce processus."""
    return _pret


def marquer_pret() -> None:
    """À appeler APRÈS le retour de _warm_up() (jamais dans son corps mis en cache)."""
    global _pret
    _pret = True

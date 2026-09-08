"""Journal d'execution horodate de l'agent (palier 4).

Chaque evenement important (question recue, appel d'outil, panne de
ressource, arret/redemarrage) est ecrit sur une ligne, avec un timestamp UTC
a la milliseconde. On utilise logging.FileHandler plutot qu'un print/open
maison car il flush (ecrit reellement sur le disque) apres chaque ligne :
meme si le processus s'arrete juste apres, la ligne est deja lisible.
"""
import logging
import os
import time
from pathlib import Path

DEFAULT_LOG_PATH = "data/execution.log"

_logger = logging.getLogger("sosie.agent")
_logger.setLevel(logging.INFO)
_logger.propagate = False


def _build_formatter() -> logging.Formatter:
    # Format texte simple, lisible directement avec `tail -f`, sans JSON.
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03dZ %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime  # Horodatage en UTC, jamais en heure locale.
    return formatter


def configure_execution_log(path: str | None = None) -> None:
    # Redirige le journal vers le fichier donne (ou EXECUTION_LOG_PATH, ou le
    # chemin par defaut). A appeler une fois par app Flask creee.
    log_path = path or os.environ.get("EXECUTION_LOG_PATH", DEFAULT_LOG_PATH)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    for handler in list(_logger.handlers):
        _logger.removeHandler(handler)
        handler.close()

    formatter = _build_formatter()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)

    # Egalement sur la sortie standard, pour un `docker compose logs` en direct.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    # Ecrit une ligne de journal : un nom d'evenement, puis des cle=valeur.
    detail = " ".join(f"{key}={value!r}" for key, value in fields.items())
    _logger.log(level, f"{event} {detail}".rstrip())


# En test, pytest ferme sa capture de sys.stderr entre chaque test, alors que
# le handler console garde une reference a l'ancienne. Le tout dernier appel
# (a la fermeture de l'interpreteur) tombe donc sur un flux deja ferme.
# raiseExceptions=False est le mecanisme documente du module logging pour ce
# cas precis : ignorer silencieusement un echec d'ecriture de log plutot que
# d'afficher une trace d'erreur qui n'a rien a voir avec le code applicatif.
logging.raiseExceptions = False

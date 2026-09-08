"""Journal d'execution horodate de l'agent (palier 4).

Chaque evenement important (question recue, appel d'outil, panne de
ressource, arret/redemarrage) est ecrit sur une ligne, avec un timestamp UTC
a la milliseconde. On utilise logging.FileHandler plutot qu'un print/open
maison car il flush (ecrit reellement sur le disque) apres chaque ligne :
meme si le processus s'arrete juste apres, la ligne est deja lisible.
"""
import logging
import os
import re
import time
from collections import deque
from pathlib import Path

DEFAULT_LOG_PATH = "data/execution.log"

_logger = logging.getLogger("sosie.agent")
_logger.setLevel(logging.INFO)
_logger.propagate = False

MAX_LOG_LINE_CHARS = 4000
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z) "
    r"(?P<level>[A-Z]+)\s+(?P<message>.*)$"
)
SENSITIVE_NAME_RE = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(anthropic_api_key|api[_-]?key|authorization|password|secret|"
    r"access[_-]?token|refresh[_-]?token)(\s*[:=]\s*)([^\s,;]+)"
)
BEARER_RE = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
ANTHROPIC_KEY_RE = re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b")


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


def redact_sensitive_text(text: str) -> str:
    """Retire les secrets connus et les formats de credentials usuels."""
    redacted = str(text)
    for name, value in os.environ.items():
        if SENSITIVE_NAME_RE.search(name) and value:
            redacted = redacted.replace(value, "[REDACTED]")
    redacted = SENSITIVE_ASSIGNMENT_RE.sub(r"\1\2[REDACTED]", redacted)
    redacted = BEARER_RE.sub("Bearer [REDACTED]", redacted)
    return ANTHROPIC_KEY_RE.sub("[REDACTED]", redacted)


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    # Ecrit une ligne de journal : un nom d'evenement, puis des cle=valeur.
    details = []
    for key, value in fields.items():
        safe_value = "[REDACTED]" if SENSITIVE_NAME_RE.search(key) else value
        details.append(f"{key}={safe_value!r}")
    detail = " ".join(details)
    _logger.log(level, redact_sensitive_text(f"{event} {detail}".rstrip()))


def read_execution_log(path: str, limit: int = 50) -> list[dict[str, str | None]]:
    """Lit les dernieres lignes en memoire bornee et les structure pour l'API."""
    if not 1 <= limit <= 50:
        raise ValueError("La limite doit être comprise entre 1 et 50.")

    try:
        with Path(path).open(encoding="utf-8", errors="replace") as log_file:
            lines = deque(log_file, maxlen=limit)
    except FileNotFoundError:
        return []

    entries = []
    for raw_line in lines:
        safe_line = redact_sensitive_text(raw_line.rstrip("\r\n"))
        if len(safe_line) > MAX_LOG_LINE_CHARS:
            safe_line = safe_line[:MAX_LOG_LINE_CHARS] + "…"
        match = LOG_LINE_RE.match(safe_line)
        if match:
            entries.append(match.groupdict())
        else:
            entries.append({
                "timestamp": None,
                "level": "UNKNOWN",
                "message": safe_line,
            })
    return entries


# En test, pytest ferme sa capture de sys.stderr entre chaque test, alors que
# le handler console garde une reference a l'ancienne. Le tout dernier appel
# (a la fermeture de l'interpreteur) tombe donc sur un flux deja ferme.
# raiseExceptions=False est le mecanisme documente du module logging pour ce
# cas precis : ignorer silencieusement un echec d'ecriture de log plutot que
# d'afficher une trace d'erreur qui n'a rien a voir avec le code applicatif.
logging.raiseExceptions = False

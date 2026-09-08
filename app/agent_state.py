"""Etat et generations d'execution de l'agent (palier 4).

Couper l'agent ne tue pas le processus. Le compteur de generation permet en
plus d'invalider les requetes deja lancees : un redemarrage ne peut donc pas
reactiver une execution appartenant a une ancienne generation.
"""
import logging
import threading
from dataclasses import dataclass
from typing import Callable, TypeVar

from app.execution_log import log_event

_lock = threading.Lock()
_state = {"status": "running", "reason": None}
_generation = 0
_next_execution_id = 1

Result = TypeVar("Result")


@dataclass(frozen=True)
class ExecutionToken:
    """Identite immuable attribuee atomiquement a une execution acceptee."""

    execution_id: int
    generation: int


class ExecutionCancelled(RuntimeError):
    """L'execution n'appartient plus a la generation active."""


def get_agent_state() -> dict:
    # Renvoie une copie de l'etat courant (statut + raison de l'arret).
    with _lock:
        return dict(_state)


def is_agent_running() -> bool:
    # Vrai si l'agent accepte actuellement de nouvelles questions.
    with _lock:
        return _state["status"] == "running"


def begin_agent_execution() -> ExecutionToken | None:
    """Accepte atomiquement une execution et capture sa generation."""
    global _next_execution_id
    with _lock:
        if _state["status"] != "running":
            return None
        token = ExecutionToken(_next_execution_id, _generation)
        _next_execution_id += 1
        return token


def is_execution_active(token: ExecutionToken) -> bool:
    """Vrai uniquement si le jeton appartient toujours a l'etat actif."""
    with _lock:
        return (
            _state["status"] == "running"
            and token.generation == _generation
        )


def ensure_execution_active(token: ExecutionToken) -> None:
    """Interrompt le flot courant si un STOP a invalide son jeton."""
    if not is_execution_active(token):
        raise ExecutionCancelled


def run_if_execution_active(token: ExecutionToken, callback: Callable[[], Result]) -> Result:
    """Execute une etape finale sous le meme verrou que STOP.

    Cette section critique ferme la course entre le dernier controle et le
    commit SQLite : soit le commit finit avant STOP, soit STOP gagne et le
    callback de persistance n'est jamais lance.
    """
    with _lock:
        if _state["status"] != "running" or token.generation != _generation:
            raise ExecutionCancelled
        return callback()


def stop_agent(reason: str = "arret manuel") -> None:
    # Passe l'agent a l'arret et journalise l'instant exact de la coupure.
    global _generation
    with _lock:
        _generation += 1
        _state["status"] = "stopped"
        _state["reason"] = reason
        generation = _generation
    log_event(
        "agent_stopped",
        level=logging.WARNING,
        reason=reason,
        generation=generation,
    )


def start_agent() -> None:
    # Relance l'agent proprement et journalise le redemarrage.
    with _lock:
        _state["status"] = "running"
        _state["reason"] = None
    log_event("agent_started")

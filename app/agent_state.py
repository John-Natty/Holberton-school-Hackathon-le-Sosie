"""Etat running / stopped de l'agent (palier 4).

Un interrupteur simple, en memoire, protege par un verrou (thread-safe).
Couper l'agent ne tue pas le processus : /chat et /chat/stream continuent
de repondre, mais refusent proprement tant que l'etat est "stopped".
"""
import logging
import threading

from app.execution_log import log_event

_lock = threading.Lock()
_state = {"status": "running", "reason": None}


def get_agent_state() -> dict:
    # Renvoie une copie de l'etat courant (statut + raison de l'arret).
    with _lock:
        return dict(_state)


def is_agent_running() -> bool:
    # Vrai si l'agent accepte actuellement de nouvelles questions.
    with _lock:
        return _state["status"] == "running"


def stop_agent(reason: str = "arret manuel") -> None:
    # Passe l'agent a l'arret et journalise l'instant exact de la coupure.
    with _lock:
        _state["status"] = "stopped"
        _state["reason"] = reason
    log_event("agent_stopped", level=logging.WARNING, reason=reason)


def start_agent() -> None:
    # Relance l'agent proprement et journalise le redemarrage.
    with _lock:
        _state["status"] = "running"
        _state["reason"] = None
    log_event("agent_started")

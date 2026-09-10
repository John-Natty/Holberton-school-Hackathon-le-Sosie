"""Contrat commun des contrôles locaux, sans coût ni appel à un service."""
from dataclasses import dataclass

from app.model_pricing import RequestUsage
from app.response_status import with_response_status


class ScreeningUnavailable(Exception):
    """Un contrôle incomplet interdit de poursuivre vers Claude ou SQLite."""


@dataclass(frozen=True)
class LocalRefusal:
    status: str
    message: str

    def payload(self):
        # Zéro consommation est certain ici, même pour un modèle sans tarif :
        # aucun fournisseur n'a été appelé. Ne change pas le calcul des usages API.
        info = RequestUsage("").snapshot()
        info["cost"] = {"amount": "0.00000000", "currency": "USD"}
        return {"status": self.status, "message": self.message,
                "request_info": with_response_status(info, self.status)}

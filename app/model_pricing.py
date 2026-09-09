"""Tarifs USD/MTok et consommation Anthropic d'une seule requête utilisateur.

Tarifs standard vérifiés le 2026-09-09 :
https://platform.claude.com/docs/en/about-claude/pricing
Aucun accès réseau, comptage de texte ou calcul financier en float ici.
"""
from dataclasses import dataclass, field
from decimal import Decimal, localcontext


MODEL_PRICING = {
    "claude-sonnet-5": {
        "input_tokens": Decimal("2"),
        "output_tokens": Decimal("10"),
        "cache_read_input_tokens": Decimal("0.20"),
        "cache_creation_5m_input_tokens": Decimal("2.50"),
        "cache_creation_1h_input_tokens": Decimal("4"),
    },
    "claude-opus-5": {
        "input_tokens": Decimal("5"),
        "output_tokens": Decimal("25"),
        "cache_read_input_tokens": Decimal("0.50"),
        "cache_creation_5m_input_tokens": Decimal("6.25"),
        "cache_creation_1h_input_tokens": Decimal("10"),
    },
    "claude-haiku-4-5": {
        "input_tokens": Decimal("1"),
        "output_tokens": Decimal("5"),
        "cache_read_input_tokens": Decimal("0.10"),
        "cache_creation_5m_input_tokens": Decimal("1.25"),
        "cache_creation_1h_input_tokens": Decimal("2"),
    },
}
TOKEN_FIELDS = tuple(MODEL_PRICING["claude-sonnet-5"])


def _field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _count(value):
    return value if type(value) is int and value >= 0 else None


@dataclass
class RequestUsage:
    model: str
    model_calls: int = 0
    tool_calls: int = 0
    totals: dict = field(default_factory=lambda: dict.fromkeys(TOKEN_FIELDS, 0))
    usage_complete: bool = True
    known_fields: set = field(default_factory=set)

    def record(self, usage):
        """Additionne uniquement les compteurs retournés par l'API, une fois par réponse."""
        counts = {name: _count(_field(usage, name)) for name in ("input_tokens", "output_tokens")}
        read = _field(usage, "cache_read_input_tokens")
        counts["cache_read_input_tokens"] = _count(0 if read is None else read)
        creation = _field(usage, "cache_creation_input_tokens")
        creation = _count(0 if creation is None else creation)
        detail = _field(usage, "cache_creation")
        if detail is None:
            # Sans ventilation, le contrat Anthropic utilise le TTL par défaut de 5 minutes.
            counts["cache_creation_5m_input_tokens"] = creation
            counts["cache_creation_1h_input_tokens"] = 0
        else:
            counts["cache_creation_5m_input_tokens"] = _count(_field(detail, "ephemeral_5m_input_tokens"))
            counts["cache_creation_1h_input_tokens"] = _count(_field(detail, "ephemeral_1h_input_tokens"))
            parts = [counts["cache_creation_5m_input_tokens"], counts["cache_creation_1h_input_tokens"]]
            if None not in parts and creation is not None and _field(usage, "cache_creation_input_tokens") is not None:
                if sum(parts) != creation:
                    self.usage_complete = False
        for name, count in counts.items():
            if count is None:
                self.usage_complete = False
            else:
                self.totals[name] += count
                self.known_fields.add(name)

    def snapshot(self):
        """Liste fermée de métriques publiques ; aucune réponse brute ni donnée privée."""
        metrics = {**self.totals, "model_calls": self.model_calls, "tool_calls": self.tool_calls,
                   "calls": self.model_calls + self.tool_calls}
        if not self.usage_complete:
            for name in TOKEN_FIELDS:
                if name not in self.known_fields:
                    metrics[name] = None
        metrics["total_tokens"] = (metrics["input_tokens"] + metrics["output_tokens"]
                                   if metrics["input_tokens"] is not None and metrics["output_tokens"] is not None else None)
        writes = [metrics["cache_creation_5m_input_tokens"], metrics["cache_creation_1h_input_tokens"]]
        metrics["cache_creation_input_tokens"] = sum(writes) if None not in writes else None
        rates = MODEL_PRICING.get(self.model)
        cost = None
        if rates is not None and self.usage_complete:
            # Enough precision even for large integer counters; eight decimals are exact for these rates.
            with localcontext() as context:
                context.prec = max(28, max(len(str(value)) for value in self.totals.values()) + 16)
                amount = sum((Decimal(self.totals[name]) * rate for name, rate in rates.items()), Decimal("0")) / Decimal("1000000")
                cost = {"amount": format(amount, ".8f"), "currency": "USD"}
        return {"metrics": metrics, "cost": cost, "usage_complete": self.usage_complete}

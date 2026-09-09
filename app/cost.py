"""Estimation du cout d'un appel Claude (palier 5, bonus).

Ce n'est jamais une facture reelle Anthropic : juste une estimation a partir
des tarifs publics et des tokens effectivement consommes pour la requete.
"""

# Dollars US pour 1 million de tokens (tarifs publics au moment de l'ecriture).
# Cle de repli si le modele reellement utilise n'est pas dans la table.
PRICING_PER_MILLION_TOKENS = {
    "claude-sonnet-5": {"input": 2.0, "output": 10.0},
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}
DEFAULT_PRICING = PRICING_PER_MILLION_TOKENS["claude-sonnet-5"]


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    # Calcule un cout approximatif en dollars a partir des tokens et du tarif du modele.
    pricing = PRICING_PER_MILLION_TOKENS.get(model, DEFAULT_PRICING)
    return (
        input_tokens * pricing["input"] / 1_000_000
        + output_tokens * pricing["output"] / 1_000_000
    )

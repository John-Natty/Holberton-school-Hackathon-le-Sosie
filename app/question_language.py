"""Détection locale Lingua, sans lexique de marques ni liste de mots français."""
import re
import unicodedata
from functools import lru_cache

from app.local_screening import ScreeningUnavailable

FRENCH_ONLY_MESSAGE = (
    "Je peux uniquement traiter les questions en français. "
    "Merci de reformuler votre demande en français."
)
# Une faible preuve ne suffit pas à rejeter un nom propre ou un terme technique.
MIN_CONFIDENCE = 0.15
MIN_RELATIVE_MARGIN = 0.50


@lru_cache(maxsize=1)
def _detector():
    from lingua import LanguageDetectorBuilder
    return LanguageDetectorBuilder.from_all_spoken_languages().build()


def foreign_language(text):
    """Renvoie un code ISO seulement si la question est clairement étrangère.

    Une expression ambiguë reste traitable (ex. « Total ? », « Netflix »).
    Les très courts textes latins ne constituent pas une preuve de langue ;
    les scripts non latins passent quand même dans le détecteur.
    """
    try:
        from lingua import Language
        text = unicodedata.normalize("NFKC", text)
        letters = [char for char in text if char.isalpha()]
        words = re.findall(r"[^\W\d_]+", text, re.UNICODE)
        if not letters:
            return None
        if len(words) < 4 and all("LATIN" in unicodedata.name(c, "") for c in letters):
            return None
        scores = _detector().compute_language_confidence_values(text)
        if not scores or scores[0].language == Language.FRENCH:
            return None
        winner = scores[0]
        # Les probabilités sont réparties entre 74 langues. La séparation
        # relative des deux premières est plus utile qu'un seuil absolu élevé.
        runner_up = scores[1].value if len(scores) > 1 else 0.0
        if (winner.value >= MIN_CONFIDENCE
                and (winner.value - runner_up) / winner.value >= MIN_RELATIVE_MARGIN):
            return winner.language.iso_code_639_1.name.lower()
        return None
    except Exception:
        raise ScreeningUnavailable("Détection locale de langue indisponible.") from None

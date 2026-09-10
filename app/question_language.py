"""Détection locale par petits profils de n-grammes, sans moteur ML natif."""
import re
import unicodedata
from threading import Lock

from app.local_screening import ScreeningUnavailable

FRENCH_ONLY_MESSAGE = (
    "Je peux uniquement traiter les questions en français. "
    "Merci de reformuler votre demande en français."
)
MIN_CONFIDENCE = 0.90
MIN_MARGIN = 0.50
MIN_LONG_WORDS = 6
MIN_LONG_LETTERS = 25
MIN_LONG_CONFIDENCE = 0.50
MAX_FRENCH_CONFIDENCE = 0.10
_factory = None
_factory_lock = Lock()


def _foreign_script(letters):
    """Repère une écriture majoritairement incompatible avec le français.

    Un nom cité dans une phrase française ne suffit pas. Les lettres latines
    accentuées comptent comme françaises possibles. Les codes identifient ici
    une famille d'écriture (ru pour le cyrillique), pas toutes ses langues.
    """
    counts = {"ru": 0, "ar": 0, "zh": 0, "ja": 0}
    for char in letters:
        name = unicodedata.name(char, "")
        if "CYRILLIC" in name:
            counts["ru"] += 1
        elif "ARABIC" in name:
            counts["ar"] += 1
        elif "HIRAGANA" in name or "KATAKANA" in name:
            counts["ja"] += 1
        elif name.startswith(("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH")):
            counts["zh"] += 1
    if sum(counts.values()) * 2 <= len(letters):
        return None
    # Les kanji japonais sont aussi des Han ; les kana lèvent cette ambiguïté.
    if counts["ja"] and counts["ja"] + counts["zh"] >= max(counts["ru"], counts["ar"]):
        return "ja"
    return max(counts, key=counts.get)


def _detector():
    """Un seul jeu de profils par worker, un détecteur privé par requête.

    Le verrou empêche deux threads Gunicorn de charger les profils en même
    temps. Aucun texte utilisateur n'est conservé dans la fabrique partagée.
    """
    global _factory
    with _factory_lock:
        if _factory is None:
            from langdetect.detector_factory import DetectorFactory, PROFILES_DIRECTORY

            factory = DetectorFactory()
            factory.set_seed(0)
            factory.load_profile(PROFILES_DIRECTORY)
            # Ne publier qu'une fabrique initialisée ; un chargement en échec
            # ne doit pas laisser d'état partiel partagé entre les requêtes.
            if "fr" not in factory.get_lang_list():
                raise RuntimeError("Profils de langue incomplets.")
            _factory = factory
        # create() construit un nouvel objet avec son propre texte et PRNG.
        # Seuls les profils, ensuite utilisés en lecture, sont partagés.
        return _factory.create()


def foreign_language(text):
    """Refuse seulement une langue étrangère identifiée avec forte confiance.

    Les expressions latines très courtes restent ambiguës : noms propres,
    marques et termes techniques ne constituent pas une preuve de langue.
    None signifie français ou langue non déterminée ; une absence d'indices
    linguistiques n'est pas une panne du détecteur.
    """
    try:
        text = unicodedata.normalize("NFKC", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Cf")
        letters = [char for char in text if char.isalpha()]
        words = re.findall(r"[^\W\d_]+", text, re.UNICODE)
        if not letters:
            return None
        script_language = _foreign_script(letters)
        if script_language is not None:
            return script_language
        if len(words) < 4 and all("LATIN" in unicodedata.name(c, "") for c in letters):
            return None
        from langdetect.lang_detect_exception import ErrorCode, LangDetectException

        detector = _detector()
        try:
            detector.append(text)
            scores = detector.get_probabilities()
        except LangDetectException as exc:
            # Le nettoyage interne peut retirer URL/e-mails, ou ne trouver
            # aucun n-gramme connu dans un texte pourtant valide pour la route.
            if exc.code in (ErrorCode.NoTextError, ErrorCode.CantDetectError):
                return None
            raise
        if not scores or scores[0].lang in {"fr", "unknown"}:
            return None
        winner = scores[0]
        runner_up = scores[1].prob if len(scores) > 1 else 0.0
        if winner.prob >= MIN_CONFIDENCE and winner.prob - runner_up >= MIN_MARGIN:
            return winner.lang.split("-")[0]  # zh-cn/zh-tw -> zh pour le journal.
        # Sur une phrase longue, une hésitation italien/portugais reste une
        # preuve de non-français si le français n'est pas un candidat crédible.
        # langdetect ne renvoie que les candidats dont la probabilité > 0,1.
        french = next((score.prob for score in scores if score.lang == "fr"), 0.0)
        if (len(words) >= MIN_LONG_WORDS and len(letters) >= MIN_LONG_LETTERS
                and winner.prob >= MIN_LONG_CONFIDENCE
                and french <= MAX_FRENCH_CONFIDENCE):
            return winner.lang.split("-")[0]
        return None
    except Exception:
        raise ScreeningUnavailable("Détection locale de langue indisponible.") from None

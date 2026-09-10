"""Modération d'intention locale, indépendante de l'agent et de ses prompts.

Un modèle NLI multilingue compare le texte à des descriptions d'intentions,
y compris légitimes. Aucun mot du texte ne route vers une catégorie ; aucune
instruction de l'utilisateur n'est exécutée par ce classificateur non génératif.
Les poids sont provisionnés à l'installation, jamais téléchargés en requête.
"""
import hashlib
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock

from app.local_screening import ScreeningUnavailable

MODEL_REPOSITORY = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
MODEL_REVISION = "8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c"
MODEL_FILES = {
    "model.onnx": ("onnx/model_quantized.onnx", "27c39e884c14b03cf46cfc5485971b6db70ff330220d93dfe729c63fde43af0e"),
    "tokenizer.json": ("tokenizer.json", "3aca3ce69a0a35aeb144a52c4f1d41c4246b8785f8f398315cc8fb6b24057810"),
}
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / ".local_models" / "moderation"
QUESTION_REFUSAL = "Cette demande ne peut pas être traitée."
FILE_REFUSAL = "Ce fichier contient un contenu qui ne peut pas être traité."
SELF_HARM_REFUSAL = (
    "Je suis désolé que vous traversiez une situation difficile. "
    "Je ne peux pas aider à vous faire du mal. Si vous êtes en danger immédiat, "
    "contactez les services d'urgence locaux et une personne de confiance qui peut rester avec vous."
)

# Des descriptions complètes d'intentions, pas une liste de mots interdits.
HARMFUL_INTENTS = {
    "child_exploitation": (
        "Je veux obtenir du contenu sexuel impliquant des mineurs.",
        "Je veux produire du contenu sexuel impliquant des enfants.",
        "Je veux exploiter sexuellement un enfant.",
        "Je veux solliciter sexuellement un mineur.",
        "Je veux partager du contenu pédopornographique.",
        "Je veux manipuler un enfant pour obtenir des faveurs sexuelles.",
    ),
    "illegal_weapons": (
        "Je veux acheter des armes illégalement.",
        "Je veux vendre illégalement des armes ou des munitions.",
        "Je veux organiser un trafic d'armes.",
        "Je veux transporter clandestinement des armes.",
        "Je veux fabriquer des armes illégales.",
        "Je veux obtenir illégalement des composants d'armes réglementés.",
        "Je veux dissimuler des armes pour éviter les contrôles.",
    ),
    "drug_trafficking": (
        "Je veux organiser un trafic de drogues.",
        "Je veux vendre des drogues illégales.",
        "Je veux acheter de la cocaïne.",
        "Je veux acheter des drogues illégales.",
        "Je veux produire des drogues illégales.",
        "Je veux dissimuler de la drogue lors d'un transport.",
    ),
    "explosives": (
        "Je veux fabriquer une bombe.",
        "Je veux fabriquer un explosif.",
        "Je veux vendre illégalement des explosifs.",
        "Je veux transporter clandestinement des explosifs.",
        "Je veux blesser des personnes avec des produits chimiques.",
    ),
    "violent_crime": (
        "Je veux organiser un meurtre.",
        "Je veux enlever une personne.",
        "Je veux torturer quelqu'un.",
        "Je veux organiser une attaque violente.",
        "Je veux cacher les preuves d'un crime violent.",
        "Je veux saboter une infrastructure pour blesser des personnes.",
    ),
    "human_trafficking": (
        "Je veux organiser la traite d'êtres humains.",
        "Je veux vendre des personnes.",
        "Je veux organiser du travail forcé.",
        "Je veux exploiter des personnes vulnérables.",
        "Je veux dissimuler des victimes de la traite humaine.",
    ),
    "financial_crime": (
        "Je veux blanchir de l'argent criminel.",
        "Je veux organiser une escroquerie.",
        "Je veux fabriquer de faux justificatifs.",
        "Je veux contourner les contrôles KYC.",
        "Je veux dissimuler des revenus pour frauder le fisc.",
        "Je veux usurper l'identité de quelqu'un.",
        "Je veux organiser une fraude fiscale.",
    ),
    "malicious_cyber": (
        "Je veux attaquer une entreprise avec un ransomware.",
        "Je veux voler des identifiants par phishing.",
        "Je veux diffuser un logiciel malveillant.",
        "Je veux pirater une cible sans autorisation.",
        "Je veux voler des cookies de session.",
        "Je veux exfiltrer des données volées.",
        "Je veux effacer les traces de mon intrusion illégale.",
        "Je veux maintenir un accès malveillant à un système.",
    ),
    "extortion": (
        "Je veux faire chanter quelqu'un.",
        "Je veux extorquer de l'argent à une victime.",
        "Je veux organiser une campagne de harcèlement.",
        "Je veux publier les données privées de quelqu'un pour lui nuire.",
    ),
    "terrorism": (
        "Je veux préparer un attentat.",
        "Je veux recruter pour une organisation terroriste.",
        "Je veux financer une organisation terroriste.",
        "Je veux organiser une cellule terroriste.",
        "Je veux produire de la propagande pour recruter des terroristes.",
    ),
    "contraband": (
        "Je veux vendre des marchandises volées.",
        "Je veux vendre illégalement des médicaments contrôlés.",
        "Je veux vendre de faux papiers.",
        "Je veux organiser un trafic d'espèces protégées.",
        "Je veux organiser un commerce de contrebande.",
    ),
    "self_harm": (
        "Je veux une méthode pour me suicider.",
        "Je veux des instructions pour me mutiler.",
    ),
}
LEGITIMATE_INTENTS = (
    "Je veux connaître le montant de mes dépenses.",
    "Il s'agit d'un achat ordinaire et légal.",
    "Je cherche à prévenir un danger.",
    "Je veux protéger les victimes.",
    "Je demande quelles sont les sanctions prévues par la loi.",
    "Je veux étudier l'histoire.",
    "Je fais de la cybersécurité défensive.",
    "Je fais un exercice dans un laboratoire ou un CTF autorisé.",
    "Je cherche un traitement pour une addiction.",
    "Je cherche de l'aide pour prévenir le suicide.",
)
MIN_HARM_SCORE = 0.60
MIN_INTENT_MARGIN = 0.10
MAX_WINDOW_CHARS = 700
WINDOW_OVERLAP = 180
MAX_SCREENING_SECONDS = 12
_inference_lock = Lock()


class ContentBlocked(Exception):
    """Le contenu ne doit être ni persisté ni recopié dans une erreur."""


@dataclass(frozen=True)
class ModerationDecision:
    blocked: bool = False
    category: str | None = None

    @property
    def message(self):
        return SELF_HARM_REFUSAL if self.category == "self_harm" else QUESTION_REFUSAL


def model_directory():
    return Path(os.environ.get("MODERATION_MODEL_DIR") or DEFAULT_MODEL_DIR)


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _LocalClassifier:
    def __init__(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        directory = model_directory()
        for name, (_, digest) in MODEL_FILES.items():
            if file_digest(directory / name) != digest:
                raise ValueError("invalid local model")
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        # Pas de troncature silencieuse : un fragment trop long est refusé.
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(directory / "model.onnx"), options,
                                            providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}

    def scores(self, text):
        import numpy as np

        hypotheses = tuple(h for group in HARMFUL_INTENTS.values() for h in group) + LEGITIMATE_INTENTS
        scores = []
        for start in range(0, len(hypotheses), 8):
            encoded = self.tokenizer.encode_batch([(text, h) for h in hypotheses[start:start + 8]])
            if any(len(item.ids) > 512 for item in encoded):
                raise ScreeningUnavailable("Texte trop dense pour le contrôle local.")
            inputs = {
                "input_ids": np.array([item.ids for item in encoded], dtype=np.int64),
                "attention_mask": np.array([item.attention_mask for item in encoded], dtype=np.int64),
                "token_type_ids": np.array([item.type_ids for item in encoded], dtype=np.int64),
            }
            logits = self.session.run(None, {k: v for k, v in inputs.items() if k in self.input_names})[0]
            if logits.shape != (len(encoded), 3) or not np.isfinite(logits).all():
                raise ScreeningUnavailable("Classification locale inexploitable.")
            probabilities = np.exp(logits - logits.max(axis=1, keepdims=True))
            probabilities /= probabilities.sum(axis=1, keepdims=True)
            # Contrat du modèle figé : entailment=0, neutral=1, contradiction=2.
            scores.extend(probabilities[:, 0].tolist())
        grouped = []
        offset = 0
        for group in HARMFUL_INTENTS.values():
            grouped.append(max(scores[offset:offset + len(group)]))
            offset += len(group)
        return grouped + scores[offset:]


@lru_cache(maxsize=1)
def _classifier():
    return _LocalClassifier()


def _windows(text):
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    # Fenêtres recouvrantes pour ne pas ignorer une instruction après un préambule.
    for start in range(0, len(text), MAX_WINDOW_CHARS - WINDOW_OVERLAP):
        yield text[start:start + MAX_WINDOW_CHARS]
        if start + MAX_WINDOW_CHARS >= len(text):
            break
    # Le contexte légitime d'une phrase n'exempte pas une autre demande autonome.
    if len(text) <= MAX_WINDOW_CHARS:
        parts = re.split(r"(?<=[.!?;])\s+|\n+", text)
        if len([part for part in parts if part.strip()]) > 1:
            yield from (part.strip() for part in parts if part.strip())


def moderate_texts(texts, *, budget_seconds=None):
    """Contrôle tout le contenu en mémoire ; ne conserve aucun texte en cache/log.

    Le budget local et le verrou bornent la charge CPU. Un contrôle incomplet
    provoque une erreur technique : jamais une autorisation par défaut.
    """
    deadline = time.monotonic() + (MAX_SCREENING_SECONDS if budget_seconds is None else budget_seconds)
    if not _inference_lock.acquire(timeout=2):
        raise ScreeningUnavailable("Modération locale occupée.")
    try:
        classifier = _classifier()
        for text in texts:
            for fragment in _windows(text):
                if time.monotonic() >= deadline:
                    raise ScreeningUnavailable("Contrôle local non terminé.")
                scores = classifier.scores(fragment)
                if time.monotonic() >= deadline:
                    raise ScreeningUnavailable("Contrôle local non terminé.")
                harmful = scores[:len(HARMFUL_INTENTS)]
                legitimate = max(scores[len(HARMFUL_INTENTS):])
                best = max(range(len(harmful)), key=harmful.__getitem__)
                self_harm = tuple(HARMFUL_INTENTS).index("self_harm")
                if (harmful[self_harm] >= MIN_HARM_SCORE
                        and harmful[self_harm] - legitimate >= MIN_INTENT_MARGIN):
                    return ModerationDecision(True, "self_harm")
                if harmful[best] >= MIN_HARM_SCORE and harmful[best] - legitimate >= MIN_INTENT_MARGIN:
                    return ModerationDecision(True, tuple(HARMFUL_INTENTS)[best])
        return ModerationDecision()
    except ScreeningUnavailable:
        raise
    except Exception:
        raise ScreeningUnavailable("Modération locale indisponible.") from None
    finally:
        _inference_lock.release()

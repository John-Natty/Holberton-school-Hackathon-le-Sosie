"""Modération locale déterministe, sans modèle, téléchargement ou moteur ML.

Les règles associent une action et un objet dangereux dans la même proposition,
avec portée limitée des négations et des contextes légitimes. Elles couvrent des
formulations explicites françaises et quelques équivalents anglais, sans prétendre
comprendre toutes les paraphrases, langues ou obfuscations. Aucun texte n'est mis
en cache, journalisé ou transmis à un service par ce module.
"""
import re
import time
import unicodedata
from dataclasses import dataclass

from app.local_screening import ScreeningUnavailable

QUESTION_REFUSAL = "Cette demande ne peut pas être traitée."
FILE_REFUSAL = "Ce fichier contient un contenu qui ne peut pas être traité."
SELF_HARM_REFUSAL = (
    "Je suis désolé que vous traversiez une situation difficile. "
    "Je ne peux pas aider à vous faire du mal. Si vous êtes en danger immédiat, "
    "contactez les services d'urgence locaux et une personne de confiance qui peut rester avec vous."
)
MAX_WINDOW_CHARS = 700
WINDOW_OVERLAP = 350
MAX_SCREENING_SECONDS = 12
MAX_RELATION_CHARS = 240


class ContentBlocked(Exception):
    """Le contenu ne doit être ni persisté ni recopié dans une erreur."""


@dataclass(frozen=True)
class ModerationDecision:
    blocked: bool = False
    category: str | None = None

    @property
    def message(self):
        return SELF_HARM_REFUSAL if self.category == "self_harm" else QUESTION_REFUSAL


def _pattern(expression):
    return re.compile(r"\b(?:" + expression + r")\b")


# Actions verbales et nominales : un CSV peut porter « achat ... » sans phrase.
_OPERATIONS = (
    r"achet\w*|achat\w*|vend\w*|vente\w*|fabriqu\w*|fabrication\w*|"
    r"produi\w*|product\w*|cre(?:e|ation)\w*|organis\w*|prepar\w*|"
    r"planifi\w*|financ\w*|recrut\w*|transport\w*|livr\w*|distribu\w*|"
    r"diffus\w*|partag\w*|trouv\w*|obten\w*|obti\w*|acquer\w*|acquisition\w*|"
    r"optimis\w*|dissimul\w*|cach\w*|contourn\w*|deploy\w*|deploi\w*|"
    r"buy|sell|make|build|create|produce|organize|recruit|finance|"
    r"trafic\w*|traffic\w*|smuggl\w*|hide|deploy|share|find|obtain"
)
_ILLICIT = (
    r"illegal\w*|illicit\w*|clandestin\w*|sans autorisation|sans permis|"
    r"sans licence|sans controle\w*|eviter les controles|contourn\w*|"
    r"trafic\w*|contrebande|criminel\w*|illegal\w*|unlicensed|smuggl\w*"
)


@dataclass(frozen=True)
class _Rule:
    category: str
    action: re.Pattern
    target: re.Pattern
    qualifier: re.Pattern | None = None


def _rule(category, target, action=_OPERATIONS, qualifier=None):
    return _Rule(category, _pattern(action), _pattern(target),
                 _pattern(qualifier) if qualifier else None)


# Pas de refus sur le thème seul : chaque règle exige une relation d'action.
_RULES = (
    _rule("self_harm", r"me suicid\w*|me mutil\w*|me tuer|suicid\w*|automutil\w*|"
          r"kill myself|self.harm", r"methode\w*|instruction\w*|comment|dose\w*|"
          r"moyen\w*|plan\w*|veux|vais|want|how|method\w*"),
    _rule("child_exploitation", r"sexuel\w*|pornograph\w*|pedopornograph\w*|"
          r"sexual\w*|porn\w*|grooming", qualifier=r"mineur\w*|enfant\w*|"
          r"adolescent\w*|pedo\w*|minor\w*|child\w*|underage",
          action=_OPERATIONS + r"|exploit\w*|sollicit\w*|sexualis\w*|manipul\w*|groom\w*"),
    _rule("illegal_weapons", r"arme\w*|munition\w*|fusil\w*|pistolet\w*|"
          r"weapon\w*|gun\w*|ammunition", qualifier=_ILLICIT),
    _rule("drug_trafficking", r"cocaine|heroine|methamphetamine\w*|"
          r"stupefiant\w*|drogue\w*|narcotic\w*|illegal drugs?",
          action=_OPERATIONS + r"|fournisseur\w*|rendement\w*|fixer les prix"),
    _rule("explosives", r"bombe\w*|explosif\w*|bomb\w*|explosive\w*"),
    _rule("explosives", r"produit\w* chimique\w*|chemical\w*",
          action=r"bless\w*|tuer|empoisonn\w*|kill|injur\w*"),
    _rule("violent_crime", r"meurtre\w*|enlevement\w*|sequestration\w*|torture\w*|"
          r"crime\w* violent\w*|agression\w*|attaque\w*|murder|kidnap\w*",
          action=_OPERATIONS + r"|commet\w*|execut\w*|cible\w*"),
    _rule("violent_crime", r"voisin\w*|personne\w*|victime\w*|quelqu.un|"
          r"collegue\w*|people|someone|victim\w*",
          action=r"tuer|assassin\w*|enlever|tortur\w*|sequestr\w*|kill|kidnap\w*"),
    _rule("violent_crime", r"infrastructure\w*|hopital\w*|reseau electrique",
          action=r"sabot\w*|detruire"),
    _rule("human_trafficking", r"traite|trafic d.etres humains|travail force|"
          r"esclavage|victimes de la traite|human trafficking|forced labo[u]?r"),
    _rule("human_trafficking", r"personne\w*|etre\w* humain\w*|victime\w*|"
          r"refugie\w*|people|humans?", action=r"vendre|achat|acheter|sell|buy"),
    _rule("human_trafficking", r"personnes vulnerables|victimes de la traite",
          action=r"exploit\w*|dissimul\w*|cach\w*"),
    _rule("financial_crime", r"argent|revenu\w*|fonds|money|proceeds",
          action=r"blanchi\w*|launder\w*"),
    _rule("financial_crime", r"escroquer\w*|fraude\w*|faux justificatif\w*|"
          r"faux document\w*|fausse\w* facture\w*|prete.noms?|"
          r"fake (?:documents?|invoices?)|fraud\w*"),
    _rule("financial_crime", r"kyc|controle\w* banca\w*|identite|revenu\w* criminel\w*|"
          r"fisc|impots?", action=r"contourn\w*|usurp\w*|dissimul\w*|fraud\w*|bypass"),
    _rule("malicious_cyber", r"ransomware\w*|malware\w*|logiciel\w* malveillant\w*|"
          r"rancongiciel\w*|phishing", action=_OPERATIONS + r"|attaqu\w*|vol\w*"),
    _rule("malicious_cyber", r"identifiant\w*|mot\w* de passe|cookie\w*|session\w*|"
          r"donnee\w*|credentials?|password\w*|data",
          action=r"vol\w*|derob\w*|exfiltr\w*|steal|exfiltrat\w*"),
    _rule("malicious_cyber", r"cible|entreprise|serveur|compte|systeme|reseau|target|server",
          action=r"pirat\w*|intrusion|contourn\w*|sabot\w*|hack\w*",
          qualifier=r"sans autorisation|non autorise\w*|malveillant\w*|unauthorized"),
    _rule("malicious_cyber", r"traces?\b.{0,60}\bintrusion|acces malveillant|"
          r"persistance malveillante", action=r"effac\w*|cach\w*|maintenir|install\w*"),
    _rule("extortion", r"chantage|faire chanter|extorsion|extorqu\w*|harcelement|"
          r"blackmail|extort\w*", action=_OPERATIONS + r"|faire chanter|extorqu\w*|blackmail|extort\w*"),
    _rule("extortion", r"donnee\w* privee\w*|adresse personnelle|doxxing",
          qualifier=r"nuire|menac\w*|harcel\w*|victime|harm|threat\w*"),
    _rule("terrorism", r"attentat\w*|terroriste\w*|terrorist\w*"),
    _rule("contraband", r"marchandise\w* volee\w*|bien\w* vole\w*|faux papiers|"
          r"espece\w* protege\w*|contrebande|stolen goods|forged papers"),
    _rule("contraband", r"medicament\w* controle\w*|bien\w* reglemente\w*|"
          r"controlled medicines?", qualifier=_ILLICIT),
)

# Un support documentaire doit être relié à son sujet, pas simplement cité.
_STUDY_EXPRESSION = (
    r"(?:livres?|ouvrages?|manuels?|cours|documentations?|etudes?|formations?|articles?|rapports?)"
    r"\s+(?:sur|contre|concernant|du|des|de|d')"
)
_STUDY_OBJECT = _pattern(_STUDY_EXPRESSION)
_NOUN_INTRODUCTION = re.compile(r"\b(?:de|des|du|un|une|le|la|les|ces|mes|nos|vos)\s+$|\bd'$")
_WEAPON_PURCHASE = _pattern(r"achet\w*|achat\w*|acquer\w*|acquisition\w*|buy")
_LAWFUL_PURCHASE = _pattern(r"legalement|avec (?:un |une )?(?:permis|licence|autorisation)")

# Ces contextes doivent gouverner l'action, et non apparaître n'importe où.
_LEGITIMATE = _pattern(
    r"prevenir|prevention|empecher|proteger|protection|detecter|detection|"
    r"lutter contre|sanctions?|peines?|loi|droit|juridique|histoire|historique|etudier|"
    r"journalistique|academique|traitement\w*|addiction\w*|reduction des risques|"
    + _STUDY_EXPRESSION + "|"
    r"prevent\w*|protect\w*|history|penalties|treatment"
)
_DETAILS = _pattern(
    r"(?:donne\w*|fourni\w*|detaille\w*|montre\w*|explique\w*|apprends|give|show)"
    r".{0,65}\b(?:comment|methode\w*|etape\w*|instruction\w*|recette\w*|code|plan|how)|"
    r"(?:je veux|aide.moi a|help me|i want to)"
)
_AUTHORIZED = _pattern(r"ctf|laboratoire autorise|lab autorise|pentest autorise|"
                       r"test autorise|audit autorise|authorized lab|authorized pentest")
_REAL_ATTACK = _pattern(r"sans autorisation|non autorise\w*|cible reelle|"
                        r"attaquer une entreprise|voler|exfiltrer|unauthorized|real target")
_NEGATION = re.compile(
    r"\b(?:ne|n')\s*\w*\s*(?:veux|vais|souhaite|dois|faut)?\s*"
    r"(?:pas|jamais|plus)\s*(?:\w+\s+){0,3}$|"
    r"\b(?:ne pas|sans vouloir|refuse de|interdire de|do not|don't|never)\s*$"
)
_CLAUSE_BREAK = re.compile(r"[.!?;\n]+|\b(?:mais|cependant|pourtant|ensuite|puis|but|however|then)\b")


def _normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold()).replace("’", "'")
    return "".join(c for c in text if unicodedata.category(c) not in {"Mn", "Cf"})


def _windows(text):
    # Aucun préfixe seul : même les longues cellules CSV sont lues jusqu'au bout.
    for start in range(0, len(text), MAX_WINDOW_CHARS - WINDOW_OVERLAP):
        yield text[start:start + MAX_WINDOW_CHARS]
        if start + MAX_WINDOW_CHARS >= len(text):
            break


def _legitimate_action(clause, action, category):
    prefix = clause[:action.start()]
    # livr\w* couvre aussi « livre(s) ». Après un déterminant (ou en titre),
    # « livres sur ... » est un nom de support, pas une livraison d'armes.
    if (action.group() in {"livre", "livres"}
            and _STUDY_OBJECT.match(clause, action.start())
            and (not prefix.strip() or _NOUN_INTRODUCTION.search(prefix))):
        return True
    if _NEGATION.search(prefix[-80:]):
        return True
    if (re.search(r"\bne\s+$|\bn'$", prefix)
            and re.match(r"\s+(?:pas|jamais)\b", clause[action.end():])):
        return True
    context = list(_LEGITIMATE.finditer(prefix))
    if context:
        # « prévention ... donne la méthode pour fabriquer » reste opérationnel.
        governed = prefix[context[-1].start():]
        if not _DETAILS.search(governed):
            return True
    if (category == "malicious_cyber" and _AUTHORIZED.search(clause)
            and not _REAL_ATTACK.search(clause)):
        return True
    return False


def _moderate_fragment(fragment):
    for clause in _CLAUSE_BREAK.split(fragment):
        for rule in _RULES:
            targets = tuple(rule.target.finditer(clause))
            if not targets:
                continue
            for action in rule.action.finditer(clause):
                if _legitimate_action(clause, action, rule.category):
                    continue
                for target in targets:
                    start, end = min(action.start(), target.start()), max(action.end(), target.end())
                    if end - start > MAX_RELATION_CHARS:
                        continue
                    # L'objet d'un achat peut être un livre sur un sujet, et non
                    # le sujet dangereux lui-même. Les autres actions de la
                    # proposition sont toujours analysées séparément.
                    if target.start() > action.end():
                        relation = clause[action.end():target.start()]
                        if _STUDY_OBJECT.search(relation) and not _DETAILS.search(relation):
                            continue
                        # « Comment prévenir le suicide ? » : le verbe de
                        # prévention gouverne ici le sujet après « comment ».
                        if (rule.category == "self_harm" and _LEGITIMATE.search(relation)
                                and not _DETAILS.search(relation)):
                            continue
                    context = clause[max(0, start - 80):end + 80]
                    if rule.qualifier and not rule.qualifier.search(context):
                        # L'achat direct d'armes reste bloqué ; l'achat légal
                        # explicitement autorisé garde son traitement actuel.
                        if (rule.category != "illegal_weapons"
                                or not _WEAPON_PURCHASE.fullmatch(action.group())
                                or _LAWFUL_PURCHASE.search(context)):
                            continue
                    return ModerationDecision(True, rule.category)
    return ModerationDecision()


def moderate_texts(texts, *, budget_seconds=None):
    """Analyse en mémoire et en flux ; aucun modèle ni état utilisateur partagé.

    Toute erreur ou dépassement du budget reste bloquant (HTTP 503 dans les
    routes), avant Claude et avant la transaction d'import.
    """
    deadline = time.monotonic() + (MAX_SCREENING_SECONDS if budget_seconds is None else budget_seconds)
    try:
        for text in texts:
            # Normalisation par fenêtre : pas de copie normalisée du CSV entier.
            for window in _windows(text):
                if time.monotonic() >= deadline:
                    raise ScreeningUnavailable("Contrôle local non terminé.")
                decision = _moderate_fragment(_normalize(window))
                if time.monotonic() >= deadline:
                    raise ScreeningUnavailable("Contrôle local non terminé.")
                if decision.blocked:
                    return decision
        return ModerationDecision()
    except ScreeningUnavailable:
        raise
    except Exception:
        raise ScreeningUnavailable("Modération locale indisponible.") from None

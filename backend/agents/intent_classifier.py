"""Local intent classifier: keyword rules first, sentence embeddings second.

Most turns are settled here on CPU with no model call. A turn that neither stage is sure
about comes back with `needs_llm=True` and a best guess, and the orchestrator asks the LLM.
"""

import math
import re
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from agents.embeddings import Embedder, Vector, load_embedder
from agents.intent_data import EXEMPLARS, KEYWORDS, Intent
from agents.languages import Language
from config import get_settings

Source = Literal["keywords", "embedding", "none"]

# Keyword confidence is top / (top + runner_up + 1): one clear signal with no rival passes
KEYWORD_CONFIDENT = 0.6
# Cosine similarity to the closest exemplar, and its lead over the next intent
EMBEDDING_CONFIDENT = 0.6
EMBEDDING_MARGIN = 0.05

_JOINERS = dict.fromkeys(map(ord, "‌‍"))  # zero-width (non-)joiners
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)

# A few very common words of each language as typed in Latin script
_ROMAN_WORDS: dict[Language, frozenset[str]] = {
    "hi": frozenset(
        "hai hain kya karo kar mujhe mera meri mere mein kahan batao dikhao karna nahi aur "
        "kal aap raha rahi tha thi chahiye kaunse kitna milega paas sona".split()
    ),
    "kn": frozenset(
        "maadi madi beku nanna nanage ide enu ellide elli yaava yaavaga hogbeku thumba nale "
        "illa aagittu torisi kodi eshtu sigutte chinna".split()
    ),
    "ml": frozenset(
        "ente enikku undo venam ethra evide aanu alle cheyyanam kittum swarnam nale "
        "parayamo njan ningal".split()
    ),
    "ta": frozenset(
        "enakku enna evvalavu irukku vendum venum enga kidaikkum naan ungal thangam "
        "naalai sollunga".split()
    ),
}

# Unicode blocks of the Indic scripts we speak
_SCRIPTS: tuple[tuple[Language, str, str], ...] = (
    ("hi", "ऀ", "ॿ"),  # Devanagari
    ("ta", "஀", "௿"),  # Tamil
    ("kn", "ಀ", "೿"),  # Kannada
    ("ml", "ഀ", "ൿ"),  # Malayalam
)


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    confidence: float
    source: Source
    needs_llm: bool
    language: Language


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_JOINERS).lower()
    # Keep combining marks (Indic vowel signs are category M, which \w does not cover)
    kept = "".join(
        ch if ch.isalnum() or ch.isspace() or unicodedata.category(ch).startswith("M") else " "
        for ch in text
    )
    return " ".join(kept.split())


def detect_language(text: str) -> Language:
    """Script first; for Latin script, a few very common romanised words of each language."""
    for language, first, last in _SCRIPTS:
        if any(first <= ch <= last for ch in text):
            return language
    words = set(normalise(text).split())
    counts = {language: len(words & roman) for language, roman in _ROMAN_WORDS.items()}
    best = max(counts, key=lambda language: counts[language])
    return best if counts[best] else "en"


def _compile(pattern: str) -> re.Pattern[str]:
    if pattern.isascii():
        return re.compile(rf"\b(?:{pattern})\b")
    return re.compile(re.escape(normalise(pattern)))


_RULES: dict[Intent, list[tuple[re.Pattern[str], int]]] = {
    intent: [(_compile(pattern), weight) for pattern, weight in rules]
    for intent, rules in KEYWORDS.items()
}


def keyword_scores(text: str) -> dict[Intent, int]:
    clean = normalise(text)
    return {
        intent: sum(weight for pattern, weight in rules if pattern.search(clean))
        for intent, rules in _RULES.items()
    }


def _cosine(a: Vector, b: Vector) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


class IntentClassifier:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder
        self._exemplars: list[tuple[Intent, Vector]] | None = None

    @property
    def has_embeddings(self) -> bool:
        return self._embedder is not None

    def _similarities(self, text: str) -> dict[Intent, float]:
        """Closest-exemplar cosine similarity for each intent."""
        assert self._embedder is not None  # noqa: S101 — callers check has_embeddings
        if self._exemplars is None:
            labelled = [
                (intent, phrase) for intent, phrases in EXEMPLARS.items() for phrase in phrases
            ]
            vectors = self._embedder.embed([phrase for _, phrase in labelled])
            self._exemplars = [
                (intent, v) for (intent, _), v in zip(labelled, vectors, strict=True)
            ]
        query = self._embedder.embed([text])[0]
        best = dict.fromkeys(Intent, 0.0)
        for intent, vector in self._exemplars:
            best[intent] = max(best[intent], _cosine(query, vector))
        return best

    def classify(self, text: str) -> IntentResult:
        language = detect_language(text)
        scores = keyword_scores(text)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        (kw_intent, top), (_, runner_up) = ranked[0], ranked[1]
        kw_confidence = top / (top + runner_up + 1)

        if top and top > runner_up and kw_confidence >= KEYWORD_CONFIDENT:
            return IntentResult(kw_intent, kw_confidence, "keywords", False, language)

        kw_guess = kw_intent if top > runner_up else None
        if self._embedder is None or not text.strip():
            return IntentResult(kw_guess or Intent.GENERAL, kw_confidence, "none", True, language)

        similar = sorted(self._similarities(text).items(), key=lambda item: item[1], reverse=True)
        (emb_intent, best), (_, second) = similar[0], similar[1]
        agrees = kw_guess is None or kw_guess == emb_intent
        if best >= EMBEDDING_CONFIDENT and best - second >= EMBEDDING_MARGIN and agrees:
            return IntentResult(emb_intent, best, "embedding", False, language)
        return IntentResult(kw_guess or emb_intent, best, "none", True, language)


@lru_cache
def get_classifier() -> IntentClassifier:
    """The full classifier. Loading its embedding model takes seconds: call it at start-up."""
    classifier = IntentClassifier(load_embedder(get_settings().intent_embedding_model))
    _ready.set()
    return classifier


_ready = threading.Event()
_KEYWORDS_ONLY = IntentClassifier()


def classifier_for_requests() -> IntentClassifier:
    """What a request should classify with: never something that is still loading.

    Until the start-up warm-up has loaded the embedding model, requests use the keyword
    rules alone. Loading it inside a request would hold every other customer's request
    for seconds (the load test caught this).
    """
    if _ready.is_set() or not get_settings().intent_embedding_model:
        return get_classifier()
    return _KEYWORDS_ONLY


def models_ready() -> bool:
    return _ready.is_set() or not get_settings().intent_embedding_model

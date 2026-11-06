import pytest

from agents.intent_classifier import IntentClassifier, detect_language
from agents.intent_data import Intent

KEYWORDS_ONLY = IntentClassifier()


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("How much loan for 30 grams?", "en"),
        ("Mere paas 30 gram sona hai, kitna loan milega?", "hi"),
        ("मेरे पास 30 ग्राम सोना है", "hi"),
        ("ನನ್ನ ಬಳಿ 30 ಗ್ರಾಂ ಚಿನ್ನ ಇದೆ", "kn"),
        ("എന്റെ കയ്യിൽ 4 പവൻ സ്വർണമുണ്ട്", "ml"),
        ("என்னிடம் 30 கிராம் தங்கம் உள்ளது", "ta"),
        ("ente kayyil swarnam undu, ethra kittum", "ml"),
        ("enakku evvalavu kadan kidaikkum", "ta"),
    ],
)
def test_language_is_detected(text: str, language: str) -> None:
    assert detect_language(text) == language


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        # The headline demo, in every language
        ("Mere paas 30 gram sona hai, kitna loan milega?", Intent.CALCULATOR),
        ("I have 30 grams of 22 carat gold, how much loan can I get?", Intent.CALCULATOR),
        ("मेरे पास 30 ग्राम सोना है, कितना लोन मिलेगा?", Intent.CALCULATOR),
        ("ನನ್ನ ಬಳಿ 30 ಗ್ರಾಂ ಚಿನ್ನ ಇದೆ, ಎಷ್ಟು ಸಾಲ ಸಿಗುತ್ತದೆ?", Intent.CALCULATOR),
        ("എന്റെ കയ്യിൽ 4 പവൻ സ്വർണമുണ്ട്, എത്ര വായ്പ കിട്ടും?", Intent.CALCULATOR),
        ("என்னிடம் 30 கிராம் தங்கம் உள்ளது, எவ்வளவு கடன் கிடைக்கும்?", Intent.CALCULATOR),
        # Branch visits
        ("Book a valuation slot at the Kochi branch tomorrow", Intent.VISIT),
        ("Cancel my visit", Intent.VISIT),
        ("कल के लिए विज़िट बुक करो", Intent.VISIT),
        ("நாளை கிளை வருகை முன்பதிவு", Intent.VISIT),
        # Account
        ("What is my outstanding amount?", Intent.ACCOUNT),
        ("When is my interest due date?", Intent.ACCOUNT),
        ("मेरा लोन बकाया कितना है", Intent.ACCOUNT),
        ("ನನ್ನ ಸಾಲದ ಬಾಕಿ ಎಷ್ಟು", Intent.ACCOUNT),
        ("എന്റെ വായ്പയുടെ ബാക്കി എത്ര", Intent.ACCOUNT),
        ("என் கடன் நிலுவை எவ்வளவு", Intent.ACCOUNT),
        # Help
        ("What documents do I need?", Intent.HELP),
        ("What is the gold rate today?", Intent.HELP),
        ("I want to make a complaint", Intent.HELP),
        ("Can I do a part payment?", Intent.HELP),
        ("गोल्ड लोन के लिए कौन से दस्तावेज़ चाहिए", Intent.HELP),
        ("ಯಾವ ದಾಖಲೆಗಳು ಬೇಕು", Intent.HELP),
        ("എന്തൊക്കെ രേഖകൾ വേണം", Intent.HELP),
        ("என்ன ஆவணங்கள் வேண்டும்", Intent.HELP),
        # General
        ("Hello", Intent.GENERAL),
        ("നമസ്കാരം", Intent.GENERAL),
        ("வணக்கம்", Intent.GENERAL),
    ],
)
def test_keywords_route_without_a_model(text: str, intent: Intent) -> None:
    result = KEYWORDS_ONLY.classify(text)

    assert result.intent == intent
    assert result.source == "keywords"
    assert not result.needs_llm


def test_a_message_with_no_signal_needs_the_llm() -> None:
    result = KEYWORDS_ONLY.classify("what about tomorrow then")

    assert result.needs_llm

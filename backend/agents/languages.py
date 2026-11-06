"""The languages the assistant speaks, and the replies that must exist in every one of them.

These are said without a model: guardrail warnings, the estimate disclaimer, and the rule-based
loan estimate (the headline demo has to work even when no LLM answers). Everything else a
model writes in the customer's language, and the rule-based replies of other agents are English.

Translations were written for the demo; have a native speaker check them before real use.
"""

from typing import Literal

Language = Literal["en", "hi", "kn", "ml", "ta"]
LANGUAGES: tuple[Language, ...] = ("en", "hi", "kn", "ml", "ta")

LANGUAGE_NAMES: dict[Language, str] = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "ml": "Malayalam",
    "ta": "Tamil",
}

# Said whenever a customer tries to share an OTP, PIN, CVV or password
SECRET_WARNING: dict[Language, str] = {
    "en": (
        "Muthoot will never ask for your OTP, PIN, CVV or password. Please don't share them "
        "with anyone, including me."
    ),
    "hi": (
        "मुथूट कभी भी आपका OTP, PIN, CVV या पासवर्ड नहीं माँगेगा। कृपया इन्हें किसी के साथ "
        "साझा न करें, मेरे साथ भी नहीं।"
    ),
    "kn": (
        "ಮುತ್ತೂಟ್ ಎಂದಿಗೂ ನಿಮ್ಮ OTP, PIN, CVV ಅಥವಾ ಪಾಸ್‌ವರ್ಡ್ ಕೇಳುವುದಿಲ್ಲ. ದಯವಿಟ್ಟು ಅವುಗಳನ್ನು "
        "ಯಾರೊಂದಿಗೂ ಹಂಚಿಕೊಳ್ಳಬೇಡಿ, ನನ್ನೊಂದಿಗೂ ಸಹ."
    ),
    "ml": (
        "മുത്തൂറ്റ് ഒരിക്കലും നിങ്ങളുടെ OTP, PIN, CVV അല്ലെങ്കിൽ പാസ്‌വേഡ് ചോദിക്കില്ല. "
        "ദയവായി അവ ആരുമായും പങ്കിടരുത്, എന്നോടും."
    ),
    "ta": (
        "முத்தூட் ஒருபோதும் உங்கள் OTP, PIN, CVV அல்லது கடவுச்சொல்லைக் கேட்காது. "
        "தயவுசெய்து அவற்றை யாருடனும் பகிர வேண்டாம், என்னுடனும் கூட."
    ),
}

INVESTMENT_REFUSAL: dict[Language, str] = {
    "en": (
        "I can't give investment advice, such as whether to buy or sell gold. I can tell you "
        "today's gold rate or estimate a loan on your gold."
    ),
    "hi": (
        "मैं निवेश सलाह नहीं दे सकता, जैसे सोना खरीदना या बेचना चाहिए या नहीं। मैं आज का सोने "
        "का भाव बता सकता हूँ या आपके सोने पर लोन का अनुमान दे सकता हूँ।"
    ),
    "kn": (
        "ಚಿನ್ನ ಖರೀದಿಸಬೇಕೇ ಅಥವಾ ಮಾರಬೇಕೇ ಎಂಬಂತಹ ಹೂಡಿಕೆ ಸಲಹೆ ನಾನು ನೀಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ಇಂದಿನ "
        "ಚಿನ್ನದ ದರ ಹೇಳಬಲ್ಲೆ ಅಥವಾ ನಿಮ್ಮ ಚಿನ್ನದ ಮೇಲೆ ಸಾಲದ ಅಂದಾಜು ನೀಡಬಲ್ಲೆ."
    ),
    "ml": (
        "സ്വർണം വാങ്ങണോ വിൽക്കണോ പോലുള്ള നിക്ഷേപ ഉപദേശം എനിക്ക് നൽകാൻ കഴിയില്ല. ഇന്നത്തെ "
        "സ്വർണവില പറയാം, അല്ലെങ്കിൽ നിങ്ങളുടെ സ്വർണത്തിന് ലഭിക്കാവുന്ന വായ്പയുടെ ഏകദേശ തുക പറയാം."
    ),
    "ta": (
        "தங்கம் வாங்கலாமா விற்கலாமா போன்ற முதலீட்டு ஆலோசனையை என்னால் வழங்க முடியாது. இன்றைய "
        "தங்க விலையைச் சொல்லலாம் அல்லது உங்கள் தங்கத்திற்கான கடன் மதிப்பீட்டைத் தரலாம்."
    ),
}

# Shown and spoken with every reply that gives a loan amount
ESTIMATE_DISCLAIMER: dict[Language, str] = {
    "en": (
        "This is an estimate only. The final loan amount is decided after your gold is "
        "valued at the branch."
    ),
    "hi": "यह केवल एक अनुमान है। अंतिम लोन राशि शाखा में आपके सोने के मूल्यांकन के बाद तय होगी।",
    "kn": ("ಇದು ಕೇವಲ ಅಂದಾಜು. ಅಂತಿಮ ಸಾಲದ ಮೊತ್ತವನ್ನು ಶಾಖೆಯಲ್ಲಿ ನಿಮ್ಮ ಚಿನ್ನದ ಮೌಲ್ಯಮಾಪನದ ನಂತರ ನಿರ್ಧರಿಸಲಾಗುತ್ತದೆ."),
    "ml": (
        "ഇത് ഒരു ഏകദേശ കണക്ക് മാത്രമാണ്. ബ്രാഞ്ചിൽ നിങ്ങളുടെ സ്വർണം മൂല്യനിർണയം ചെയ്ത ശേഷമാണ് "
        "അന്തിമ വായ്പാ തുക തീരുമാനിക്കുന്നത്."
    ),
    "ta": (
        "இது ஒரு மதிப்பீடு மட்டுமே. கிளையில் உங்கள் தங்கம் மதிப்பிடப்பட்ட பிறகே இறுதிக் கடன் "
        "தொகை முடிவு செய்யப்படும்."
    ),
}

# What replaces a reply the output guardrails blocked
SAFE_FALLBACK: dict[Language, str] = {
    "en": (
        "Sorry, I can't answer that. I can estimate a gold loan, book a branch visit, show "
        "your loan account, or help with documents and timings."
    ),
    "hi": (
        "क्षमा करें, मैं इसका उत्तर नहीं दे सकता। मैं गोल्ड लोन का अनुमान दे सकता हूँ, शाखा "
        "विज़िट बुक कर सकता हूँ, आपका लोन खाता दिखा सकता हूँ, या दस्तावेज़ों और समय की "
        "जानकारी दे सकता हूँ।"
    ),
    "kn": (
        "ಕ್ಷಮಿಸಿ, ನಾನು ಅದಕ್ಕೆ ಉತ್ತರಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ. ಚಿನ್ನದ ಸಾಲದ ಅಂದಾಜು, ಶಾಖೆ ಭೇಟಿ ಬುಕಿಂಗ್, "
        "ನಿಮ್ಮ ಸಾಲದ ಖಾತೆ ಅಥವಾ ದಾಖಲೆಗಳು ಮತ್ತು ಸಮಯದ ಬಗ್ಗೆ ಸಹಾಯ ಮಾಡಬಲ್ಲೆ."
    ),
    "ml": (
        "ക്ഷമിക്കണം, അതിന് ഉത്തരം നൽകാൻ എനിക്ക് കഴിയില്ല. സ്വർണ വായ്പയുടെ ഏകദേശ തുക, ബ്രാഞ്ച് "
        "സന്ദർശനം ബുക്ക് ചെയ്യൽ, നിങ്ങളുടെ വായ്പാ അക്കൗണ്ട്, രേഖകളും സമയവും എന്നിവയിൽ സഹായിക്കാം."
    ),
    "ta": (
        "மன்னிக்கவும், அதற்கு என்னால் பதில் அளிக்க முடியாது. தங்கக் கடன் மதிப்பீடு, கிளை "
        "வருகை முன்பதிவு, உங்கள் கடன் கணக்கு, ஆவணங்கள் மற்றும் நேரங்கள் பற்றி உதவ முடியும்."
    ),
}

CAPABILITIES: dict[Language, str] = {
    "en": (
        "I can estimate a gold loan, book a gold valuation visit at a branch, tell you about "
        "your loan account, and help with documents, branch timings, today's gold rate and "
        "complaints."
    ),
    "hi": (
        "मैं गोल्ड लोन का अनुमान दे सकता हूँ, शाखा में सोने के मूल्यांकन के लिए विज़िट बुक कर "
        "सकता हूँ, आपके लोन खाते की जानकारी दे सकता हूँ, और दस्तावेज़, शाखा का समय, आज का "
        "सोने का भाव और शिकायतों में मदद कर सकता हूँ।"
    ),
    "kn": (
        "ನಾನು ಚಿನ್ನದ ಸಾಲದ ಅಂದಾಜು ನೀಡಬಲ್ಲೆ, ಶಾಖೆಯಲ್ಲಿ ಚಿನ್ನದ ಮೌಲ್ಯಮಾಪನಕ್ಕೆ ಭೇಟಿ ಬುಕ್ "
        "ಮಾಡಬಲ್ಲೆ, ನಿಮ್ಮ ಸಾಲದ ಖಾತೆಯ ಬಗ್ಗೆ ತಿಳಿಸಬಲ್ಲೆ, ಮತ್ತು ದಾಖಲೆಗಳು, ಶಾಖೆಯ ಸಮಯ, ಇಂದಿನ "
        "ಚಿನ್ನದ ದರ ಹಾಗೂ ದೂರುಗಳಿಗೆ ಸಹಾಯ ಮಾಡಬಲ್ಲೆ."
    ),
    "ml": (
        "സ്വർണ വായ്പയുടെ ഏകദേശ തുക പറയാനും, ബ്രാഞ്ചിൽ സ്വർണ മൂല്യനിർണയത്തിനുള്ള സന്ദർശനം "
        "ബുക്ക് ചെയ്യാനും, നിങ്ങളുടെ വായ്പാ അക്കൗണ്ട് വിവരങ്ങൾ പറയാനും, രേഖകൾ, ബ്രാഞ്ച് സമയം, "
        "ഇന്നത്തെ സ്വർണവില, പരാതികൾ എന്നിവയിൽ സഹായിക്കാനും എനിക്ക് കഴിയും."
    ),
    "ta": (
        "தங்கக் கடன் மதிப்பீடு தரவும், கிளையில் தங்க மதிப்பீட்டுக்கான வருகையை முன்பதிவு "
        "செய்யவும், உங்கள் கடன் கணக்கு விவரங்களைச் சொல்லவும், ஆவணங்கள், கிளை நேரம், இன்றைய "
        "தங்க விலை மற்றும் புகார்களில் உதவவும் என்னால் முடியும்."
    ),
}

# The rule-based loan estimate. {low} and {high} are already formatted, e.g. "₹2,22,700".
ESTIMATE_REPLY: dict[Language, str] = {
    "en": "For {grams} g of {carat} carat gold, you could get a loan of about {low} to {high}.",
    "hi": "{grams} ग्राम {carat} कैरेट सोने पर आपको लगभग {low} से {high} तक का लोन मिल सकता है।",
    "kn": "{grams} ಗ್ರಾಂ {carat} ಕ್ಯಾರೆಟ್ ಚಿನ್ನಕ್ಕೆ ನಿಮಗೆ ಸುಮಾರು {low} ರಿಂದ {high} ವರೆಗೆ ಸಾಲ ಸಿಗಬಹುದು.",
    "ml": "{grams} ഗ്രാം {carat} കാരറ്റ് സ്വർണത്തിന് ഏകദേശം {low} മുതൽ {high} വരെ വായ്പ ലഭിക്കാം.",
    "ta": "{grams} கிராம் {carat} கேரட் தங்கத்திற்கு சுமார் {low} முதல் {high} வரை கடன் கிடைக்கலாம்.",
}

ASK_GRAMS: dict[Language, str] = {
    "en": "How many grams of gold do you have, and is it 22 or 24 carat?",
    "hi": "आपके पास कितने ग्राम सोना है, और वह 22 कैरेट है या 24 कैरेट?",
    "kn": "ನಿಮ್ಮ ಬಳಿ ಎಷ್ಟು ಗ್ರಾಂ ಚಿನ್ನವಿದೆ, ಮತ್ತು ಅದು 22 ಕ್ಯಾರೆಟ್ ಅಥವಾ 24 ಕ್ಯಾರೆಟ್?",
    "ml": "നിങ്ങളുടെ കയ്യിൽ എത്ര ഗ്രാം സ്വർണമുണ്ട്, അത് 22 കാരറ്റാണോ 24 കാരറ്റാണോ?",
    "ta": "உங்களிடம் எத்தனை கிராம் தங்கம் உள்ளது, அது 22 கேரட்டா 24 கேரட்டா?",
}

OFFER_VISIT: dict[Language, str] = {
    "en": "Shall I book a branch visit to value your gold?",
    "hi": "क्या मैं सोने के मूल्यांकन के लिए शाखा विज़िट बुक कर दूँ?",
    "kn": "ನಿಮ್ಮ ಚಿನ್ನದ ಮೌಲ್ಯಮಾಪನಕ್ಕೆ ಶಾಖೆ ಭೇಟಿಯನ್ನು ಬುಕ್ ಮಾಡಲೇ?",
    "ml": "നിങ്ങളുടെ സ്വർണം മൂല്യനിർണയം ചെയ്യാൻ ഒരു ബ്രാഞ്ച് സന്ദർശനം ബുക്ക് ചെയ്യട്ടേ?",
    "ta": "உங்கள் தங்கத்தை மதிப்பிட கிளை வருகையை முன்பதிவு செய்யட்டுமா?",
}

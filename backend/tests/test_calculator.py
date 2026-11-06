import pytest

from services.gold import rupees
from tools.calculator_tools import parse_gold


@pytest.mark.parametrize(
    ("text", "grams", "carat"),
    [
        ("Mere paas 30 gram sona hai, kitna loan milega?", 30, None),
        ("I have 30g of 22 carat gold", 30, 22),
        ("12.5 grams, 24k", 12.5, 24),
        ("30 gms 18 kt", 30, 18),
        ("4 pavan", 32, None),
        ("2 sovereigns of 22 carat", 16, 22),
        ("one tola", 11.66, None),
        ("tees gram sona", 30, None),
        ("मेरे पास तीस ग्राम सोना है", 30, None),
        ("मेरे पास 30 ग्राम 22 कैरेट सोना है", 30, 22),
        ("ನನ್ನ ಬಳಿ 30 ಗ್ರಾಂ ಚಿನ್ನ ಇದೆ", 30, None),
        ("എന്റെ കയ്യിൽ 4 പവൻ സ്വർണമുണ്ട്", 32, None),
        ("என்னிடம் 30 கிராம் தங்கம்", 30, None),
        ("thirty grams", 30, None),
    ],
)
def test_grams_and_carat_are_read_from_what_the_customer_said(
    text: str, grams: float, carat: int | None
) -> None:
    found = parse_gold(text)

    assert found.grams == grams
    assert found.carat == carat


@pytest.mark.parametrize(
    "text",
    [
        "I have 30 gold bangles",  # "30 g" must not be read out of "30 gold"
        "how much loan can I get",
        "my pin code is 682011",
        "20 carat",  # not a purity we lend on
    ],
)
def test_no_weight_is_invented(text: str) -> None:
    assert parse_gold(text).grams is None


@pytest.mark.parametrize(
    ("amount", "text"),
    [(0, "₹0"), (950, "₹950"), (2_47_500, "₹2,47,500"), (12_34_56_789, "₹12,34,56,789")],
)
def test_rupees_use_indian_grouping(amount: int, text: str) -> None:
    assert rupees(amount) == text

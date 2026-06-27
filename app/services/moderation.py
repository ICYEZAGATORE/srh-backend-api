"""
app/services/moderation.py — Safety fallback routing.

Centralises the user-facing fallback copy and crisis referral shown when the
safety classifier flags a query as UNSAFE. Bilingual (English / Kinyarwanda).
"""

FALLBACK_MESSAGES = {
    "en": "I'm not able to help with that. If you need support, please speak to a trusted health worker or call a helpline.",
    "rw": "Ntabwo nshobora gufasha muri icyo kibazo. Niba ukeneye inkunga, baza inzobere y'ubuzima.",
}

REFERRAL = {
    "en": "Rwanda Health Hotline: 114",
    "rw": "Inzira y'ubuzima mu Rwanda: 114",
}


def get_fallback(lang: str) -> dict:
    """Return the fallback message + referral for ``lang`` (defaults to English)."""
    lang = lang if lang in FALLBACK_MESSAGES else "en"
    return {
        "fallback_message": FALLBACK_MESSAGES[lang],
        "referral": {"text": REFERRAL[lang], "url": None},
    }

"""Business catalogue: countries, plans, quotas and products.

Every amount is an integer in the local currency (XAF and XOF have no decimals).
Values come from the project brief (fiche projet) unless marked DECISION.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    currency: str  # ISO 4217
    language: str = "fr"


# XAF = CEMAC (Cameroun, Gabon, Congo), XOF = UEMOA (Sénégal, Côte d'Ivoire, Togo, Bénin, Burkina).
COUNTRIES: dict[str, Country] = {
    c.code: c
    for c in [
        Country("CM", "Cameroun", "XAF"),
        Country("GA", "Gabon", "XAF"),
        Country("CG", "Congo-Brazzaville", "XAF"),
        Country("SN", "Sénégal", "XOF"),
        Country("CI", "Côte d'Ivoire", "XOF"),
        Country("TG", "Togo", "XOF"),
        Country("BJ", "Bénin", "XOF"),
        Country("BF", "Burkina Faso", "XOF"),
    ]
}

# Per-country price overrides, keyed by (country_code, product_code).
# DECISION: empty for now, all FCFA countries pay the same price.
PRICE_OVERRIDES: dict[tuple[str, str], int] = {}

# Plan limits. None = unlimited.
PLAN_LIMITS: dict[str, dict[str, object]] = {
    "free": {
        "max_subjects": 3,
        "ai_ops_per_day": 5,
        "evaluations_per_week": 1,
        "document_analysis": False,
    },
    "etudiant": {  # also granted by the annual plan (DECISION: annual = Étudiant features)
        "max_subjects": None,
        "ai_ops_per_day": 30,
        "evaluations_per_week": 5,
        "document_analysis": False,
    },
    "premium": {
        "max_subjects": None,
        "ai_ops_per_day": 100,
        "evaluations_per_week": 5,  # DECISION: the brief does not give a figure for Premium
        "document_analysis": True,
    },
}

# Products that can be bought. Price in local currency before promo codes.
PRODUCTS: dict[str, dict[str, object]] = {
    "etudiant_monthly": {"kind": "plan", "plan": "etudiant", "days": 30, "price": 3500},
    "etudiant_annual": {"kind": "plan", "plan": "etudiant", "days": 365, "price": 16500},
    "premium_monthly": {"kind": "plan", "plan": "premium", "days": 30, "price": 7000},
    # DECISION: credit packs (the brief has no price list for credits)
    "credits_100": {"kind": "credits", "credits": 100, "price": 1000},
    "credits_300": {"kind": "credits", "credits": 300, "price": 2500},
}


def get_country(code: str) -> Country:
    country = COUNTRIES.get(code.upper())
    if country is None:
        raise ValueError(f"Pays non pris en charge : {code}")
    return country


def price_for(country_code: str, product: str) -> int:
    return PRICE_OVERRIDES.get((country_code, product), int(PRODUCTS[product]["price"]))  # type: ignore[arg-type]

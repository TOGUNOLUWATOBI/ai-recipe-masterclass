"""Country -> demonym (adjective form) mapping for the countries actually present in the
curated corpus. Needed because BM25 does zero stemming — a query for "nigerian stew"
shares no token at all with a recipe whose text only says "Nigeria" (confirmed via
retrieval debugging: Obe Ata's BM25 score for that query came entirely from "stew",
ranking it 110th, well outside the candidate pool). A generic English stemmer doesn't
fix this either, since demonym formation ("Nigeria" -> "Nigerian", "Mali" -> "Malian")
isn't a simple suffix-stripping relationship a stemmer would normalize both ways.
Explicit mapping is small, bounded, and correct — better than guessing with a suffix rule
for irregular cases like "Côte d'Ivoire" -> "Ivorian" or "Democratic Republic of Congo"
-> "Congolese"."""

COUNTRY_DEMONYMS = {
    "Benin": "Beninese",
    "Cameroon": "Cameroonian",
    "Côte d'Ivoire": "Ivorian",
    "Democratic Republic of Congo": "Congolese",
    "Denmark": "Danish",
    "Egypt": "Egyptian",
    "Ethiopia": "Ethiopian",
    "Ghana": "Ghanaian",
    "Guinea": "Guinean",
    "Kenya": "Kenyan",
    "Liberia": "Liberian",
    "Mali": "Malian",
    "Morocco": "Moroccan",
    "Mozambique": "Mozambican",
    "Nigeria": "Nigerian",
    "Norway": "Norwegian",
    "Senegal": "Senegalese",
    "Sierra Leone": "Sierra Leonean",
    "South Africa": "South African",
    "Sweden": "Swedish",
    "Tanzania": "Tanzanian",
    "Togo": "Togolese",
    "Tunisia": "Tunisian",
    "Uganda": "Ugandan",
    "Zambia": "Zambian",
    "Zimbabwe": "Zimbabwean",
}


def demonym_for(country: str) -> str:
    """Returns the demonym if known, else the country name unchanged (safe no-op for
    any future country added to the corpus without updating this table)."""
    return COUNTRY_DEMONYMS.get(country, country)

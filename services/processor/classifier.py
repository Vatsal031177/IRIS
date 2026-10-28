import re
from typing import Dict, List, Optional, Tuple
from services.common.models import RawNewsArticle, SignalType


SIGNAL_RULES: Dict[SignalType, List[Tuple[str, re.Pattern]]] = {
    SignalType.ESG_DEBT_ISSUANCE: [
        ("green_bond", re.compile(r"\bgreen\s+bonds?\b", re.I)),
        ("gruene_anleihe", re.compile(r"\bgrüne[n]?\s+anleihe[n]?\b", re.I)),
        ("esg_anleihe", re.compile(r"\besg[\-\s]anleihe[n]?\b", re.I)),
        ("sustainability_bond", re.compile(r"\bsustainability[\-\s]linked\s+bonds?\b", re.I)),
        ("eu_green_bond_standard", re.compile(r"\bstandard\s+für\s+grüne\s+anleihen\b", re.I)),
    ],
    SignalType.INFRASTRUCTURE_FUND_LAUNCH: [
        ("infrastrukturfonds", re.compile(r"\binfrastruktur[\-\s]?fonds\b", re.I)),
        ("infrastructure_fund", re.compile(r"\binfrastructure\s+fund\b", re.I)),
        ("wind_und_solarparks_fonds", re.compile(r"\b(wind[\-\s]und\s+solarparks|energieinfrastruktur)\b.*\b(spezialfonds|fonds)\b", re.I)),
        ("klima_infrastruktur", re.compile(r"\bklima[\-\s]infrastrukturfonds\b", re.I)),
        ("fonds_auflegung_infrastruktur", re.compile(r"\b(legt|startet|closing)\b.*\b(infrastruktur|erneuerbare\s+energien|solarparks)\b", re.I)),
    ],
    SignalType.INSTITUTIONAL_ALLOCATION_MANDATE: [
        ("kapitalzusagen", re.compile(r"\bkapitalzusagen\b", re.I)),
        ("pensionskasse_allokation", re.compile(r"\b(pensionskasse|versorgungswerk|pensionsvermögen|staatsfonds)\b", re.I)),
        ("mandat_vergabe", re.compile(r"\b(mandat|allokation|kapitalzuweisung)\b", re.I)),
        ("institutionelle_private_markets", re.compile(r"\b(private\s+debt|private\s+capital|infrastruktur)\b.*\b(chancen|institutionelle|portfolios)\b", re.I)),
    ],
}


class DealFlowSignalClassifier:
    """
    Classifies German/English Institutional Money newsroom articles into the three
    target deal-flow signal categories required by IRIS-SIG-47.
    """

    def classify(
        self, article: RawNewsArticle
    ) -> Optional[Tuple[SignalType, List[str]]]:
        combined_text = f"{article.title} {article.summary_text or ''}"

        # Priority order: ESG Debt Issuance -> Infrastructure Fund Launch -> Institutional Allocation Mandate
        for signal_type in (
            SignalType.ESG_DEBT_ISSUANCE,
            SignalType.INFRASTRUCTURE_FUND_LAUNCH,
            SignalType.INSTITUTIONAL_ALLOCATION_MANDATE,
        ):
            matched_labels: List[str] = []
            for label, pattern in SIGNAL_RULES[signal_type]:
                if pattern.search(combined_text):
                    matched_labels.append(label)
            if matched_labels:
                return signal_type, matched_labels

        return None

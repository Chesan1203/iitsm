"""Duplicate incident detection without machine learning.

1. Lowercase the text and split it into words (apostrophes removed: can't -> cant).
2. Drop stopwords.
3. Replace words by a canonical word using synonym groups (down/failing/unable -> FAIL, ...).
4. Text similarity = Jaccard: |overlap| / |union| of the two word sets.
5. Score = 0.7 x text similarity + 0.3 x (1 if same service). Flag at 0.5 or more.

Text similarity is the better of two comparisons: title only, and title plus description.
Descriptions are mandatory and long ones would dilute a clear title match, so the title-only
comparison stops a wordy description from hiding an obvious duplicate. Flag only: never merge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.business_rules import BusinessRules as R

if TYPE_CHECKING:
    from app.domain.models.incident import Incident

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "for", "and", "in",
    "on", "at", "by", "with", "from", "as", "it", "this", "that", "when", "can", "will", "has",
    "have", "my", "our", "we", "i",
})  # "unable" and "cannot" are NOT stopwords: they are mapped to FAIL below.

_SYNONYM_GROUPS = {
    "FAIL": "unavailable down failing failed fail failure error errors outage unable cannot cant "
            "broken crashed crash crashing unreachable",
    "PAYMENT": "payment payments pay paying transaction transactions checkout",
    "AUTH": "login logon signin sign password passwords authenticate authentication credential "
            "credentials sso",
    "NETWORK": "network wifi internet connectivity connection lan",
    "EMAIL": "email emails mail outlook inbox smtp",
    "DATABASE": "database db sql query queries",
    "SLOW": "slow slowness latency lag laggy delayed timeout timeouts",
    "STORAGE": "storage disk quota space",
    "PRINTER": "printer printing print",
}
_CANONICAL = {word: canon for canon, words in _SYNONYM_GROUPS.items() for word in words.split()}
_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    """The comparable word set of a text (stopwords removed, synonyms unified)."""
    words = _WORD.findall(text.lower().replace("'", "").replace("’", ""))
    return {_CANONICAL.get(w, w) for w in words if len(w) > 1 and w not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _same_service(a: Incident, b: Incident) -> bool:
    sa, sb = a.affected_service, b.affected_service
    return sa.id == sb.id if sa.id is not None and sb.id is not None else sa == sb


@dataclass(frozen=True)
class DuplicateMatch:
    other_ticket_number: str
    score: float


class DuplicateDetector:
    def find_similar(self, incident: Incident, recent_incidents: list[Incident]) -> list[DuplicateMatch]:
        """Matches at or above the threshold, best first. The caller decides which incidents
        are 'recent' (the plan: open, same service, last 24 hours)."""
        title = tokens(incident.title)
        full = title | tokens(incident.description)
        matches = []
        for other in recent_incidents:
            if (other is incident or other.ticket_number is None
                    or other.ticket_number == incident.ticket_number):
                continue
            other_title = tokens(other.title)
            other_full = other_title | tokens(other.description)
            text = max(_jaccard(title, other_title), _jaccard(full, other_full))
            same = 1.0 if _same_service(incident, other) else 0.0
            score = round(R.DUPLICATE_TEXT_WEIGHT * text + R.DUPLICATE_SERVICE_WEIGHT * same, 4)
            if score >= R.DUPLICATE_THRESHOLD:
                matches.append(DuplicateMatch(other.ticket_number, score))
        matches.sort(key=lambda m: (-m.score, m.other_ticket_number))
        return matches

"""Two-document TF-IDF: raw counts, smooth IDF, L2 cosine; stable token order."""
from collections import Counter
from math import log, sqrt
import re

from .normalize import normalize
from .role_templates import ROLE_TEMPLATES

_STOP = set("a an the and or of to in for with on at is are as by from this that i my و في من علي الي".split())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[^\W_]+", normalize(text)) if len(t) > 1 and t not in _STOP]


def tfidf_cosine(left: str, right: str) -> float:
    a, b = Counter(tokens(left)), Counter(tokens(right))
    vocabulary = sorted(a.keys() | b.keys())
    av, bv = [], []
    for term in vocabulary:
        idf = log(3 / (1 + int(term in a) + int(term in b))) + 1
        av.append(a[term] * idf)
        bv.append(b[term] * idf)
    denominator = sqrt(sum(v * v for v in av) * sum(v * v for v in bv))
    return min(1.0, sum(x * y for x, y in zip(av, bv)) / denominator) if denominator else 0.0


def suggest_template(text: str, templates=None, min_score: float = 0.04, min_margin: float = 0.005):
    """Return ``(template, similarity)`` or abstain with ``(None, score)``.

    This helper is intentionally separate from ``score``: similarity suggests
    a starting template and never contributes points to a candidate.
    """
    candidates = templates or ROLE_TEMPLATES
    ranked = sorted(
        ((tfidf_cosine(text, template.get("similarity_text", template["title"])), template)
         for template in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked:
        return None, 0.0
    best_score, best = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score < min_score or best_score - runner_up < min_margin:
        return None, best_score
    return best, best_score

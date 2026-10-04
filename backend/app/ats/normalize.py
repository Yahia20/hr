"""Readable Arabic repair plus conservative matching normalization.

PDF text can be stored in logical order or in the visual order painted on the
page. Presentation-form code points reveal shaping, not ordering, so they are
never by themselves a reason to reverse a line. Instead, this module builds a
small set of plausible candidates and changes the source only when Arabic
lexical and phrase evidence gives a clear winner.
"""
from dataclasses import dataclass
from functools import lru_cache
import re
import unicodedata


_FORMS = re.compile(r"[\ufb50-\ufdff\ufe70-\ufeff]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_MARKS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06edـ]")
_BIDI = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_TRANSLATION = str.maketrans(
    "أإآٱةى٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "ااااهي01234567890123456789",
)
_SPACED_LATIN = re.compile(r"(?<![A-Za-z])([A-Za-z](?:[ \u00a0]+[A-Za-z]){1,})(?![A-Za-z])")
_COLUMN_BREAK = re.compile(r"(?:\t+| {3,})")

# Ordering vocabulary only; skill matching always uses taxonomy.py.
_AR_WORDS = set("""
الخبرة الخبرات المهنية العملية العمل الوظيفة الوظائف التعليم المؤهلات المؤهل
الدراسة الجامعي الجامعة الكلية بكالوريوس ماجستير دكتوراه دبلوم الثانوية
المهارات مهارات اللغات اللغة العربية الانجليزية الإنجليزية البيانات الشخصية
المعلومات الاتصال الهاتف البريد الالكتروني الإلكتروني العنوان المدينة الجنسية
الهدف الملخص السيرة الذاتية الدورات الشهادات التدريب المراجع حتى الان الآن
من الى إلى في على مع لدى شركة مؤسسة مدير مسؤول موظف خدمة العملاء سنوات سنة
حجز حجوزات الطيران التذاكر السفر السياحة التأشيرات التسويق الموارد البشرية
الحالية السابق سابقا حاليا اجادة رخصة قيادة قابلة نقل الكفالة
""".split())
_AR_PHRASES = (
    "الخبرة المهنية", "الخبرات المهنية", "الخبرة العملية", "المؤهلات العلمية",
    "المهارات الشخصية", "المهارات التقنية", "البيانات الشخصية", "معلومات الاتصال",
    "البريد الالكتروني", "خدمة العملاء", "الموارد البشرية", "حتى الان",
    "حجز التذاكر", "حجوزات الطيران", "رخصة قيادة", "نقل الكفالة",
)
_HEADING_WORDS = {
    "الخبرة", "الخبرات", "التعليم", "المؤهلات", "المهارات", "اللغات",
    "البيانات", "المعلومات", "الدورات", "الشهادات", "المراجع", "الهدف", "الملخص",
}
_AR_WORDS = {word.translate(_TRANSLATION) for word in _AR_WORDS}
_AR_PHRASES = tuple(phrase.translate(_TRANSLATION) for phrase in _AR_PHRASES)
_HEADING_WORDS = {word.translate(_TRANSLATION) for word in _HEADING_WORDS}


@dataclass(frozen=True)
class NormalizedText:
    """Both text views and a stable map from output lines to source lines."""

    readable_text: str
    matching_text: str
    readable_lines: list[str]
    matching_lines: list[str]
    line_map: list[int]


def _join_spaced_latin(text: str) -> str:
    return _SPACED_LATIN.sub(lambda match: re.sub(r"[ \u00a0]+", "", match.group(1)), text)


def _reverse_arabic_letters(text: str) -> str:
    return re.sub(r"[\u0600-\u06ff]+", lambda match: match.group(0)[::-1], text)


def _units(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9@.+/_-]+|[\u0600-\u06ff]+|[^\w\s]|[^\s]", text)
    units: list[str] = []
    latin: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[A-Za-z0-9@.+/_-]+", token):
            latin.append(token)
            continue
        if latin:
            units.append(" ".join(latin))
            latin = []
        units.append(token)
    if latin:
        units.append(" ".join(latin))
    return units


def _reverse_units(text: str) -> str:
    mirrored = str.maketrans({"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "«": "»", "»": "«"})
    return " ".join(reversed(_units(text))).translate(mirrored)


def _plain_arabic(text: str) -> str:
    text = _MARKS.sub("", text.translate(_TRANSLATION)).lower()
    return re.sub(r"\s+", " ", text).strip()


def _order_score(text: str) -> float:
    plain = _plain_arabic(text)
    words = re.findall(r"[\u0600-\u06ff]+", plain)
    score = sum(2.0 for word in words if word in _AR_WORDS)
    score += sum(5.0 for phrase in _AR_PHRASES if phrase in plain)
    if words and words[0] in _HEADING_WORDS:
        score += 2.0
    if re.match(r"^[\u0600-\u06ff ]+\s*[:：]", plain):
        score += 1.0
    score -= sum(0.5 for word in words if len(word) > 3 and (word.startswith("ة") or word.endswith("لا")))
    return score


def _repair_segment(segment: str, had_forms: bool) -> str:
    base = re.sub(r"\s+", " ", segment).strip()
    if not _ARABIC.search(base):
        return base
    candidates = [base, _reverse_units(base)]
    if had_forms:
        chars = _reverse_arabic_letters(base)
        candidates.extend([chars, _reverse_units(chars)])
    unique = list(dict.fromkeys(candidates))
    ranked = sorted(
        enumerate(unique),
        key=lambda item: (_order_score(item[1]), -item[0]),
        reverse=True,
    )
    best_index, best = ranked[0]
    base_score = _order_score(base)
    if best_index and _order_score(best) >= base_score + 2.0:
        return re.sub(r"\s+([,.;:!?،؛])", r"\1", best).strip()
    return base


def readable_line(source: str) -> str:
    """Return displayable logical-order text for one extracted source line."""
    had_forms = bool(_FORMS.search(source))
    line = unicodedata.normalize("NFKC", source)
    line = _join_spaced_latin(_BIDI.sub("", line))
    columns = _COLUMN_BREAK.split(line)
    repaired = [_repair_segment(column, had_forms) for column in columns]
    return "   ".join(part for part in repaired if part).strip()


def matching_line(readable: str) -> str:
    """Aggressive, lossy normalization used only for matching."""
    line = unicodedata.normalize("NFKC", readable).lower().translate(_TRANSLATION)
    line = _MARKS.sub("", _BIDI.sub("", line))
    line = re.sub(
        r"([\u0600-\u06ff])([a-z])|([a-z])([\u0600-\u06ff])",
        lambda match: " ".join(value for value in match.groups() if value),
        line,
    )
    return re.sub(r"\s+", " ", line).strip()


def prepare_text(text: str) -> NormalizedText:
    readable_lines: list[str] = []
    matching_lines: list[str] = []
    line_map: list[int] = []
    for source_index, source in enumerate(text.splitlines()):
        readable = readable_line(source)
        readable_lines.append(readable)
        matching_lines.append(matching_line(readable))
        line_map.append(source_index)
    return NormalizedText(
        readable_text="\n".join(readable_lines),
        matching_text="\n".join(matching_lines),
        readable_lines=readable_lines,
        matching_lines=matching_lines,
        line_map=line_map,
    )


def normalize_lines(text: str) -> list[str]:
    """Compatibility helper: matching-normalized lines with stable indices."""
    return prepare_text(text).matching_lines


def normalize(text: str) -> str:
    return " ".join(line for line in normalize_lines(text) if line)


@lru_cache(maxsize=1024)
def _term_pattern(term: str) -> re.Pattern:
    normalized_term = matching_line(readable_line(term))
    prefix = r"(?:[وفبلك])?" if normalized_term and _ARABIC.match(normalized_term) else ""
    return re.compile(r"(?<!\w)" + prefix + re.escape(normalized_term) + r"(?!\w)")


def contains(line: str, term: str) -> bool:
    return bool(_term_pattern(term).search(line))

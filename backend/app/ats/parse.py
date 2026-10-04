"""Deterministic CV field extraction with line-level evidence."""
from dataclasses import asdict, dataclass, field
from datetime import date
from functools import lru_cache
import re
from typing import Optional

from .normalize import contains, matching_line, prepare_text
from .taxonomy import SKILLS


EDUCATION_ORDINAL = {"high_school": 1, "diploma": 2, "bachelor": 3, "master": 4, "phd": 5}


@dataclass(frozen=True)
class Evidence:
    term: str
    line: str
    source_line: int


@dataclass
class SkillMatch:
    id: str
    canonical: str
    category: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class ParsedCV:
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    years_experience: Optional[float]
    education: Optional[str]
    education_ordinal: Optional[int]
    languages: list[str]
    skills: list[SkillMatch]
    sections: dict[str, list[str]]
    readable_text: str
    normalized_text: str
    line_map: list[int]
    language_evidence: dict[str, list[Evidence]] = field(default_factory=dict)
    education_evidence: list[Evidence] = field(default_factory=list)
    experience_evidence: list[Evidence] = field(default_factory=list)
    nationality: Optional[str] = None
    city: Optional[str] = None
    willing_to_relocate: Optional[bool] = None
    driving_licence: Optional[bool] = None
    transferable_iqama: Optional[bool] = None

    def to_dict(self):
        return asdict(self)


_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
_PHONE_CANDIDATE = re.compile(r"(?<!\d)(?:\+|00)?\d[\d\s().-]{6,}\d(?!\d)")

_SECTION_HEADINGS = {
    "experience": {"experience", "work experience", "professional experience", "employment history", "career history", "الخبره", "الخبرات", "الخبره المهنيه", "الخبره العمليه", "الخبرات المهنيه", "الخبرات العمليه", "الخبره الوظيفيه", "الخبرات الوظيفيه", "التاريخ الوظيفي"},
    "education": {"education", "academic qualifications", "qualifications", "academic background", "التعليم", "المؤهلات", "المؤهلات العلميه", "التحصيل العلمي"},
    "skills": {"skills", "technical skills", "core skills", "competencies", "المهارات", "المهارات التقنيه", "المهارات الشخصيه"},
    "languages": {"languages", "language skills", "اللغات", "المهارات اللغويه"},
    "contact": {"contact", "contact details", "personal information", "personal details", "معلومات الاتصال", "البيانات الشخصيه"},
    "certifications": {"certifications", "courses", "training", "الشهادات", "الدورات", "التدريب"},
    "summary": {"summary", "profile", "objective", "professional summary", "الملخص", "الملخص المهني", "الهدف الوظيفي", "نبذه", "نبذه عني"},
    "references": {"references", "المراجع"},
}

_EDUCATION_ALIASES = {
    "phd": ("phd", "ph.d", "doctorate", "doctoral", "دكتوراه"),
    "master": ("master", "masters", "msc", "m.sc", "mba", "ماجستير"),
    "bachelor": ("bachelor", "bachelors", "bsc", "b.sc", "ba degree", "جامعي", "بكالوريوس", "ليسانس"),
    "diploma": ("diploma", "associate degree", "دبلوم"),
    "high_school": ("high school", "secondary school", "secondary certificate", "الثانويه", "الثانويه العامه"),
}

_LANGUAGES = {
    "Arabic": ("arabic", "اللغه العربيه", "العربيه"),
    "English": ("english", "اللغه الانجليزيه", "الانجليزيه"),
    "French": ("french", "francais", "الفرنسيه"),
    "German": ("german", "الالمانيه"),
    "Urdu": ("urdu", "الاوردو"),
    "Hindi": ("hindi", "الهنديه"),
}

_MONTHS = {
    "january": 1, "jan": 1, "يناير": 1, "كانون الثاني": 1,
    "february": 2, "feb": 2, "فبراير": 2, "شباط": 2,
    "march": 3, "mar": 3, "مارس": 3, "اذار": 3,
    "april": 4, "apr": 4, "ابريل": 4, "نيسان": 4,
    "may": 5, "مايو": 5, "ايار": 5,
    "june": 6, "jun": 6, "يونيو": 6, "حزيران": 6,
    "july": 7, "jul": 7, "يوليو": 7, "تموز": 7,
    "august": 8, "aug": 8, "اغسطس": 8, "اب": 8,
    "september": 9, "sep": 9, "sept": 9, "سبتمبر": 9, "ايلول": 9,
    "october": 10, "oct": 10, "اكتوبر": 10, "تشرين الاول": 10,
    "november": 11, "nov": 11, "نوفمبر": 11, "تشرين الثاني": 11,
    "december": 12, "dec": 12, "ديسمبر": 12, "كانون الاول": 12,
}
_MONTH_PATTERN = "|".join(sorted((re.escape(month) for month in _MONTHS), key=len, reverse=True))
_PRESENT_ALIASES = (
    "until now", "till now", "till date", "to date", "presently", "present",
    "current", "ongoing", "now", "حتى تاريخه", "حتي تاريخه", "حتى الآن",
    "حتي الان", "إلى الآن", "الي الان", "الآن", "الان", "حاليا", "مستمر",
)
# Whole words only: "present" must not fire inside "presentations" or
# "representative", nor "الان" inside "والانصراف".
_PRESENT_PATTERN = r"(?<!\w)(?:" + "|".join(
    sorted((re.escape(matching_line(value)) for value in _PRESENT_ALIASES), key=len, reverse=True)
) + r")(?!\w)"
_ENDPOINT = rf"(?:({_MONTH_PATTERN})\s*[,./-]?\s*((?:19|20)\d{{2}})|((?:0?[1-9]|1[0-2]))[./-]((?:19|20)\d{{2}})|((?:19|20)\d{{2}})[./-]((?:0?[1-9]|1[0-2]))|((?:19|20)\d{{2}})|{_PRESENT_PATTERN})"
_DATE_RANGE = re.compile(
    rf"(?P<start>{_ENDPOINT})(?:\s*(?:-|–|—|/|\bto\b|\btill\b|\bthrough\b|\buntil\b|الي|حتي(?!\s+الان))\s*|\s+(?={_PRESENT_PATTERN}))(?P<end>{_ENDPOINT})",
    re.I,
)
_SIMPLE_YEAR_RANGE = re.compile(r"(?P<start>(?:19|20)\d{2})\s*[-–—/:]\s*(?P<end>(?:19|20)\d{2})")
_OPEN_RANGE_TAIL = re.compile(
    rf"\s*(?:-|–|—|\bto\b|\btill\b|\buntil\b|\bthrough\b|الي|حتي)\s*(?P<month>{_MONTH_PATTERN})?\s*$", re.I
)
_SINCE_DATE = re.compile(rf"(?:\bsince\b|منذ)\s*(?P<start>{_ENDPOINT})", re.I)

_EMPLOYMENT_CUES = re.compile(
    r"\b(?:experience|employment|work history|career|company|employer|manager|supervisor|"
    r"agent|officer|consultant|specialist|accountant|representative|coordinator|engineer|"
    r"analyst|developer|sales|reservation|ticketing|travel|tourism|airline|hotel|branch)\b|"
    r"خبر|عمل|وظيف|شركة|مؤسسة|مدير|مشرف|موظف|مسؤول|محاسب|مندوب|مبيعات|حجوزات|"
    r"تذاكر|سفر|سياحة|طيران|فندق|فرع"
)
_EDUCATION_CUES = re.compile(
    r"\b(?:education|academic|university|faculty|college|school|bachelor|master|phd|diploma|degree)\b|"
    r"تعليم|دراس|جامع|كلية|مدرسة|بكالور|ماجستير|دكتوراه|دبلوم|ثانوي|مؤهل"
)
_COURSE_CUES = re.compile(
    r"\b(?:course|certificate|certification|training|workshop|project)\b|"
    r"دورة|دورات|شهادة|شهادات|تدريب|ورشة|مشروع|مشروعات"
)
_BIRTH_CUES = re.compile(r"\b(?:birth|born|dob|date of birth)\b|ميلاد|مولود")


@lru_cache(maxsize=512)
def _normalized_alias(alias: str) -> str:
    return matching_line(alias)


def _one_edit_or_transposition(left: str, right: str) -> bool:
    """True for one edit, including one adjacent transposition."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        if len(differences) == 1:
            return True
        return (len(differences) == 2 and differences[1] == differences[0] + 1
                and left[differences[0]] == right[differences[1]]
                and left[differences[1]] == right[differences[0]])
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    for index in range(len(longer)):
        if longer[:index] + longer[index + 1:] == shorter:
            return True
    return False


@lru_cache(maxsize=128)
def _skill_pattern(aliases: tuple[str, ...]) -> re.Pattern:
    alternatives = []
    for alias in aliases:
        normalized = _normalized_alias(alias)
        prefix = r"(?:[وفبلك])?" if re.match(r"[\u0600-\u06ff]", normalized) else ""
        alternatives.append(prefix + re.escape(normalized))
    return re.compile(r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)")


def _skill_alias_on_line(line: str, aliases: tuple[str, ...], *, fuzzy: bool = False) -> Optional[str]:
    exact = _skill_pattern(aliases).search(line)
    if exact or not fuzzy:
        return exact.group(0) if exact else None
    # RTL PDF extraction occasionally swaps two adjacent glyphs inside an
    # Arabic product name.  Restrict fuzzy recovery to long Arabic aliases and
    # one edit so ordinary short words cannot become skill matches.
    words = re.findall(r"[\u0600-\u06ff]+", line)
    for alias in aliases:
        normalized = _normalized_alias(alias)
        if len(normalized) < 6 or not re.fullmatch(r"[\u0600-\u06ff]+", normalized):
            continue
        if any(_one_edit_or_transposition(word, normalized) for word in words):
            return alias
    return None


def _heading(line: str) -> Optional[str]:
    cleaned = re.sub(r"[^\w\s]", " ", line)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for section, headings in _SECTION_HEADINGS.items():
        if cleaned in headings:
            return section
    return None


def _sections(lines: list[str], readable_lines: list[str]) -> tuple[dict[str, list[str]], list[Optional[str]]]:
    result: dict[str, list[str]] = {}
    assignments: list[Optional[str]] = [None] * len(lines)
    current: Optional[str] = None
    for index, line in enumerate(lines):
        found = _heading(line)
        if found:
            current = found
            result.setdefault(found, [])
            assignments[index] = found
        elif current is not None:
            result[current].append(readable_lines[index])
            assignments[index] = current
    return result, assignments


def _extract_phone(readable_lines: list[str], matching_lines: list[str]) -> Optional[str]:
    candidates: list[tuple[int, str]] = []
    for readable, normalized in zip(readable_lines, matching_lines):
        digits_line = normalized.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        labelled = bool(re.search(r"\b(phone|mobile|tel|contact)\b|هاتف|جوال|موبايل", normalized))
        for match in _PHONE_CANDIDATE.finditer(digits_line):
            raw = match.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            has_plus = raw.startswith("+") or raw.startswith("00")
            score = 3 if labelled else 0
            formatted: Optional[str] = None
            if digits.startswith("00966") and len(digits) == 14:
                formatted, score = "+" + digits[2:], score + 4
            elif digits.startswith("966") and len(digits) == 12:
                formatted, score = "+" + digits, score + 4
            elif digits.startswith("05") and len(digits) == 10:
                formatted, score = "+966" + digits[1:], score + 4
            elif digits.startswith("0020") and len(digits) == 15:
                formatted, score = "+" + digits[2:], score + 4
            elif digits.startswith("20") and len(digits) == 12:
                formatted, score = "+" + digits, score + 4
            elif digits.startswith("01") and len(digits) == 11:
                formatted, score = "+20" + digits[1:], score + 4
            elif has_plus and 8 <= len(digits.removeprefix("00")) <= 15:
                formatted = "+" + digits.removeprefix("00")
                score += 2
            elif labelled and 8 <= len(digits) <= 15:
                formatted = digits
                score += 1
            if formatted:
                candidates.append((score, formatted))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _extract_name(readable_lines: list[str], matching_lines: list[str]) -> Optional[str]:
    rejected = {heading for headings in _SECTION_HEADINGS.values() for heading in headings}
    for readable, normalized in zip(readable_lines[:12], matching_lines[:12]):
        value = readable.strip(" :-|•\t")
        words = re.findall(r"[A-Za-z\u0600-\u06ff'-]+", value)
        if not value or not 2 <= len(words) <= 6:
            continue
        if any(char.isdigit() for char in value) or "@" in value or _heading(normalized):
            continue
        if normalized in rejected or re.search(r"\b(cv|resume|curriculum vitae)\b|السيره الذاتيه", normalized):
            continue
        if len("".join(words)) >= 5:
            return value
    return None


def _endpoint_value(value: str, reference_date: Optional[date] = None) -> Optional[int]:
    value = re.sub(r"[,]+", " ", value.lower()).strip()
    reference_date = reference_date or date.today()
    if any(value == matching_line(alias) for alias in _PRESENT_ALIASES):
        return reference_date.year * 12 + reference_date.month - 1
    year_match = re.search(r"(?:19|20)\d{2}", value)
    if not year_match:
        return None
    year = int(year_match.group(0))
    month = 1
    for name, number in _MONTHS.items():
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", value):
            month = number
            break
    else:
        numeric_month = re.search(r"(?<!\d)(0?[1-9]|1[0-2])[./-](?:19|20)\d{2}", value)
        if numeric_month:
            month = int(numeric_month.group(1))
        else:
            year_first = re.search(r"(?:19|20)\d{2}[./-](0?[1-9]|1[0-2])(?!\d)", value)
            if year_first:
                month = int(year_first.group(1))
    return year * 12 + month - 1


def _cue_counts(lines: list[str], start: int, end: int) -> tuple[int, int, int, int]:
    context = " ".join(lines[max(0, start):min(len(lines), end)])
    return (
        len(_EMPLOYMENT_CUES.findall(context)),
        len(_EDUCATION_CUES.findall(context)),
        len(_COURSE_CUES.findall(context)),
        len(_BIRTH_CUES.findall(context)),
    )


def _employment_date_line(index: int, lines: list[str], assignments: list[Optional[str]]) -> bool:
    line = lines[index]
    direct_emp, direct_edu, direct_course, direct_birth = _cue_counts(lines, index, index + 1)
    nearby_emp, nearby_edu, nearby_course, nearby_birth = _cue_counts(lines, index - 2, index + 3)
    if direct_birth or (direct_edu + direct_course > direct_emp):
        return False
    section = assignments[index]
    if section in {"contact", "references"}:
        return False
    if section == "experience":
        return not (nearby_birth or (nearby_edu >= 2 and nearby_emp == 0))
    if section in {"education", "certifications"}:
        return nearby_emp >= 2 and nearby_edu == 0 and nearby_course == 0 and nearby_birth == 0
    return nearby_emp >= 1 and nearby_emp >= nearby_edu and nearby_course == 0 and nearby_birth == 0


def _valid_interval(start: Optional[int], end: Optional[int], reference_month: int) -> Optional[tuple[int, int]]:
    if start is None or end is None:
        return None
    if start > end:
        start, end = end, start  # visually ordered RTL date columns
    if start < 1950 * 12 or start > reference_month + 12 or end > reference_month + 12:
        return None
    return start, min(end, reference_month)


def _experience(
    lines: list[str],
    readable_lines: list[str],
    assignments: list[Optional[str]],
    reference_date: date,
) -> tuple[Optional[float], list[Evidence]]:
    evidence: list[Evidence] = []
    intervals: list[tuple[int, int]] = []
    fallback_years: list[float] = []
    reference_month = reference_date.year * 12 + reference_date.month - 1
    consumed_lines: set[int] = set()

    # Scan every line because PDF columns often place employment rows after a
    # different heading. Context must identify employment; section labels alone
    # are neither sufficient nor necessary.
    for index, line in enumerate(lines):
        if not _employment_date_line(index, lines, assignments):
            continue
        matches = list(_DATE_RANGE.finditer(line))
        if not matches:
            matches = list(_SIMPLE_YEAR_RANGE.finditer(line))
        for match in matches:
            interval = _valid_interval(
                _endpoint_value(match.group("start"), reference_date),
                _endpoint_value(match.group("end"), reference_date),
                reference_month,
            )
            if interval and interval[0] < interval[1]:
                intervals.append(interval)
                evidence.append(Evidence(match.group(0), readable_lines[index], index))
                consumed_lines.add(index)
        for match in _SINCE_DATE.finditer(line):
            interval = _valid_interval(
                _endpoint_value(match.group("start"), reference_date), reference_month, reference_month
            )
            if interval and interval[0] < interval[1]:
                intervals.append(interval)
                evidence.append(Evidence(match.group(0), readable_lines[index], index))
                consumed_lines.add(index)

    # Pair endpoints split over separate rows/columns. A present marker belongs
    # to the chronologically latest unmatched start; remaining endpoints pair
    # in extracted order. Pair-level context rejects academic/project blocks.
    endpoints: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        if index in consumed_lines or assignments[index] in {"contact", "references", "certifications", "education"}:
            continue
        for match in re.finditer(_ENDPOINT, line, re.I):
            value = _endpoint_value(match.group(0), reference_date)
            if value is None or not 1950 * 12 <= value <= reference_month:
                continue
            direct = _cue_counts(lines, index, index + 1)
            nearby = _cue_counts(lines, index - 2, index + 3)
            is_present = value == reference_month and not re.search(r"(?:19|20)\d{2}", match.group(0))
            if is_present and any(end == reference_month for _, end in intervals):
                continue
            plausible = _employment_date_line(index, lines, assignments)
            if is_present and assignments[index] not in {"education", "certifications"}:
                plausible = plausible or nearby[0] > 0 or assignments[index] in {"experience", "skills"}
            if plausible and not direct[3]:
                endpoints.append((value, index, match.group(0)))

    used: set[int] = set()
    # An open range ("From June 2019 to March" + "2022" on the next row) names
    # its own end: pair it with the next endpoint before any order-based pairing,
    # so a stray year elsewhere cannot shift every later pair.
    for pos, (value, index, term) in enumerate(endpoints):
        if pos in used or value == reference_month or pos + 1 >= len(endpoints):
            continue
        tail = lines[index][lines[index].find(term) + len(term):]
        opener = _OPEN_RANGE_TAIL.match(tail)
        next_value, next_index, next_term = endpoints[pos + 1]
        if not opener or pos + 1 in used or not 0 < next_index - index <= 3:
            continue
        end_value = next_value
        if opener.group("month") and re.fullmatch(r"(?:19|20)\d{2}", next_term.strip()):
            end_value = int(next_term) * 12 + _MONTHS[opener.group("month")] - 1
        interval = _valid_interval(value, end_value, reference_month)
        if interval and interval[0] < interval[1]:
            intervals.append(interval)
            evidence.extend([
                Evidence(term, readable_lines[index], index),
                Evidence(next_term, readable_lines[next_index], next_index),
            ])
            used.update({pos, pos + 1})

    for present_pos, (value, index, term) in enumerate(endpoints):
        if value != reference_month or present_pos in used:
            continue
        candidates = [
            (candidate_value, pos, candidate_index, candidate_term)
            for pos, (candidate_value, candidate_index, candidate_term) in enumerate(endpoints)
            if pos not in used and pos != present_pos and candidate_value < reference_month
        ]
        if not candidates:
            continue
        start, start_pos, start_index, start_term = max(candidates, key=lambda item: item[0])
        emp, edu, course, birth = _cue_counts(lines, min(index, start_index) - 2, max(index, start_index) + 3)
        if birth or (edu >= 2 and emp == 0) or (course >= 2 and emp == 0):
            continue
        intervals.append((start, reference_month))
        evidence.extend([
            Evidence(start_term, readable_lines[start_index], start_index),
            Evidence(term, readable_lines[index], index),
        ])
        used.update({present_pos, start_pos})

    remaining = [(pos, item) for pos, item in enumerate(endpoints) if pos not in used and item[0] != reference_month]
    for pair_index in range(0, len(remaining) - 1, 2):
        (left_pos, (left, left_index, left_term)), (right_pos, (right, right_index, right_term)) = remaining[pair_index:pair_index + 2]
        if abs(right_index - left_index) > 8:
            continue
        emp, edu, course, birth = _cue_counts(lines, min(left_index, right_index) - 2, max(left_index, right_index) + 3)
        if birth or (edu >= 2 and emp == 0) or (course >= 2 and emp == 0):
            continue
        interval = _valid_interval(left, right, reference_month)
        if interval and interval[0] < interval[1]:
            intervals.append(interval)
            evidence.extend([
                Evidence(left_term, readable_lines[left_index], left_index),
                Evidence(right_term, readable_lines[right_index], right_index),
            ])

    # Explicit totals remain a fallback from the plan, but never override real
    # date ranges and must occur in an employment/summary context.
    if not intervals:
        word_years = {
            "one year": 1, "two years": 2, "three years": 3, "four years": 4,
            "five years": 5, "ten years": 10, "سنتين": 2, "ثلاث سنوات": 3,
            "اربع سنوات": 4, "خمس سنوات": 5, "عشر سنوات": 10,
        }
        for index, line in enumerate(lines):
            if assignments[index] not in {"experience", "summary"} and not _employment_date_line(index, lines, assignments):
                continue
            for explicit in re.finditer(r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*(?:\+\s*)?(?:years?|yrs?|سنوات|سنه|عام|اعوام)(?!\w)", line, re.I):
                value = float(explicit.group(1))
                if value <= 50:
                    fallback_years.append(value)
                    evidence.append(Evidence(explicit.group(0), readable_lines[index], index))
            for phrase, value in word_years.items():
                if contains(line, phrase):
                    fallback_years.append(float(value))
                    evidence.append(Evidence(phrase, readable_lines[index], index))

    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    ranged = sum(end - start for start, end in merged) / 12 if merged else 0.0
    years = max([ranged, *fallback_years], default=0.0)
    return (round(years, 1) if years else None), evidence


def _label_value(lines: list[str], labels: str) -> Optional[str]:
    pattern = re.compile(rf"(?:^|\b)(?:{labels})\s*[:：-]\s*(.+)$", re.I)
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(1).strip(" ,;|.") or None
    return None


def parse_cv(text: str, reference_date: Optional[date] = None) -> ParsedCV:
    """Parse a CV without I/O, network calls, or probabilistic models."""
    reference_date = reference_date or date.today()
    prepared = prepare_text(text)
    lines = prepared.matching_lines
    readable_lines = prepared.readable_lines
    sections, assignments = _sections(lines, readable_lines)

    email_match = _EMAIL.search(prepared.readable_text)
    email = email_match.group(0).lower() if email_match else None
    phone = _extract_phone(readable_lines, lines)
    name = _extract_name(readable_lines, lines)
    years, experience_evidence = _experience(lines, readable_lines, assignments, reference_date)

    education: Optional[str] = None
    education_evidence: list[Evidence] = []
    for level, aliases in _EDUCATION_ALIASES.items():
        for index, line in enumerate(lines):
            alias = next((alias for alias in aliases if contains(line, alias)), None)
            if alias:
                evidence = Evidence(alias, readable_lines[index], index)
                if education is None or EDUCATION_ORDINAL[level] > EDUCATION_ORDINAL[education]:
                    education = level
                    education_evidence = [evidence]
                elif level == education:
                    education_evidence.append(evidence)

    languages: list[str] = []
    language_evidence: dict[str, list[Evidence]] = {}
    for language, aliases in _LANGUAGES.items():
        found: list[Evidence] = []
        for index, line in enumerate(lines):
            alias = next((alias for alias in aliases if contains(line, alias)), None)
            if alias:
                found.append(Evidence(alias, readable_lines[index], index))
        if found:
            languages.append(language)
            language_evidence[language] = found

    skill_matches: list[SkillMatch] = []
    for skill in SKILLS:
        aliases = tuple(sorted(skill["aliases"], key=len, reverse=True))
        found: list[Evidence] = []
        for index, line in enumerate(lines):
            alias = _skill_alias_on_line(line, aliases, fuzzy=skill["id"] == "amadeus")
            if alias:
                found.append(Evidence(alias, readable_lines[index], index))
        if found:
            skill_matches.append(SkillMatch(skill["id"], skill["canonical"], skill["category"], found))

    nationality = _label_value(lines, r"nationality|الجنسيه")
    city = _label_value(lines, r"city|location|address|المدينه|العنوان")
    relocate_positive = any(re.search(r"willing to relocate|open to relocation|قابل للانتقال|استعداد للانتقال", line) for line in lines)
    relocate_negative = any(re.search(r"not willing to relocate|غير قابل للانتقال", line) for line in lines)
    willing_to_relocate = False if relocate_negative else True if relocate_positive else None
    licence_positive = any(re.search(r"driving licen[cs]e|driver.?s licen[cs]e|رخصه قياده", line) for line in lines)
    licence_negative = any(re.search(r"no driving licen[cs]e|without.*driving licen[cs]e|لا (?:املك|يوجد).*رخصه", line) for line in lines)
    driving_licence = False if licence_negative else True if licence_positive else None
    iqama_positive = any(re.search(r"transferable iqama|iqama transferable|اقامه قابله للنقل|نقل الكفاله", line) for line in lines)
    iqama_negative = any(re.search(r"non.?transferable iqama|اقامه غير قابله للنقل", line) for line in lines)
    transferable_iqama = False if iqama_negative else True if iqama_positive else None

    return ParsedCV(
        name=name,
        email=email,
        phone=phone,
        years_experience=years,
        education=education,
        education_ordinal=EDUCATION_ORDINAL.get(education) if education else None,
        languages=languages,
        skills=skill_matches,
        sections=sections,
        readable_text=prepared.readable_text,
        normalized_text=prepared.matching_text,
        line_map=prepared.line_map,
        language_evidence=language_evidence,
        education_evidence=education_evidence,
        experience_evidence=experience_evidence,
        nationality=nationality,
        city=city,
        willing_to_relocate=willing_to_relocate,
        driving_licence=driving_licence,
        transferable_iqama=transferable_iqama,
    )

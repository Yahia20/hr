"""Local Phase 1 evaluator. Prints to stdout and never writes files."""
from argparse import ArgumentParser
import logging
from pathlib import Path
import sys
from time import perf_counter

# Allow ``python scripts/ats_eval.py`` without installing the project.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ats.extract import extract_text  # noqa: E402
from app.ats.parse import parse_cv  # noqa: E402
from app.ats.role_templates import ROLE_TEMPLATES  # noqa: E402
from app.ats.score import score  # noqa: E402

logging.getLogger("pypdf").setLevel(logging.ERROR)


HEADERS = [
    "file", "pages", "extract_ms", "rules_ms", "email", "phone", "education",
    "years", "languages", "top_skills", "best_template", "score", "needs_review",
]


def _render(rows: list[list[str]]) -> None:
    widths = [len(header) for header in HEADERS]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = min(42, max(widths[index], len(value)))

    def line(values):
        return " | ".join(value[:widths[index]].ljust(widths[index]) for index, value in enumerate(values))

    print(line(HEADERS))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(line(row))


def evaluate(folder: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    paths = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".pdf", ".docx", ".txt"}
    )
    for path in paths:
        extract_started = perf_counter()
        extracted = extract_text(path.read_bytes(), path.name)
        extract_ms = (perf_counter() - extract_started) * 1000

        rules_started = perf_counter()
        parsed = parse_cv(extracted.text)
        results = [(template, score(parsed, template)) for template in ROLE_TEMPLATES]
        best_template, best_result = max(results, key=lambda item: item[1].rules_score)
        rules_ms = (perf_counter() - rules_started) * 1000

        rows.append([
            path.name,
            str(extracted.pages),
            f"{extract_ms:.1f}",
            f"{rules_ms:.1f}",
            parsed.email or "-",
            parsed.phone or "-",
            parsed.education or "-",
            f"{parsed.years_experience:.1f}" if parsed.years_experience is not None else "-",
            ", ".join(parsed.languages) or "-",
            ", ".join(skill.canonical for skill in parsed.skills[:6]) or "-",
            best_template["title"],
            str(best_result.rules_score),
            "yes" if extracted.needs_manual_review else "no",
        ])
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error(f"not a folder: {args.folder}")
    _render(evaluate(args.folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

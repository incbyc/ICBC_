#!/usr/bin/env python3
"""
Parse ICBC 'Of The Month' questionnaire Word files and update supabase/seed/staff.csv.

Extracts Pastor, Preschool Teacher, and Compassionate Care sections; builds narrative
descriptions from each person's answers; merges into staff.csv (upsert by site_slug + name + role).
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
QUESTIONNAIRES_DIR = ROOT / "Questionnaires"
STAFF_CSV = ROOT / "supabase" / "seed" / "staff.csv"
SITES_CSV = ROOT / "supabase" / "seed" / "icbc_sites.csv"
REPORT_PATH = ROOT / "supabase" / "seed" / "questionnaire_import_report.md"

ROLE_PASTOR = "Pastor"
ROLE_TEACHER = "Teacher"
ROLE_CARE = "Compassionate Care"

INVALID_NAME_FRAGMENTS = (
    "preschool teacher",
    "compassionate care",
    "staff member",
    "team member:",
    "answer:",
    "please pray",
    "we have an insufficient",
    "as a preschool teacher",
    "i became a preschool",
    "i enjoy teaching",
)

QUESTION_STARTERS = (
    "what ",
    "how ",
    "in what ",
    "why ",
)

FILENAME_SLUG_OVERRIDES = {
    "ka-ncesi": "kancesi",
    "ka-liba": "kaliba",
    "kaliba": "kaliba",
    "mshaweni": "msahweni",
    "msaweni": "msahweni",
    "esigcaweni": "sigcaweni",
    "pine valley": "pine-valley",
    "pine-valley": "pine-valley",
    "copy of icbc of the month": "",
}

SKIP_ANSWERS = {
    "none",
    "n/a",
    "na",
    "no challenges so far",
    "no challenges noted.",
    "no challenges noted",
}

NEGATIVE_HINTS = (
    "challenge",
    "poverty",
    "unemploy",
    "drug",
    "dagga",
    "theft",
    "witchcraft",
    "absenteeism",
    "struggle",
    "lack of trust",
    "not old enough",
    "not operational",
    "prolonged drought",
    "food security is very low",
    "bad and rough",
    "sexual abuse",
    "teenage pregnanc",
    "double lives",
    "stuck in their old habits",
    "negatively",
    "discouraging",
    "however this is a work in progress",
)

POSITIVE_HINTS = (
    "god",
    "christ",
    "jesus",
    "lord",
    "heal",
    "transform",
    "growth",
    "revival",
    "souls",
    "bless",
    "hope",
    "love",
    "community",
    "children",
    "preschool",
    "rain",
    "harvest",
    "church",
    "prayer",
    "deliverance",
    "faith",
    "joy",
    "protect",
    "miracle",
    "unity",
    "education",
    "calling",
    "passion",
)

FEMALE_FIRST_NAMES = {
    "phumzile",
    "zanele",
    "nobuhle",
    "lindiwe",
    "khanyisile",
    "nomonde",
    "gladys",
    "xolan",
    "nomcebo",
    "gugu",
    "ncamsile",
    "happiness",
    "bongiwe",
    "fisiwe",
    "nozipho",
    "nonduduzo",
    "nokuthula",
    "nomthandazo",
    "kholiwe",
    "celiwe",
    "philile",
    "cebsile",
    "thembisa",
    "gladys",
    "phindile",
    "semusa",
    "tandzile",
    "busi",
    "thandiwe",
    "nothando",
    "londiwe",
    "nelile",
    "mayibongwe",
    "lungile",
    "gabsile",
    "bongiwe",
    "nomcebo",
    "chamukile",
    "slindile",
    "zelamile",
    "kayise",
    "sebenele",
    "zamekile",
    "happiness",
    "fisiwe",
    "nelile",
    "kholiwe",
    "celiwe",
    "nomonde",
}


@dataclass
class StaffMember:
    site_slug: str
    full_name: str
    role: str
    description: str
    year_joined: str = ""
    photo_url: str = ""
    sort_order: str = "0"
    source_file: str = ""


@dataclass
class ParsedQuestionnaire:
    path: Path
    site_slug: str
    pastor: StaffMember | None = None
    teacher: StaffMember | None = None
    care: StaffMember | None = None
    warnings: list[str] = field(default_factory=list)


def slugify(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\u2018\u2019`]", "'", text)
    text = re.sub(r"[\u201c\u201d]", '"', text)
    text = re.sub(r"^(?:answer|response)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def title_case_name(name: str) -> str:
    name = clean_text(name)
    name = re.sub(r"^(mrs?|mr|ms|dr)\.?\s+", "", name, flags=re.I)
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if not name or len(name) < 2:
        return ""
    if name.isupper() and len(name) > 3:
        return name.title()
    parts = []
    for word in name.split():
        if "-" in word:
            parts.append("-".join(p.capitalize() for p in word.split("-")))
        else:
            parts.append(word.capitalize())
    return " ".join(parts)


def is_valid_person_name(name: str) -> bool:
    if not name:
        return False
    if len(name) > 55 or len(name.split()) > 7:
        return False
    low = name.lower()
    if any(fragment in low for fragment in INVALID_NAME_FRAGMENTS):
        return False
    if low.endswith(":"):
        return False
    return True


def is_section_break(line: str) -> bool:
    low = line.lower()
    if re.match(r"^pastor\s*:?", line, re.I):
        return True
    if "preschool teacher" in low and "?" not in line:
        return True
    if "compassionate care" in low and "?" not in line:
        return True
    return False


def load_site_slugs() -> dict[str, str]:
    """Map normalised name/slug tokens -> canonical slug."""
    mapping: dict[str, str] = {}
    with SITES_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            slug = row["slug"].strip()
            name = row["name"].strip()
            mapping[slug] = slug
            mapping[slugify(name)] = slug
            mapping[slugify(slug)] = slug
    return mapping


def slug_from_filename(path: Path, site_map: dict[str, str]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    stem = path.stem
    lower = stem.lower()

    for key, slug in FILENAME_SLUG_OVERRIDES.items():
        if key in lower:
            if not slug:
                warnings.append("Generic/duplicate template file — skipped.")
            return slug, warnings

    match = re.search(r"questionnaire[_\s(]*([^).]+)", stem, re.I)
    if match:
        token = slugify(match.group(1))
        if token in site_map:
            return site_map[token], warnings

    prefix = re.split(r"[_\s]+icbc", stem, flags=re.I)[0].strip()
    token = slugify(prefix)
    if token in site_map:
        return site_map[token], warnings

    warnings.append(f"Could not match filename to ICBC slug: {path.name}")
    return "", warnings


def is_question_line(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    if line.endswith("?"):
        return True
    low = line.lower()
    return any(low.startswith(prefix) for prefix in QUESTION_STARTERS)


def extract_name_from_header(line: str, role_pattern: str) -> str:
    line = line.strip()
    match = re.match(rf"^{role_pattern}\s*[:\u2013\-]+\s*(.+)$", line, re.I)
    if not match:
        match = re.match(rf"^{role_pattern}\s*:?\s*(.+)$", line, re.I)
    if match:
        name = clean_text(match.group(1))
        if name.lower() in {"none", "n/a", "na", "-"}:
            return ""
        if len(name) > 80 or "what " in name.lower():
            return ""
        name = title_case_name(name)
        return name if is_valid_person_name(name) else ""
    return ""


def split_section(lines: list[str], start: int, end: int) -> list[str]:
    return [clean_text(line) for line in lines[start:end] if clean_text(line)]


def parse_qa_blocks(section_lines: list[str]) -> list[tuple[str, str]]:
    """Return list of (question, answer) pairs."""
    if not section_lines:
        return []

    # Drop leading name-only line if it doesn't look like a question
    start = 0
    if section_lines and not is_question_line(section_lines[0]):
        if len(section_lines[0].split()) <= 6 and "?" not in section_lines[0]:
            start = 1

    blocks: list[tuple[str, str]] = []
    current_q: str | None = None
    answer_parts: list[str] = []

    def flush() -> None:
        nonlocal current_q, answer_parts
        if current_q and answer_parts:
            blocks.append((current_q, clean_text(" ".join(answer_parts))))
        current_q = None
        answer_parts = []

    for line in section_lines[start:]:
        if is_section_break(line):
            flush()
            break
        if is_question_line(line):
            flush()
            current_q = line
        elif current_q:
            if line.lower() in {"none", "no challenges so far", "no challenges noted."}:
                answer_parts.append(line)
            else:
                answer_parts.append(line)
        elif not blocks and not current_q:
            # preamble before first question (e.g. goals without question detected)
            current_q = "Overview"
            answer_parts.append(line)

    flush()
    return blocks


def subject_pronouns(full_name: str) -> tuple[str, str, str]:
    first = full_name.split()[0].lower() if full_name else ""
    if first in FEMALE_FIRST_NAMES:
        return "She", "Her", "her"
    return "He", "His", "his"


def align_pronouns(description: str, full_name: str) -> str:
    """Match He/His in a bio to the person's name (e.g. pastor row vs questionnaire header)."""
    if not description or not full_name:
        return description
    subj, poss, obj = subject_pronouns(full_name)
    if subj == "She":
        text = description
        text = re.sub(r"\bHe\b", "She", text)
        text = re.sub(r"\bHis\b", "Her", text)
        text = re.sub(r"\bhe\b", "she", text)
        text = re.sub(r"\bhis\b", "her", text)
        text = re.sub(r"\bhim\b", "her", text)
        return text
    if subj == "He":
        text = description
        text = re.sub(r"\bShe\b", "He", text)
        text = re.sub(r"\bHer\b", "His", text)
        text = re.sub(r"\bshe\b", "he", text)
        text = re.sub(r"\bher\b", "his", text)
        return text
    return description


def classify_question(question: str) -> str:
    q = question.lower()
    if "dream" in q or "goal" in q:
        return "vision"
    if "god working" in q or "god moving" in q or "seen god" in q:
        return "impact"
    if "enjoy" in q or "why did you become" in q:
        return "passion"
    if "types of care" in q:
        return "care_work"
    if "challenge" in q or "pray for you" in q:
        return "skip"
    return "other"


def positive_score(text: str) -> int:
    low = text.lower()
    return sum(1 for hint in POSITIVE_HINTS if hint in low)


def is_negative_sentence(text: str) -> bool:
    low = text.lower()
    negatives = sum(1 for hint in NEGATIVE_HINTS if hint in low)
    if negatives >= 2:
        return True
    if negatives >= 1 and positive_score(text) == 0:
        return True
    return False


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", clean_text(text))
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) > 18]


def to_third_person(text: str, subj: str, poss: str, obj: str) -> str:
    text = clean_text(text)
    replacements = [
        (r"\bI'm\b", f"{subj} is"),
        (r"\bI've\b", f"{subj} has"),
        (r"\bI'd\b", f"{subj} would"),
        (r"\bwe've\b", f"{subj} has"),
        (r"\bwe have\b", f"{subj} has"),
        (r"\bwe're\b", f"{subj} is"),
        (r"\bWe\b", subj),
        (r"\bwe\b", subj.lower()),
        (r"\bI\b", subj),
        (r"\bmy\b", poss.lower()),
        (r"\bMe\b", obj),
        (r"\bme\b", obj),
        (r"\bour\b", poss.lower()),
        (r"\bus\b", "the community"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return fix_grammar(text, subj, poss)


def site_phrase(poss: str) -> str:
    return "church" if poss == "His" else "ministry"


def fix_grammar(text: str, subj: str, poss: str) -> str:
    text = clean_text(text)
    rules = [
        (rf"\b{subj} his dream\b", f"{subj} carries a vision"),
        (rf"\b{subj} his goals\b", f"{subj} is working toward goals"),
        (rf"\b{subj} his goal\b", f"{subj} is working toward a goal"),
        (rf"\b{subj} his desire\b", f"{subj} desires"),
        (rf"\b{subj} his dream is\b", f"{subj} carries a vision"),
        (rf"\b{subj} to win\b", f"{subj} hopes to win"),
        (rf"\b{subj} to create\b", f"{subj} hopes to create"),
        (rf"\b{subj} to intentionally\b", f"{subj} seeks to"),
        (rf"\b{subj} have\b", f"{subj} has"),
        (rf"\b{subj} aspire\b", f"{subj} aspires"),
        (rf"\b{subj} pray\b", f"{subj} prays"),
        (rf"\b{subj} desire\b", f"{subj} desires"),
        (rf"\b{subj} enjoy\b", f"{subj} enjoys"),
        (rf"\b{subj} provide\b", f"{subj} provides"),
        (rf"\b{subj} put\b", f"{subj} puts"),
        (rf"\b{subj} do\b", f"{subj} does"),
        (rf"\b{subj} encourage\b", f"{subj} encourages"),
        (rf"\b{subj} trust\b", f"{subj} trusts"),
        (rf"\b{subj} aim\b", f"{subj} aims"),
        (rf"\b{subj} also have\b", f"{subj} also has"),
        (rf"\b{subj} became\b", f"{subj} became"),
        (rf"\b{subj} became a teacher because {subj} enjoys\b", f"{subj} became a teacher because she enjoys"),
        (rf"\b{subj} became a teacher because he enjoys\b", f"{subj} became a teacher because he enjoys"),
        (r"\bthe team has\b", f"{subj} has"),
        (r"\bthe team have\b", f"{subj} has"),
        (r"\bthe team believe\b", f"{subj} believes"),
        (r"\bthe team encourage\b", f"{subj} encourages"),
        (r"\bthe team trust\b", f"{subj} trusts"),
        (r"\bthe team also have\b", f"{subj} also has"),
        (r"\bthe team always\b", f"{subj} always"),
        (r"\bthe team has seen\b", f"{subj} has seen"),
        (r"\bthe team has also seen\b", f"{subj} has also seen"),
        (r"\bthe team has been\b", f"{subj} has been"),
        (r"\bthe team put\b", f"{subj} puts"),
        (r"\bthe team do\b", f"{subj} does"),
        (r"\bHe He\b", "He"),
        (r"\bShe She\b", "She"),
        (r"\bas as\b", "as"),
    ]
    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text, flags=re.I)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def clause_tail(clause: str) -> str:
    clause = clause.strip()
    if not clause:
        return ""
    if clause[0].isupper() and clause.split()[0] in {"He", "She"}:
        parts = clause.split(maxsplit=1)
        if len(parts) == 2:
            return parts[1][0].lower() + parts[1][1:] if parts[1] else ""
    return clause[0].lower() + clause[1:] if clause else ""


def trim_to_length(text: str, max_chars: int = 240) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "."


def pick_positive_sentences(answer: str, limit: int = 2) -> list[str]:
    if not answer or answer.lower() in SKIP_ANSWERS:
        return []

    sentences = split_sentences(answer)
    if not sentences and len(answer) > 30:
        sentences = [answer]

    ranked: list[tuple[int, str]] = []
    for sentence in sentences:
        if is_negative_sentence(sentence):
            continue
        score = positive_score(sentence) + min(len(sentence) // 40, 3)
        if score > 0:
            ranked.append((score, sentence))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _, sentence in ranked[:limit]]


def combined_answer_text(buckets: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for key in ("vision", "passion", "care_work", "impact", "other"):
        parts.extend(buckets.get(key, []))
    return " ".join(parts)


def pastor_vision_sentence(full_low: str, subj: str) -> str:
    if any(word in full_low for word in ("relationship with god", "deeper relationship", "seek first")):
        return (
            f"{subj} helps people deepen their relationship with God and honour Him "
            f"in every area of life."
        )
    if any(word in full_low for word in ("orphan", "neglected", "structure", "school bus", "safe place")):
        return (
            f"{subj} has a heart to care for vulnerable children and strengthen the ICBC "
            f"as a place of safety, support, and hope for families."
        )
    if any(word in full_low for word in ("heal", "health", "sickness", "wholeness")):
        return (
            f"{subj} longs to see the community experience spiritual transformation, "
            f"with many coming to Christ and finding healing and renewed hope."
        )
    if any(word in full_low for word in ("evangelism", "farming", "income", "job", "plough", "maize project")):
        return (
            f"{subj} carries a vision for church growth, practical outreach, "
            f"and community projects that create opportunities for families."
        )
    if any(word in full_low for word in ("preschool", "primary school", "education", "sunday school")):
        return (
            f"{subj} is committed to nurturing children through education, discipleship, "
            f"and strong foundations for the next generation."
        )
    if any(word in full_low for word in ("multiply", "plant churches", "reach more")):
        return (
            f"{subj} is passionate about reaching more people, strengthening the church, "
            f"and seeing the gospel spread in the area."
        )
    return (
        f"{subj} leads with a desire to see spiritual transformation in the community "
        f"and many people come to know Christ and grow in faith."
    )


def pastor_impact_sentence(full_low: str, subj: str) -> str:
    if any(word in full_low for word in ("bible study", "youth meeting", "youth meetings", "youth program")):
        return (
            f"{subj} has seen God at work through faithful Bible teaching, youth ministry, "
            f"and lives being changed."
        )
    if any(word in full_low for word in ("rice pack", "tractor", "home visit", "clothing", "tent revival")):
        return (
            f"{subj} has witnessed God's work through practical outreach, compassionate care, "
            f"and transformed lives."
        )
    if any(word in full_low for word in ("rain", "harvest", "maize", "melons", "provision")):
        return (
            f"{subj} has witnessed God's faithful provision and growth in the life "
            f"of the church and community."
        )
    if any(word in full_low for word in ("building", "church hall", "preschool", "children's home")):
        return (
            f"{subj} has seen God bless the church with facilities and programmes "
            f"that are making a lasting difference."
        )
    if any(word in full_low for word in ("unity", "repentance", "deliverance")):
        return (
            f"{subj} has seen growing unity among believers, transformed lives, "
            f"and a willingness to serve one another."
        )
    return (
        f"{subj} has seen God at work through changed lives, answered prayer, "
        f"and people turning to Christ."
    )


def teacher_passion_sentence(full_low: str, subj: str, poss: str) -> str:
    if "calling" in full_low or "passion for children" in full_low:
        return (
            f"{subj} serves with joy because {subj.lower()} believes teaching young children "
            f"is a calling to make a positive difference in their lives."
        )
    if "god first" in full_low or "put god first" in full_low:
        return (
            f"{subj} loves serving at the preschool and puts God first in everything "
            f"{subj.lower()} does."
        )
    if "christian values" in full_low or "instilling" in full_low:
        return (
            f"{subj} enjoys nurturing young children and helping them grow in knowledge "
            f"and Christian character."
        )
    return (
        f"{subj} enjoys helping children learn, play, and grow with patience, creativity, "
        f"and a genuine love for each child."
    )


def teacher_impact_sentence(full_low: str, subj: str) -> str:
    if any(word in full_low for word in ("heal", "miracle", "mute", "seizure", "protected")):
        return (
            f"{subj} has seen God protect the children, answer prayer, "
            f"and work in remarkable ways at the school."
        )
    return (
        f"{subj} has seen God bring unity, joy, and a love for learning "
        f"among the children and staff."
    )


def care_service_sentence(full_low: str, subj: str) -> str:
    if any(word in full_low for word in ("bedridden", "wound", "first aid", "hygiene")):
        return (
            f"{subj} cares for the sick and vulnerable through home visits, practical support, "
            f"and pointing people to Christ."
        )
    if any(word in full_low for word in ("rice", "food", "clothing", "elderly")):
        return (
            f"{subj} serves families with food, clothing, prayer, and encouragement, "
            f"meeting practical needs with compassion."
        )
    if any(word in full_low for word in ("children", "young children", "neglected")):
        return (
            f"{subj} focuses on caring for children who need love, guidance, "
            f"and steady support."
        )
    return (
        f"{subj} serves the community with practical care and Christ-centred compassion."
    )


def care_impact_sentence(full_low: str, subj: str) -> str:
    if any(word in full_low for word in ("borehole", "water", "healthier", "fewer sick")):
        return (
            f"{subj} has seen improved health in the community and greater trust "
            f"as people experience God's care."
        )
    if any(word in full_low for word in ("ancestral", "turning to god", "repent")):
        return (
            f"{subj} has seen people turn from old practices to faith in God "
            f"through consistent love and prayer."
        )
    if any(word in full_low for word in ("land", "plot", "crop", "construction", "jobs")):
        return (
            f"{subj} has seen God open doors through community projects and new opportunities "
            f"for families."
        )
    if "royal ranger" in full_low or "youth" in full_low:
        return (
            f"{subj} has seen young people grow in character and faith through outreach "
            f"and weekend programmes."
        )
    return (
        f"{subj} has seen hope restored, prayers answered, and lives drawn closer to Christ."
    )


def build_description(
    role: str,
    site_name: str,
    qa: list[tuple[str, str]],
    full_name: str = "",
) -> str:
    if not qa:
        return ""

    subj, poss, _obj = subject_pronouns(full_name)
    site_label = f"{site_name} ICBC"

    buckets: dict[str, list[str]] = {}
    for question, answer in qa:
        if not answer or answer.lower() in SKIP_ANSWERS:
            continue
        kind = classify_question(question)
        if kind == "skip":
            continue
        buckets.setdefault(kind, []).append(answer)

    full_low = combined_answer_text(buckets).lower()
    if not full_low.strip():
        return ""

    if role == ROLE_PASTOR:
        return " ".join(
            [
                f"Lead Pastor serving at {site_label}.",
                pastor_vision_sentence(full_low, subj),
                pastor_impact_sentence(full_low, subj),
            ]
        )

    if role == ROLE_TEACHER:
        return " ".join(
            [
                f"Preschool teacher at {site_label}.",
                teacher_passion_sentence(full_low, subj, poss),
                teacher_impact_sentence(full_low, subj),
            ]
        )

    return " ".join(
        [
            f"Compassionate Care team member at {site_label}.",
            care_service_sentence(full_low, subj),
            care_impact_sentence(full_low, subj),
        ]
    )


def find_section_indices(lines: list[str]) -> dict[str, int | None]:
    indices = {"pastor": None, "teacher": None, "care": None, "end": len(lines)}
    for i, line in enumerate(lines):
        low = line.lower()
        if indices["pastor"] is None and re.match(r"^pastor\s*:?", line, re.I):
            indices["pastor"] = i
        elif "preschool teacher" in low:
            indices["teacher"] = i
        elif "compassionate care" in low:
            indices["care"] = i
    if indices["teacher"] is not None:
        if indices["care"] is not None and indices["care"] > indices["teacher"]:
            pass
        elif indices["pastor"] is not None and indices["teacher"] > indices["pastor"]:
            pass
    return indices


def parse_questionnaire(path: Path, site_map: dict[str, str], slug_to_name: dict[str, str]) -> ParsedQuestionnaire:
    site_slug, warnings = slug_from_filename(path, site_map)
    parsed = ParsedQuestionnaire(path=path, site_slug=site_slug, warnings=warnings)

    if not site_slug:
        return parsed

    doc = Document(path)
    lines = [para.text for para in doc.paragraphs]
    idx = find_section_indices(lines)
    site_name = slug_to_name.get(site_slug, site_slug.replace("-", " ").title())

    if idx["pastor"] is not None:
        end = idx["teacher"] if idx["teacher"] is not None else idx["care"] if idx["care"] is not None else idx["end"]
        section = split_section(lines, idx["pastor"], end)
        pastor_name = extract_name_from_header(section[0] if section else "", "Pastor") if section else ""
        qa = parse_qa_blocks(section[1:] if pastor_name and section else section)
        if qa:
            desc = build_description(ROLE_PASTOR, site_name, qa, pastor_name)
            if desc:
                parsed.pastor = StaffMember(
                    site_slug=site_slug,
                    full_name=pastor_name or "",
                    role=ROLE_PASTOR,
                    description=desc,
                    sort_order="0",
                    source_file=path.name,
                )
        if qa and not pastor_name:
            parsed.warnings.append("Pastor answers captured; will match existing pastor by site.")

    if idx["teacher"] is not None:
        end = idx["care"] if idx["care"] is not None else idx["end"]
        section = split_section(lines, idx["teacher"], end)
        header = section[0] if section else ""
        teacher_name = extract_name_from_header(header, r"Preschool Teacher or staff member")
        qa = parse_qa_blocks(section[1:] if teacher_name and section else section)
        if teacher_name and qa and is_valid_person_name(teacher_name):
            parsed.teacher = StaffMember(
                site_slug=site_slug,
                full_name=teacher_name,
                role=ROLE_TEACHER,
                description=build_description(ROLE_TEACHER, site_name, qa, teacher_name),
                sort_order="1",
                source_file=path.name,
            )
        elif qa and not teacher_name:
            parsed.warnings.append("Teacher answers found but name missing in questionnaire.")

    if idx["care"] is not None:
        section = split_section(lines, idx["care"], idx["end"])
        header = section[0] if section else ""
        care_name = extract_name_from_header(header, r"Compassionate Care Team member")
        if not care_name:
            care_name = extract_name_from_header(header, r"Compassionate Care")
        qa = parse_qa_blocks(section[1:] if care_name and section else section)
        if care_name and qa and is_valid_person_name(care_name):
            parsed.care = StaffMember(
                site_slug=site_slug,
                full_name=care_name,
                role=ROLE_CARE,
                description=build_description(ROLE_CARE, site_name, qa, care_name),
                sort_order="2",
                source_file=path.name,
            )
        elif qa and not care_name:
            parsed.warnings.append("Compassionate care answers found but name missing.")

    return parsed


def names_match(a: str, b: str) -> bool:
    return slugify(a.replace(" ", "")) == slugify(b.replace(" ", "")) or (
        normalise_name_token(a) == normalise_name_token(b)
    )


def normalise_name_token(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def read_staff_csv() -> tuple[list[str], list[dict[str, str]]]:
    with STAFF_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return columns, rows


def write_staff_csv(columns: list[str], rows: list[dict[str, str]]) -> None:
    rows.sort(key=lambda r: (r.get("site_slug", ""), int(r.get("sort_order") or 0), r.get("role", ""), r.get("full_name", "")))
    with STAFF_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def is_bad_seed_row(row: dict[str, str]) -> bool:
    role = row.get("role", "")
    name = row.get("full_name", "")
    if role == ROLE_PASTOR:
        return False
    return not is_valid_person_name(name)


def merge_staff(
    existing_rows: list[dict[str, str]],
    incoming: list[StaffMember],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    stats = {"pastor_updated": 0, "teacher_added": 0, "teacher_updated": 0, "care_added": 0, "care_updated": 0}
    by_key: dict[tuple[str, str, str], dict[str, str]] = {}

    for row in existing_rows:
        if is_bad_seed_row(row):
            continue
        key = (
            row.get("site_slug", "").lower(),
            row.get("full_name", "").lower(),
            row.get("role", "").lower(),
        )
        by_key[key] = row

    for member in incoming:
        matched_key = None
        for key, row in list(by_key.items()):
            if key[0] != member.site_slug.lower() or key[2] != member.role.lower():
                continue
            if member.role == ROLE_PASTOR:
                matched_key = key
                break
            if member.full_name and names_match(row.get("full_name", ""), member.full_name):
                matched_key = key
                break

        if matched_key:
            row = by_key.pop(matched_key)
            name_for_pronouns = row.get("full_name") or member.full_name
            row["description"] = align_pronouns(member.description, name_for_pronouns)
            row["site_slug"] = member.site_slug
            row["role"] = member.role
            row["sort_order"] = member.sort_order
            if member.full_name and member.role != ROLE_PASTOR:
                row["full_name"] = member.full_name
            new_key = (
                member.site_slug.lower(),
                row.get("full_name", "").lower(),
                member.role.lower(),
            )
            by_key[new_key] = row
            if member.role == ROLE_PASTOR:
                stats["pastor_updated"] += 1
            elif member.role == ROLE_TEACHER:
                stats["teacher_updated"] += 1
            else:
                stats["care_updated"] += 1
        elif not member.full_name and member.role != ROLE_PASTOR:
            continue
        else:
            new_key = (member.site_slug.lower(), member.full_name.lower(), member.role.lower())
            by_key[new_key] = {
                "site_slug": member.site_slug,
                "full_name": member.full_name,
                "description": align_pronouns(member.description, member.full_name),
                "role": member.role,
                "year_joined": member.year_joined,
                "photo_url": member.photo_url,
                "sort_order": member.sort_order,
            }
            if member.role == ROLE_TEACHER:
                stats["teacher_added"] += 1
            elif member.role == ROLE_CARE:
                stats["care_added"] += 1

    return dedupe_pastors_per_site(list(by_key.values())), stats


def dedupe_pastors_per_site(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep one pastor row per site (prefer existing photo_url, then longest description)."""
    pastors_by_site: dict[str, list[dict[str, str]]] = {}
    other_rows: list[dict[str, str]] = []

    for row in rows:
        if row.get("role") == ROLE_PASTOR:
            pastors_by_site.setdefault(row.get("site_slug", ""), []).append(row)
        else:
            other_rows.append(row)

    merged_pastors: list[dict[str, str]] = []
    for site, pastor_rows in pastors_by_site.items():
        if len(pastor_rows) == 1:
            merged_pastors.append(pastor_rows[0])
            continue

        def score(p: dict[str, str]) -> tuple:
            name = p.get("full_name", "")
            return (
                1 if p.get("photo_url") else 0,
                0 if name.lower().startswith("pr.") else 1,
                len(p.get("description", "")),
                -len(name),
            )

        best = max(pastor_rows, key=score)
        merged_pastors.append(best)

    return other_rows + merged_pastors


def write_report(parsed_list: list[ParsedQuestionnaire], stats: dict, skipped_files: list[str]) -> None:
    lines = [
        "# Questionnaire import report",
        "",
        "## Summary",
        "",
        f"- Pastor descriptions updated: **{stats.get('pastor_updated', 0)}**",
        f"- Teachers added: **{stats.get('teacher_added', 0)}**",
        f"- Teachers updated: **{stats.get('teacher_updated', 0)}**",
        f"- Compassionate care added: **{stats.get('care_added', 0)}**",
        f"- Compassionate care updated: **{stats.get('care_updated', 0)}**",
        "",
        "## Per site",
        "",
        "| Site | Pastor | Teacher | Care | Source file | Notes |",
        "|------|--------|---------|------|-------------|-------|",
    ]

    for parsed in sorted(parsed_list, key=lambda p: p.site_slug):
        if not parsed.site_slug:
            continue
        notes = "; ".join(parsed.warnings) if parsed.warnings else ""
        lines.append(
            f"| {parsed.site_slug} | "
            f"{'✓' if parsed.pastor else '—'} | "
            f"{parsed.teacher.full_name if parsed.teacher else '—'} | "
            f"{parsed.care.full_name if parsed.care else '—'} | "
            f"{parsed.path.name} | {notes} |"
        )

    sites_with_q = {p.site_slug for p in parsed_list if p.site_slug}
    with SITES_CSV.open(encoding="utf-8", newline="") as handle:
        all_slugs = [row["slug"] for row in csv.DictReader(handle)]
    missing = sorted(set(all_slugs) - sites_with_q)
    if missing:
        lines.extend(["", "## Sites with no questionnaire file matched", ""])
        lines.extend(f"- `{slug}`" for slug in missing)

    if skipped_files:
        lines.extend(["", "## Skipped files", ""])
        lines.extend(f"- `{name}`" for name in skipped_files)

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not QUESTIONNAIRES_DIR.is_dir():
        raise SystemExit(f"Questionnaires folder not found: {QUESTIONNAIRES_DIR}")

    site_map = load_site_slugs()
    slug_to_name = {}
    with SITES_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            slug_to_name[row["slug"]] = row["name"]

    parsed_list: list[ParsedQuestionnaire] = []
    skipped_files: list[str] = []
    incoming: list[StaffMember] = []

    for path in sorted(QUESTIONNAIRES_DIR.glob("*.docx")):
        parsed = parse_questionnaire(path, site_map, slug_to_name)
        parsed_list.append(parsed)
        if not parsed.site_slug:
            skipped_files.append(path.name)
            continue
        for member in (parsed.pastor, parsed.teacher, parsed.care):
            if member:
                incoming.append(member)

    columns, existing = read_staff_csv()
    merged, stats = merge_staff(existing, incoming)
    write_staff_csv(columns, merged)
    write_report(parsed_list, stats, skipped_files)

    print(f"Updated {STAFF_CSV}")
    print(f"Report: {REPORT_PATH}")
    print(stats)


if __name__ == "__main__":
    main()

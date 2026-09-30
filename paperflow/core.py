from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml


SCHEMA_VERSION = "1.0"
OVERALL_STATUSES = (
    "idea",
    "exploring",
    "drafting",
    "translating",
    "language_review",
    "journal_targeting",
    "formatting",
    "internal_review",
    "ready_to_submit",
    "submitted",
    "under_review",
    "revision",
    "accepted",
    "rejected",
    "parked",
)
TRACK_STATUSES = ("not_started", "in_progress", "blocked", "complete", "not_applicable")
GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
TRANSITIONS: dict[str, set[str]] = {
    "idea": {"exploring", "drafting", "parked"},
    "exploring": {"drafting", "parked"},
    "drafting": {"translating", "journal_targeting", "internal_review", "parked"},
    "translating": {"language_review", "parked"},
    "language_review": {"translating", "journal_targeting", "parked"},
    "journal_targeting": {"formatting", "parked"},
    "formatting": {"internal_review", "journal_targeting", "parked"},
    "internal_review": {"drafting", "translating", "formatting", "ready_to_submit", "parked"},
    "ready_to_submit": {"internal_review", "submitted", "parked"},
    "submitted": {"under_review", "revision", "accepted", "rejected"},
    "under_review": {"revision", "accepted", "rejected"},
    "revision": {"internal_review", "ready_to_submit", "submitted", "accepted", "rejected"},
    "accepted": set(),
    "rejected": {"journal_targeting", "parked"},
    "parked": {"idea", "exploring", "drafting", "journal_targeting"},
}
GATE_PREREQUISITES = {
    "G1": ("G0",),
    "G2": ("G0",),
    "G3": ("G0", "G1", "G2"),
    "G4": ("G0", "G1", "G2", "G3"),
    "G5": ("G4",),
}
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class PaperflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckIssue:
    severity: str
    code: str
    message: str


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PaperflowError(f"Missing required file: {path}") from exc
    except yaml.YAMLError as exc:
        raise PaperflowError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PaperflowError(f"Expected a YAML mapping in {path}")
    return value


def atomic_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(rendered)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise PaperflowError("Slug must contain at least one ASCII letter or digit")
    return slug


def papers_root(value: str | Path | None = None) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()
    env = os.environ.get("PAPERFLOW_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "papers").resolve()


def paper_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.glob("P-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9]-*") if (path / "PAPER.yaml").is_file())


def read_paper(path: Path) -> dict[str, Any]:
    return load_yaml(path / "PAPER.yaml")


def resolve_paper(root: Path, identifier: str) -> Path:
    direct = root / identifier
    if (direct / "PAPER.yaml").is_file():
        return direct
    matches = [path for path in paper_dirs(root) if read_paper(path).get("paper_id") == identifier]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise PaperflowError(f"Unknown paper: {identifier}")
    raise PaperflowError(f"Ambiguous paper identifier: {identifier}")


def _next_paper_id(root: Path, year: int) -> str:
    prefix = f"P-{year}-"
    used = []
    for path in paper_dirs(root):
        paper_id = str(read_paper(path).get("paper_id", ""))
        if paper_id.startswith(prefix):
            try:
                used.append(int(paper_id.removeprefix(prefix)))
            except ValueError:
                continue
    return f"{prefix}{max(used, default=0) + 1:03d}"


def create_paper(root: Path, *, title: str, slug: str, entry: str, year: int) -> Path:
    if entry not in {"existing_chinese", "new_research"}:
        raise PaperflowError("entry must be existing_chinese or new_research")
    root.mkdir(parents=True, exist_ok=True)
    paper_id = _next_paper_id(root, year)
    folder = root / f"{paper_id}-{safe_slug(slug)}"
    if folder.exists():
        raise PaperflowError(f"Refusing to overwrite existing directory: {folder}")
    subdirs = (
        "00_source",
        "01_research/literature",
        "01_research/experiments",
        "02_translation/batches",
        "03_manuscript",
        "04_journal",
        "05_submission",
        "06_reviews",
        "references",
        "evidence",
        "decisions",
        "qa",
    )
    for subdir in subdirs:
        (folder / subdir).mkdir(parents=True, exist_ok=False)
    created = now_iso()
    existing = entry == "existing_chinese"
    paper = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "title": title,
        "short_title": slug,
        "entry_path": entry,
        "created_at": created,
        "updated_at": created,
        "overall_status": "drafting" if existing else "idea",
        "tracks": {
            "research_status": "not_applicable" if existing else "in_progress",
            "manuscript_status": "in_progress" if existing else "not_started",
            "translation_status": "not_started",
            "journal_status": "not_started",
            "submission_status": "not_started",
        },
        "current_tasks": [],
        "blockers": [],
        "next_gate": "G0",
        "target_date": None,
        "gates": {gate: {"approved": False, "approved_at": None, "note": ""} for gate in GATES},
        "source_files": [],
        "journal_profiles": [],
    }
    atomic_yaml(folder / "PAPER.yaml", paper)
    atomic_yaml(folder / "02_translation" / "glossary.yaml", {"schema_version": SCHEMA_VERSION, "terms": []})
    (folder / "02_translation" / "segments.jsonl").write_text("", encoding="utf-8")
    (folder / "evidence" / "evidence.jsonl").write_text("", encoding="utf-8")
    (folder / "evidence" / "claims.jsonl").write_text("", encoding="utf-8")
    (folder / "references" / "library.bib").write_text("", encoding="utf-8")
    (folder / "references" / "citations.jsonl").write_text("", encoding="utf-8")
    (folder / "README.md").write_text(_paper_readme(paper_id, title), encoding="utf-8")
    rebuild_portfolio(root)
    return folder


def _paper_readme(paper_id: str, title: str) -> str:
    return f"""# {paper_id}: {title}

`PAPER.yaml` is the authoritative project status. Original manuscripts in
`00_source/` and official journal templates under `04_journal/*/official/`
must never be edited or replaced. Use `paperflow freeze-source` and
`paperflow journal-init` to register immutable inputs.

Translation units live in `02_translation/segments.jsonl`. The English master
manuscript belongs in `03_manuscript/`; every journal-specific manuscript is a
derived artifact and belongs under its journal profile.
"""


def freeze_source(root: Path, identifier: str, source: Path) -> Path:
    folder = resolve_paper(root, identifier)
    source = source.expanduser().resolve()
    if not source.is_file():
        raise PaperflowError(f"Source is not a file: {source}")
    target = folder / "00_source" / source.name
    if target.exists():
        raise PaperflowError(f"Refusing to overwrite frozen source: {target}")
    shutil.copy2(source, target)
    record = {
        "path": target.relative_to(folder).as_posix(),
        "sha256": sha256_file(target),
        "size": target.stat().st_size,
        "frozen_at": now_iso(),
        "original_name": source.name,
    }
    paper = read_paper(folder)
    paper.setdefault("source_files", []).append(record)
    paper["updated_at"] = now_iso()
    atomic_yaml(folder / "PAPER.yaml", paper)
    rebuild_portfolio(root)
    return target


def _word_units(xml_bytes: bytes, part: str, source_hash: str, start: int) -> tuple[list[dict[str, Any]], int]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise PaperflowError(f"Invalid Word XML part {part}: {exc}") from exc
    units: list[dict[str, Any]] = []
    counter = start

    def walk(element: ET.Element, path: str, in_table_cell: bool = False) -> None:
        nonlocal counter
        local = element.tag.rsplit("}", 1)[-1]
        table_context = in_table_cell or local == "tc"
        if local == "p":
            text = "".join(node.text or "" for node in element.iter(f"{{{WORD_NS}}}t")).strip()
            if text:
                style_node = element.find(f"./{{{WORD_NS}}}pPr/{{{WORD_NS}}}pStyle")
                style = style_node.get(f"{{{WORD_NS}}}val", "") if style_node is not None else ""
                if table_context:
                    kind = "table_cell"
                elif part.startswith("word/header"):
                    kind = "header"
                elif part.startswith("word/footer"):
                    kind = "footer"
                elif part == "word/footnotes.xml":
                    kind = "footnote"
                elif part == "word/endnotes.xml":
                    kind = "endnote"
                elif "caption" in style.casefold():
                    kind = "caption"
                elif style.casefold() in {"title", "subtitle"}:
                    kind = style.casefold()
                else:
                    kind = "paragraph"
                counter += 1
                units.append(
                    {
                        "unit_id": f"U{counter:06d}",
                        "kind": kind,
                        "source_part": part,
                        "source_locator": f"{part}:{path}",
                        "source_sha256": source_hash,
                        "source_zh": text,
                        "candidate_en": "",
                        "final_en": "",
                        "status": "not_started",
                        "change_reason": "",
                        "terminology_risks": [],
                        "fact_risks": [],
                    }
                )
            return
        tag_counts: dict[str, int] = {}
        for child in list(element):
            child_local = child.tag.rsplit("}", 1)[-1]
            tag_counts[child_local] = tag_counts.get(child_local, 0) + 1
            walk(child, f"{path}/{child_local}[{tag_counts[child_local]}]", table_context)

    walk(root, root.tag.rsplit("}", 1)[-1])
    return units, counter


def extract_translation_units(root: Path, identifier: str, source_name: str | None = None) -> int:
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    sources = paper.get("source_files", [])
    if source_name is not None:
        sources = [item for item in sources if Path(str(item.get("path", ""))).name == source_name]
    if len(sources) != 1:
        raise PaperflowError("Select exactly one frozen source with --source-name")
    source_record = sources[0]
    source = folder / str(source_record["path"])
    if source.suffix.casefold() != ".docx" or not zipfile.is_zipfile(source):
        raise PaperflowError("Translation extraction currently requires a valid DOCX source")
    current_hash = sha256_file(source)
    if current_hash != source_record.get("sha256"):
        raise PaperflowError("Frozen source hash changed; extraction refused")
    destination = folder / "02_translation" / "segments.jsonl"
    if destination.exists() and destination.read_text(encoding="utf-8").strip():
        raise PaperflowError(f"Refusing to overwrite existing translation units: {destination}")
    part_pattern = re.compile(r"word/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml$")
    units: list[dict[str, Any]] = []
    counter = 0
    with zipfile.ZipFile(source) as archive:
        parts = sorted(name for name in archive.namelist() if part_pattern.fullmatch(name))
        if "word/document.xml" in parts:
            parts.remove("word/document.xml")
            parts.insert(0, "word/document.xml")
        for part in parts:
            part_units, counter = _word_units(archive.read(part), part, current_hash, counter)
            units.extend(part_units)
    if not units:
        raise PaperflowError("No translatable text units found in DOCX")
    destination.write_text("".join(json.dumps(unit, ensure_ascii=False) + "\n" for unit in units), encoding="utf-8")
    paper["tracks"]["translation_status"] = "in_progress"
    paper["updated_at"] = now_iso()
    atomic_yaml(folder / "PAPER.yaml", paper)
    rebuild_portfolio(root)
    return len(units)


def init_journal(
    root: Path,
    identifier: str,
    *,
    journal: str,
    article_type: str,
    guidelines_url: str,
    verified_at: str,
    template: Path | None,
) -> Path:
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    for existing in paper.get("journal_profiles", []):
        existing_profile = load_yaml(folder / str(existing.get("path", "")))
        if existing_profile.get("status", "active") == "active":
            raise PaperflowError("An active journal profile already exists; supersede or withdraw it first")
    slug = safe_slug(journal)
    journal_dir = folder / "04_journal" / slug
    if journal_dir.exists():
        raise PaperflowError(f"Refusing to overwrite journal profile: {journal_dir}")
    for subdir in ("official", "derived", "qa"):
        (journal_dir / subdir).mkdir(parents=True, exist_ok=True)
    template_record = None
    if template is not None:
        template = template.expanduser().resolve()
        if not template.is_file():
            raise PaperflowError(f"Template is not a file: {template}")
        target = journal_dir / "official" / template.name
        shutil.copy2(template, target)
        template_record = {
            "path": target.relative_to(folder).as_posix(),
            "sha256": sha256_file(target),
            "size": target.stat().st_size,
        }
    profile = {
        "schema_version": SCHEMA_VERSION,
        "journal_id": slug,
        "journal_name": journal,
        "status": "active",
        "article_type": article_type,
        "official_guidelines_url": guidelines_url,
        "requirements_verified_at": verified_at,
        "official_template": template_record,
        "limits": {"manuscript_words": None, "abstract_words": None, "keywords": None},
        "section_order": [],
        "blind_review": False,
        "reference_style": "",
        "required_statements": [],
        "required_submission_files": [],
        "submission_filename_rules": [],
        "master_manuscript": "03_manuscript/master_en.docx",
        "derived_manuscript": f"04_journal/{slug}/derived/manuscript.docx",
        "qa": {
            "structural_audit": {"passed": False, "checked_at": None, "evidence": ""},
            "render_review": {"passed": False, "checked_at": None, "reviewer": "", "evidence": ""},
        },
    }
    atomic_yaml(journal_dir / "journal.yaml", profile)
    (journal_dir / "artifact.md").write_text(_artifact_contract(template_record), encoding="utf-8")
    paper.setdefault("journal_profiles", []).append({"journal_id": slug, "path": f"04_journal/{slug}/journal.yaml"})
    paper["tracks"]["journal_status"] = "in_progress"
    paper["updated_at"] = now_iso()
    atomic_yaml(folder / "PAPER.yaml", paper)
    rebuild_portfolio(root)
    return journal_dir


def set_journal_status(root: Path, identifier: str, journal_id: str, status: str, note: str) -> None:
    if status not in {"active", "superseded", "withdrawn"}:
        raise PaperflowError(f"Invalid journal status: {status}")
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    match = next((item for item in paper.get("journal_profiles", []) if item.get("journal_id") == journal_id), None)
    if match is None:
        raise PaperflowError(f"Unknown journal profile: {journal_id}")
    if status == "active":
        for item in paper.get("journal_profiles", []):
            if item is match:
                continue
            profile = load_yaml(folder / str(item.get("path", "")))
            if profile.get("status", "active") == "active":
                raise PaperflowError("Another active journal profile exists")
    profile_path = folder / str(match["path"])
    profile = load_yaml(profile_path)
    previous = profile.get("status", "active")
    profile["status"] = status
    atomic_yaml(profile_path, profile)
    decision = {
        "recorded_at": now_iso(),
        "type": "journal_status_change",
        "journal_id": journal_id,
        "from": previous,
        "to": status,
        "note": note,
    }
    with (folder / "decisions" / "journal-changes.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision, ensure_ascii=False) + "\n")
    paper["updated_at"] = now_iso()
    atomic_yaml(folder / "PAPER.yaml", paper)
    rebuild_portfolio(root)


def record_journal_qa(
    root: Path,
    identifier: str,
    journal_id: str,
    *,
    check: str,
    passed: bool,
    evidence: str,
    reviewer: str = "",
) -> None:
    if check not in {"structural_audit", "render_review"}:
        raise PaperflowError(f"Unknown journal QA check: {check}")
    if check == "render_review" and passed and not reviewer.strip():
        raise PaperflowError("A human reviewer is required to pass full-page render review")
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    match = next((item for item in paper.get("journal_profiles", []) if item.get("journal_id") == journal_id), None)
    if match is None:
        raise PaperflowError(f"Unknown journal profile: {journal_id}")
    profile_path = folder / str(match["path"])
    profile = load_yaml(profile_path)
    record = {"passed": passed, "checked_at": now_iso(), "evidence": evidence}
    if check == "render_review":
        record["reviewer"] = reviewer
    profile.setdefault("qa", {})[check] = record
    atomic_yaml(profile_path, profile)


def _artifact_contract(template_record: dict[str, Any] | None) -> str:
    template_path = template_record["path"] if template_record else "UNRESOLVED"
    template_hash = template_record["sha256"] if template_record else "UNRESOLVED"
    return f"""# Journal template contract

This file must be completed from rendered and structural evidence before a
journal-specific manuscript is generated. Never infer unresolved values.

## Reference

- Template: `{template_path}`
- SHA-256: `{template_hash}`
- Page count: UNRESOLVED
- Section count: UNRESOLVED

## Page system

UNRESOLVED

## Typography and styles

UNRESOLVED

## Lists, tables, figures, captions, headers, and footers

UNRESOLVED

## Slot map and stable OOXML locators

UNRESOLVED

## Preserve-only package parts and relationships

UNRESOLVED

## Fidelity gates

- [ ] Every template page and section pattern was rendered and inspected.
- [ ] Page geometry and recurring components were recorded.
- [ ] Editable slots and preserve-only parts were inventoried.
- [ ] The official template still matches the recorded SHA-256.
"""


def set_status(root: Path, identifier: str, status: str) -> None:
    if status not in OVERALL_STATUSES:
        raise PaperflowError(f"Unknown overall status: {status}")
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    current = str(paper.get("overall_status"))
    if status != current and status not in TRANSITIONS.get(current, set()):
        raise PaperflowError(f"Illegal status transition: {current} -> {status}")
    paper["overall_status"] = status
    paper["updated_at"] = now_iso()
    atomic_yaml(folder / "PAPER.yaml", paper)
    rebuild_portfolio(root)


def set_track(root: Path, identifier: str, track: str, status: str) -> None:
    if status not in TRACK_STATUSES:
        raise PaperflowError(f"Unknown track status: {status}")
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    if track not in paper.get("tracks", {}):
        raise PaperflowError(f"Unknown track: {track}")
    paper["tracks"][track] = status
    paper["updated_at"] = now_iso()
    atomic_yaml(folder / "PAPER.yaml", paper)
    rebuild_portfolio(root)


def approve_gate(root: Path, identifier: str, gate: str, note: str) -> None:
    if gate not in GATES:
        raise PaperflowError(f"Unknown gate: {gate}")
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    for prerequisite in GATE_PREREQUISITES.get(gate, ()):
        if not paper["gates"][prerequisite]["approved"]:
            raise PaperflowError(f"Cannot approve {gate} before {prerequisite}")
    blockers = gate_readiness_issues(folder, paper, gate)
    if blockers:
        raise PaperflowError(f"{gate} readiness failed: " + "; ".join(item.message for item in blockers))
    paper["gates"][gate] = {"approved": True, "approved_at": now_iso(), "note": note}
    next_index = GATES.index(gate) + 1
    paper["next_gate"] = GATES[next_index] if next_index < len(GATES) else None
    paper["updated_at"] = now_iso()
    atomic_yaml(folder / "PAPER.yaml", paper)
    rebuild_portfolio(root)


def gate_readiness_issues(folder: Path, paper: dict[str, Any], gate: str) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if gate == "G0":
        if paper.get("entry_path") == "existing_chinese" and not paper.get("source_files"):
            issues.append(CheckIssue("error", "g0_source_missing", "Freeze the Chinese source manuscript before G0"))
        if paper.get("entry_path") == "new_research":
            question = folder / "01_research" / "research-question.md"
            if not question.is_file() or not question.read_text(encoding="utf-8").strip():
                issues.append(CheckIssue("error", "g0_question_missing", "Record the research question before G0"))
    elif gate == "G1":
        master = folder / "03_manuscript" / "master_en.docx"
        if not master.is_file():
            issues.append(CheckIssue("error", "g1_master_missing", "English master manuscript is missing"))
        if paper.get("entry_path") == "existing_chinese":
            segments, parse_issues = _read_jsonl(folder / "02_translation" / "segments.jsonl")
            issues.extend(parse_issues)
            if not segments:
                issues.append(CheckIssue("error", "g1_segments_missing", "No translation units exist"))
            for segment in segments:
                if segment.get("status") not in {"confirmed", "not_applicable"} or (
                    segment.get("status") == "confirmed" and not str(segment.get("final_en", "")).strip()
                ):
                    issues.append(CheckIssue("error", "g1_translation_incomplete", f"Translation unit {segment.get('unit_id')} is not confirmed"))
    elif gate == "G2":
        if not paper.get("journal_profiles"):
            issues.append(CheckIssue("error", "g2_journal_missing", "Create and verify a journal profile before G2"))
    elif gate == "G3":
        if not (folder / "03_manuscript" / "master_en.docx").is_file():
            issues.append(CheckIssue("error", "g3_master_missing", "English master manuscript is missing"))
        active_profiles = []
        for record in paper.get("journal_profiles", []):
            profile = load_yaml(folder / str(record.get("path", "")))
            if profile.get("status", "active") != "active":
                continue
            active_profiles.append(profile)
            derived = folder / str(profile.get("derived_manuscript", ""))
            if not derived.is_file():
                issues.append(CheckIssue("error", "g3_derived_missing", f"Derived journal manuscript is missing: {derived}"))
            qa = profile.get("qa", {})
            if not qa.get("structural_audit", {}).get("passed"):
                issues.append(CheckIssue("error", "g3_structural_qa_missing", "Journal structural QA has not passed"))
            if not qa.get("render_review", {}).get("passed"):
                issues.append(CheckIssue("error", "g3_render_qa_missing", "Full-page render review has not passed"))
        if len(active_profiles) != 1:
            issues.append(CheckIssue("error", "g3_active_journal_count", "Exactly one active journal profile is required"))
    elif gate == "G4":
        documents = sorted((folder / "05_submission").glob("*.docx"))
        if not documents:
            issues.append(CheckIssue("error", "g4_submission_missing", "No submission DOCX exists"))
        for document in documents:
            issues.extend(audit_docx(document))
        for record in paper.get("journal_profiles", []):
            profile = load_yaml(folder / str(record.get("path", "")))
            if profile.get("status", "active") != "active":
                continue
            for required in profile.get("required_submission_files", []):
                if not (folder / "05_submission" / str(required)).is_file():
                    issues.append(CheckIssue("error", "g4_required_file_missing", f"Missing required submission file: {required}"))
    elif gate == "G5":
        rounds = [path for path in (folder / "06_reviews").iterdir() if path.is_dir()]
        if not rounds:
            issues.append(CheckIssue("error", "g5_review_round_missing", "No review round directory exists"))
    return issues


def rebuild_portfolio(root: Path) -> list[dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for folder in paper_dirs(root):
        paper = read_paper(folder)
        records.append(
            {
                "paper_id": paper.get("paper_id"),
                "title": paper.get("title"),
                "folder": folder.name,
                "overall_status": paper.get("overall_status"),
                "tracks": paper.get("tracks", {}),
                "next_gate": paper.get("next_gate"),
                "target_date": paper.get("target_date"),
                "current_tasks": paper.get("current_tasks", []),
                "blockers": paper.get("blockers", []),
                "updated_at": paper.get("updated_at"),
            }
        )
    atomic_yaml(root / "INDEX.yaml", {"schema_version": SCHEMA_VERSION, "generated_at": now_iso(), "papers": records})
    (root / "STATUS.md").write_text(_status_markdown(records), encoding="utf-8")
    return records


def _status_markdown(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Paper portfolio status",
        "",
        "Generated from each paper's `PAPER.yaml`; do not edit this file manually.",
        "",
        "| Paper | Overall | Research | Manuscript | Translation | Journal | Submission | Next gate | Updated |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        tracks = record["tracks"]
        lines.append(
            "| {paper} | {overall} | {research} | {manuscript} | {translation} | {journal} | {submission} | {gate} | {updated} |".format(
                paper=f"[{record['paper_id']}]({record['folder']}/)",
                overall=record["overall_status"],
                research=tracks.get("research_status", ""),
                manuscript=tracks.get("manuscript_status", ""),
                translation=tracks.get("translation_status", ""),
                journal=tracks.get("journal_status", ""),
                submission=tracks.get("submission_status", ""),
                gate=record.get("next_gate") or "-",
                updated=record.get("updated_at") or "",
            )
        )
        details = [*record.get("current_tasks", []), *[f"BLOCKED: {item}" for item in record.get("blockers", [])]]
        if details:
            lines.extend(["", f"- **{record['paper_id']}**: " + "; ".join(details)])
    if not records:
        lines.extend(["", "No papers registered yet. Use `paperflow new`."])
    return "\n".join(lines) + "\n"


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[CheckIssue]]:
    records: list[dict[str, Any]] = []
    issues: list[CheckIssue] = []
    if not path.exists():
        return records, [CheckIssue("error", "missing_jsonl", f"Missing {path}")]
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(CheckIssue("error", "invalid_jsonl", f"{path}:{line_number}: {exc}"))
            continue
        if not isinstance(record, dict):
            issues.append(CheckIssue("error", "invalid_jsonl_record", f"{path}:{line_number}: expected object"))
            continue
        records.append(record)
    return records, issues


def audit_docx(path: Path, *, blind_review: bool = False) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if not path.is_file():
        return [CheckIssue("error", "missing_docx", f"Missing DOCX: {path}")]
    if not zipfile.is_zipfile(path):
        return [CheckIssue("error", "invalid_docx", f"Not a valid DOCX package: {path}")]
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "word/comments.xml" in names:
            issues.append(CheckIssue("error", "comments_present", f"Comments remain in {path.name}"))
        xml_text = ""
        for name in names:
            if name.startswith("word/") and name.endswith(".xml"):
                xml_text += archive.read(name).decode("utf-8", errors="ignore")
        if re.search(r"<w:(?:ins|del)(?:\s|>)", xml_text):
            issues.append(CheckIssue("error", "tracked_changes_present", f"Tracked changes remain in {path.name}"))
        visible_text = re.sub(r"<[^>]+>", " ", xml_text)
        if re.search(r"\b(?:TODO|TBD|XXX)\b|\[\[.+?\]\]", visible_text, flags=re.IGNORECASE):
            issues.append(CheckIssue("error", "placeholder_present", f"Placeholder text remains in {path.name}"))
        if blind_review and "docProps/core.xml" in names:
            core = archive.read("docProps/core.xml").decode("utf-8", errors="ignore")
            if re.search(r"<(?:dc:creator|cp:lastModifiedBy)>\s*[^<\s]", core):
                issues.append(CheckIssue("error", "identity_metadata", f"Creator metadata remains in blind manuscript {path.name}"))
    return issues


def check_paper(root: Path, identifier: str) -> list[CheckIssue]:
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    issues: list[CheckIssue] = []
    required = {"schema_version", "paper_id", "title", "entry_path", "overall_status", "tracks", "gates", "source_files"}
    for field in sorted(required - set(paper)):
        issues.append(CheckIssue("error", "missing_field", f"PAPER.yaml missing {field}"))
    if paper.get("overall_status") not in OVERALL_STATUSES:
        issues.append(CheckIssue("error", "invalid_status", f"Invalid overall status: {paper.get('overall_status')}"))
    for track, value in paper.get("tracks", {}).items():
        if value not in TRACK_STATUSES:
            issues.append(CheckIssue("error", "invalid_track_status", f"Invalid {track}: {value}"))
    for record in paper.get("source_files", []):
        path = folder / str(record.get("path", ""))
        if not path.is_file():
            issues.append(CheckIssue("error", "missing_source", f"Frozen source missing: {path}"))
        elif sha256_file(path) != record.get("sha256"):
            issues.append(CheckIssue("error", "source_hash_changed", f"Frozen source changed: {path}"))

    segments, segment_issues = _read_jsonl(folder / "02_translation" / "segments.jsonl")
    issues.extend(segment_issues)
    seen: set[str] = set()
    for index, segment in enumerate(segments, start=1):
        unit_id = str(segment.get("unit_id", ""))
        if not unit_id:
            issues.append(CheckIssue("error", "missing_unit_id", f"Translation segment {index} has no unit_id"))
        elif unit_id in seen:
            issues.append(CheckIssue("error", "duplicate_unit_id", f"Duplicate translation unit_id: {unit_id}"))
        seen.add(unit_id)
        if not str(segment.get("source_zh", "")).strip():
            issues.append(CheckIssue("error", "missing_source_text", f"Translation segment {unit_id or index} has no Chinese source"))
        source_hash = str(segment.get("source_sha256", ""))
        registered_hashes = {str(item.get("sha256", "")) for item in paper.get("source_files", [])}
        if source_hash and source_hash not in registered_hashes:
            issues.append(CheckIssue("error", "translation_source_mismatch", f"Translation segment {unit_id} does not match a frozen source"))
        status = segment.get("status", "not_started")
        if status not in {"not_started", "draft", "review", "confirmed", "not_applicable"}:
            issues.append(CheckIssue("error", "invalid_translation_status", f"Invalid translation status for {unit_id}: {status}"))
        if status == "confirmed" and not str(segment.get("final_en", "")).strip():
            issues.append(CheckIssue("error", "missing_final_translation", f"Confirmed segment {unit_id} has no final_en"))
    g1_approved = bool(paper.get("gates", {}).get("G1", {}).get("approved"))
    translation_complete = paper.get("tracks", {}).get("translation_status") == "complete"
    if g1_approved or translation_complete:
        if not segments and paper.get("entry_path") == "existing_chinese":
            issues.append(CheckIssue("error", "no_translation_segments", "Translation is approved/complete but no segments exist"))
        for segment in segments:
            if segment.get("status") not in {"confirmed", "not_applicable"}:
                issues.append(CheckIssue("error", "translation_not_confirmed", f"Segment {segment.get('unit_id')} is not confirmed"))

    glossary_path = folder / "02_translation" / "glossary.yaml"
    glossary = load_yaml(glossary_path)
    source_terms: set[str] = set()
    for term in glossary.get("terms", []):
        source = str(term.get("source_zh", "")).strip()
        preferred = str(term.get("preferred_en", "")).strip()
        if not source or not preferred:
            issues.append(CheckIssue("error", "incomplete_glossary_term", "Glossary terms require source_zh and preferred_en"))
        if source in source_terms:
            issues.append(CheckIssue("error", "duplicate_glossary_term", f"Duplicate glossary source term: {source}"))
        source_terms.add(source)

    evidence, evidence_issues = _read_jsonl(folder / "evidence" / "evidence.jsonl")
    claims, claim_issues = _read_jsonl(folder / "evidence" / "claims.jsonl")
    issues.extend(evidence_issues + claim_issues)
    evidence_ids = {str(item.get("evidence_id")) for item in evidence if item.get("evidence_id")}
    claim_ids: set[str] = set()
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        if not claim_id:
            issues.append(CheckIssue("error", "missing_claim_id", "Claim has no claim_id"))
        elif claim_id in claim_ids:
            issues.append(CheckIssue("error", "duplicate_claim_id", f"Duplicate claim_id: {claim_id}"))
        claim_ids.add(claim_id)
        links = claim.get("evidence_ids", [])
        if claim.get("core", False) and not links:
            issues.append(CheckIssue("error", "unsupported_core_claim", f"Core claim {claim_id} has no evidence"))
        for evidence_id in links:
            if str(evidence_id) not in evidence_ids:
                issues.append(CheckIssue("error", "missing_evidence_link", f"Claim {claim_id} references unknown evidence {evidence_id}"))

    bib_path = folder / "references" / "library.bib"
    bib_text = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""
    bib_keys = re.findall(r"@\w+\s*{\s*([^,\s]+)\s*,", bib_text, flags=re.IGNORECASE)
    duplicate_bib_keys = {key for key in bib_keys if bib_keys.count(key) > 1}
    for key in sorted(duplicate_bib_keys):
        issues.append(CheckIssue("error", "duplicate_bibtex_key", f"Duplicate BibTeX key: {key}"))
    citations, citation_issues = _read_jsonl(folder / "references" / "citations.jsonl")
    issues.extend(citation_issues)
    citation_ids: set[str] = set()
    for citation in citations:
        citation_id = str(citation.get("citation_id", ""))
        citekey = str(citation.get("citekey", ""))
        if not citation_id or citation_id in citation_ids:
            issues.append(CheckIssue("error", "invalid_citation_id", f"Missing or duplicate citation_id: {citation_id}"))
        citation_ids.add(citation_id)
        if not citekey or citekey not in set(bib_keys):
            issues.append(CheckIssue("error", "unresolved_citekey", f"Citation {citation_id} has unresolved citekey: {citekey}"))

    active_journal_count = 0
    for profile_record in paper.get("journal_profiles", []):
        profile_path = folder / str(profile_record.get("path", ""))
        profile = load_yaml(profile_path)
        if profile.get("status", "active") == "active":
            active_journal_count += 1
        template_record = profile.get("official_template")
        if template_record:
            template_path = folder / str(template_record.get("path", ""))
            if not template_path.is_file():
                issues.append(CheckIssue("error", "missing_template", f"Official template missing: {template_path}"))
            elif sha256_file(template_path) != template_record.get("sha256"):
                issues.append(CheckIssue("error", "template_hash_changed", f"Official template changed: {template_path}"))
        derived = folder / str(profile.get("derived_manuscript", ""))
        if derived.is_file():
            issues.extend(audit_docx(derived, blind_review=bool(profile.get("blind_review"))))

    if paper.get("gates", {}).get("G2", {}).get("approved") and active_journal_count != 1:
        issues.append(CheckIssue("error", "missing_journal_profile", "G2 requires exactly one active journal profile"))
    if paper.get("gates", {}).get("G4", {}).get("approved"):
        submission_docs = sorted((folder / "05_submission").glob("*.docx"))
        if not submission_docs:
            issues.append(CheckIssue("error", "missing_submission_docx", "G4 is approved but no submission DOCX exists"))
        for document in submission_docs:
            issues.extend(audit_docx(document))
    return issues


def check_all(root: Path) -> dict[str, list[CheckIssue]]:
    results = {}
    for folder in paper_dirs(root):
        paper_id = str(read_paper(folder).get("paper_id"))
        results[paper_id] = check_paper(root, paper_id)
    return results


def format_issues(issues: Iterable[CheckIssue]) -> str:
    items = list(issues)
    if not items:
        return "PASS: no issues found"
    return "\n".join(f"{item.severity.upper()} [{item.code}] {item.message}" for item in items)

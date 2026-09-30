from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from paperflow.core import (
    PaperflowError,
    approve_gate,
    audit_docx,
    check_paper,
    create_paper,
    extract_translation_units,
    freeze_source,
    init_journal,
    load_yaml,
    set_status,
)


def issue_codes(issues):
    return {issue.code for issue in issues}


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def make_docx(path: Path, *, body: str, comments: bool = False, creator: str = "") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f"<w:document xmlns:w='w'><w:body>{body}</w:body></w:document>")
        archive.writestr(
            "docProps/core.xml",
            "<cp:coreProperties xmlns:cp='cp' xmlns:dc='dc'>"
            f"<dc:creator>{creator}</dc:creator><cp:lastModifiedBy>{creator}</cp:lastModifiedBy>"
            "</cp:coreProperties>",
        )
        if comments:
            archive.writestr("word/comments.xml", "<w:comments xmlns:w='w'/>")


def test_create_multiple_papers_and_rebuild_status(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    first = create_paper(root, title="中文论文", slug="existing-study", entry="existing_chinese", year=2026)
    second = create_paper(root, title="New research", slug="new-study", entry="new_research", year=2026)

    assert first.name == "P-2026-001-existing-study"
    assert second.name == "P-2026-002-new-study"
    index = load_yaml(root / "INDEX.yaml")
    assert [item["paper_id"] for item in index["papers"]] == ["P-2026-001", "P-2026-002"]
    status = (root / "STATUS.md").read_text(encoding="utf-8")
    assert "P-2026-001" in status and "P-2026-002" in status
    assert load_yaml(first / "PAPER.yaml")["tracks"]["research_status"] == "not_applicable"
    assert load_yaml(second / "PAPER.yaml")["overall_status"] == "idea"


def test_frozen_source_is_never_overwritten_and_hash_changes_are_detected(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    folder = create_paper(root, title="Source test", slug="source-test", entry="existing_chinese", year=2026)
    source = tmp_path / "manuscript.docx"
    source.write_bytes(b"original")
    frozen = freeze_source(root, "P-2026-001", source)

    with pytest.raises(PaperflowError, match="Refusing to overwrite frozen source"):
        freeze_source(root, "P-2026-001", source)
    assert not check_paper(root, "P-2026-001")

    frozen.write_bytes(b"changed")
    assert "source_hash_changed" in issue_codes(check_paper(root, "P-2026-001"))
    assert folder.joinpath("00_source/manuscript.docx").exists()


def test_gate_order_and_status_transitions(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    create_paper(root, title="Gate test", slug="gate-test", entry="existing_chinese", year=2026)
    source = tmp_path / "source.docx"
    source.write_bytes(b"frozen source")
    freeze_source(root, "P-2026-001", source)

    with pytest.raises(PaperflowError, match="before G0"):
        approve_gate(root, "P-2026-001", "G1", "premature")
    approve_gate(root, "P-2026-001", "G0", "scope approved")
    set_status(root, "P-2026-001", "translating")
    with pytest.raises(PaperflowError, match="Illegal status transition"):
        set_status(root, "P-2026-001", "submitted")


def test_translation_and_evidence_validation(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    folder = create_paper(root, title="Translation", slug="translation", entry="existing_chinese", year=2026)
    write_jsonl(
        folder / "02_translation/segments.jsonl",
        [
            {
                "unit_id": "P001",
                "kind": "paragraph",
                "source_zh": "原文",
                "candidate_en": "Draft",
                "final_en": "",
                "status": "confirmed",
            }
        ],
    )
    write_jsonl(
        folder / "evidence/claims.jsonl",
        [{"claim_id": "C001", "text": "Core claim", "core": True, "evidence_ids": ["E404"]}],
    )

    codes = issue_codes(check_paper(root, "P-2026-001"))
    assert "missing_final_translation" in codes
    assert "missing_evidence_link" in codes


def test_journal_template_is_hashed_and_change_is_detected(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    folder = create_paper(root, title="Journal", slug="journal", entry="new_research", year=2026)
    template = tmp_path / "template.docx"
    template.write_bytes(b"official")
    journal_dir = init_journal(
        root,
        "P-2026-001",
        journal="Example Journal",
        article_type="Original Article",
        guidelines_url="https://journal.example/official-guidelines",
        verified_at="2026-07-16",
        template=template,
    )
    assert "UNRESOLVED" in (journal_dir / "artifact.md").read_text(encoding="utf-8")
    official = journal_dir / "official/template.docx"
    official.write_bytes(b"modified")
    assert "template_hash_changed" in issue_codes(check_paper(root, "P-2026-001"))
    assert folder.joinpath("04_journal/example-journal/journal.yaml").exists()


def test_docx_structural_audit_detects_submission_residue(tmp_path: Path) -> None:
    document = tmp_path / "submission.docx"
    make_docx(document, body="<w:ins><w:r><w:t>TODO</w:t></w:r></w:ins>", comments=True, creator="Researcher")
    codes = issue_codes(audit_docx(document, blind_review=True))
    assert {"comments_present", "tracked_changes_present", "placeholder_present", "identity_metadata"} <= codes


def test_clean_minimal_docx_passes_structural_audit(tmp_path: Path) -> None:
    document = tmp_path / "clean.docx"
    make_docx(document, body="<w:p><w:r><w:t>Clean manuscript</w:t></w:r></w:p>")
    assert audit_docx(document) == []


def test_extract_docx_creates_stable_units_without_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    folder = create_paper(root, title="Extract", slug="extract", entry="existing_chinese", year=2026)
    source = tmp_path / "source.docx"
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document_xml = (
        f"<w:document xmlns:w='{ns}'><w:body>"
        "<w:p><w:r><w:t>第一段</w:t></w:r></w:p>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格内容</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document_xml)
    freeze_source(root, "P-2026-001", source)

    assert extract_translation_units(root, "P-2026-001") == 2
    records = [json.loads(line) for line in (folder / "02_translation/segments.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [item["unit_id"] for item in records] == ["U000001", "U000002"]
    assert [item["kind"] for item in records] == ["paragraph", "table_cell"]
    with pytest.raises(PaperflowError, match="Refusing to overwrite"):
        extract_translation_units(root, "P-2026-001")


def test_citation_keys_must_resolve_to_bibtex(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    folder = create_paper(root, title="Citations", slug="citations", entry="new_research", year=2026)
    (folder / "references/library.bib").write_text("@article{known2026, title={Known}}\n", encoding="utf-8")
    write_jsonl(
        folder / "references/citations.jsonl",
        [{"citation_id": "R001", "citekey": "missing2026", "locator": "03_manuscript/master_en.docx"}],
    )
    assert "unresolved_citekey" in issue_codes(check_paper(root, "P-2026-001"))

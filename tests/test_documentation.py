from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from argparse import _SubParsersAction
from pathlib import Path

from paperflow.cli import build_parser
from paperflow.core import GATES, OVERALL_STATUSES, TRACK_STATUSES, load_yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANUAL = PROJECT_ROOT / "docs" / "USER_MANUAL.md"
README = PROJECT_ROOT / "papers" / "README.md"
CLI_COMMANDS = (
    "new",
    "freeze-source",
    "extract-docx",
    "journal-init",
    "journal-status",
    "journal-qa",
    "set-status",
    "set-track",
    "approve-gate",
    "rebuild",
    "check",
    "docx-audit",
    "web",
)


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "paperflow", "--root", str(root), *arguments],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def make_extractable_docx(path: Path) -> None:
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document_xml = (
        f"<w:document xmlns:w='{namespace}'><w:body>"
        "<w:p><w:r><w:t>用于手册测试的中文段落。</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document_xml)


def test_manual_covers_cli_states_tracks_and_gates() -> None:
    text = MANUAL.read_text(encoding="utf-8")
    parser = build_parser()
    subparsers = next(action for action in parser._actions if isinstance(action, _SubParsersAction))

    assert set(subparsers.choices) == set(CLI_COMMANDS)
    for command in CLI_COMMANDS:
        assert f"`{command}`" in text
    for status in OVERALL_STATUSES:
        assert f"`{status}`" in text
    for status in TRACK_STATUSES:
        assert f"`{status}`" in text
    for gate in GATES:
        assert gate in text

    # The current public data model contains the 15 states listed in the manual.
    # This assertion makes a future API change update the manual and this test together.
    assert len(OVERALL_STATUSES) == 15
    assert len(TRACK_STATUSES) == 5
    assert len(GATES) == 6


def test_local_markdown_links_resolve() -> None:
    documents = (MANUAL, README)
    link_pattern = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")

    for document in documents:
        text = document.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (document.parent / target).resolve()
            assert resolved.exists(), f"Broken link in {document}: {raw_target}"

    assert "../docs/USER_MANUAL.md" in README.read_text(encoding="utf-8")


def test_safe_manual_command_sequence_in_temporary_portfolio(tmp_path: Path) -> None:
    papers_root = tmp_path / "papers"
    source = tmp_path / "manual-source.docx"
    make_extractable_docx(source)

    created = run_cli(
        papers_root,
        "new",
        "--title",
        "Manual verification paper",
        "--slug",
        "manual-verification",
        "--entry",
        "existing_chinese",
        "--year",
        "2026",
    )
    assert created.returncode == 0, created.stderr
    assert "P-2026-001-manual-verification" in created.stdout

    frozen = run_cli(papers_root, "freeze-source", "P-2026-001", str(source))
    assert frozen.returncode == 0, frozen.stderr
    assert "00_source/manual-source.docx" in frozen.stdout

    extracted = run_cli(papers_root, "extract-docx", "P-2026-001")
    assert extracted.returncode == 0, extracted.stderr
    assert "Extracted 1 translation unit(s)" in extracted.stdout

    approved = run_cli(
        papers_root,
        "approve-gate",
        "P-2026-001",
        "G0",
        "--note",
        "Manual test scope approved",
    )
    assert approved.returncode == 0, approved.stderr

    transitioned = run_cli(papers_root, "set-status", "P-2026-001", "translating")
    assert transitioned.returncode == 0, transitioned.stderr

    rebuilt = run_cli(papers_root, "rebuild")
    assert rebuilt.returncode == 0, rebuilt.stderr
    assert "Rebuilt portfolio with 1 paper(s)" in rebuilt.stdout

    checked = run_cli(papers_root, "check", "--all")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "PASS: no issues found" in checked.stdout

    paper = load_yaml(papers_root / "P-2026-001-manual-verification" / "PAPER.yaml")
    assert paper["overall_status"] == "translating"
    assert paper["gates"]["G0"]["approved"] is True
    assert paper["tracks"]["translation_status"] == "in_progress"
    assert "P-2026-001" in (papers_root / "STATUS.md").read_text(encoding="utf-8")

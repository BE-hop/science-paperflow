from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .core import (
    OVERALL_STATUSES,
    TRACK_STATUSES,
    PaperflowError,
    approve_gate,
    audit_docx,
    check_all,
    check_paper,
    create_paper,
    extract_translation_units,
    format_issues,
    freeze_source,
    init_journal,
    papers_root,
    rebuild_portfolio,
    record_journal_qa,
    set_journal_status,
    set_status,
    set_track,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperflow", description="Manage local SCI paper projects")
    parser.add_argument("--root", help="Paper portfolio root (default: ./papers or PAPERFLOW_ROOT)")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="Create an isolated paper project")
    new.add_argument("--title", required=True)
    new.add_argument("--slug", required=True, help="Short ASCII folder slug")
    new.add_argument("--entry", choices=("existing_chinese", "new_research"), required=True)
    new.add_argument("--year", type=int, default=datetime.now().year)

    freeze = sub.add_parser("freeze-source", help="Copy and hash an immutable source manuscript")
    freeze.add_argument("paper")
    freeze.add_argument("source", type=Path)

    extract = sub.add_parser("extract-docx", help="Extract stable translation units from one frozen DOCX")
    extract.add_argument("paper")
    extract.add_argument("--source-name", help="Required when more than one frozen source is registered")

    journal = sub.add_parser("journal-init", help="Create a journal profile without modifying the official template")
    journal.add_argument("paper")
    journal.add_argument("--journal", required=True)
    journal.add_argument("--article-type", required=True)
    journal.add_argument("--guidelines-url", required=True)
    journal.add_argument("--verified-at", required=True, help="ISO date or timestamp")
    journal.add_argument("--template", type=Path)

    journal_status = sub.add_parser("journal-status", help="Activate, supersede, or withdraw a journal target")
    journal_status.add_argument("paper")
    journal_status.add_argument("journal_id")
    journal_status.add_argument("status", choices=("active", "superseded", "withdrawn"))
    journal_status.add_argument("--note", required=True)

    journal_qa = sub.add_parser("journal-qa", help="Record structural or human visual QA evidence")
    journal_qa.add_argument("paper")
    journal_qa.add_argument("journal_id")
    journal_qa.add_argument("check", choices=("structural_audit", "render_review"))
    journal_qa.add_argument("result", choices=("pass", "fail"))
    journal_qa.add_argument("--evidence", required=True)
    journal_qa.add_argument("--reviewer", default="")

    status = sub.add_parser("set-status", help="Apply a validated overall state transition")
    status.add_argument("paper")
    status.add_argument("status", choices=OVERALL_STATUSES)

    track = sub.add_parser("set-track", help="Update one independent workstream")
    track.add_argument("paper")
    track.add_argument("track", choices=("research_status", "manuscript_status", "translation_status", "journal_status", "submission_status"))
    track.add_argument("status", choices=TRACK_STATUSES)

    gate = sub.add_parser("approve-gate", help="Record an explicit human approval")
    gate.add_argument("paper")
    gate.add_argument("gate", choices=("G0", "G1", "G2", "G3", "G4", "G5"))
    gate.add_argument("--note", required=True)

    sub.add_parser("rebuild", help="Rebuild INDEX.yaml and STATUS.md from PAPER.yaml files")

    check = sub.add_parser("check", help="Validate one paper or the whole portfolio")
    target = check.add_mutually_exclusive_group(required=True)
    target.add_argument("--paper")
    target.add_argument("--all", action="store_true")

    docx = sub.add_parser("docx-audit", help="Structurally inspect a DOCX before rendered visual QA")
    docx.add_argument("document", type=Path)
    docx.add_argument("--blind-review", action="store_true")

    web = sub.add_parser("web", help="Open the local Paperflow browser workbench")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true")
    return parser


def run(args: argparse.Namespace) -> int:
    root = papers_root(args.root)
    if args.command == "new":
        folder = create_paper(root, title=args.title, slug=args.slug, entry=args.entry, year=args.year)
        print(folder)
        return 0
    if args.command == "freeze-source":
        print(freeze_source(root, args.paper, args.source))
        return 0
    if args.command == "extract-docx":
        count = extract_translation_units(root, args.paper, args.source_name)
        print(f"Extracted {count} translation unit(s)")
        return 0
    if args.command == "journal-init":
        print(
            init_journal(
                root,
                args.paper,
                journal=args.journal,
                article_type=args.article_type,
                guidelines_url=args.guidelines_url,
                verified_at=args.verified_at,
                template=args.template,
            )
        )
        return 0
    if args.command == "journal-status":
        set_journal_status(root, args.paper, args.journal_id, args.status, args.note)
        return 0
    if args.command == "journal-qa":
        record_journal_qa(
            root,
            args.paper,
            args.journal_id,
            check=args.check,
            passed=args.result == "pass",
            evidence=args.evidence,
            reviewer=args.reviewer,
        )
        return 0
    if args.command == "set-status":
        set_status(root, args.paper, args.status)
        return 0
    if args.command == "set-track":
        set_track(root, args.paper, args.track, args.status)
        return 0
    if args.command == "approve-gate":
        approve_gate(root, args.paper, args.gate, args.note)
        return 0
    if args.command == "rebuild":
        records = rebuild_portfolio(root)
        print(f"Rebuilt portfolio with {len(records)} paper(s)")
        return 0
    if args.command == "check":
        if args.all:
            results = check_all(root)
            failed = False
            for paper_id, issues in results.items():
                print(f"## {paper_id}\n{format_issues(issues)}")
                failed = failed or any(issue.severity == "error" for issue in issues)
            if not results:
                print("PASS: no papers registered")
            return 1 if failed else 0
        issues = check_paper(root, args.paper)
        print(format_issues(issues))
        return 1 if any(issue.severity == "error" for issue in issues) else 0
    if args.command == "docx-audit":
        issues = audit_docx(args.document.expanduser().resolve(), blind_review=args.blind_review)
        print(format_issues(issues))
        return 1 if any(issue.severity == "error" for issue in issues) else 0
    if args.command == "web":
        from .web import run_web

        run_web(root, port=args.port, open_browser=not args.no_browser)
        return 0
    raise PaperflowError(f"Unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except PaperflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

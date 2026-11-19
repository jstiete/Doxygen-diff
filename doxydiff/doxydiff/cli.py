"""Command line interface for doxydiff."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .report import build_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="doxydiff",
        description="Compare Doxygen XML documentation output between two versions of a project "
        "and generate a git-diff style HTML report.",
    )
    parser.add_argument("--old-xml", required=True, help="Path to the Doxygen XML output directory of the OLD version")
    parser.add_argument("--new-xml", required=True, help="Path to the Doxygen XML output directory of the NEW version")
    parser.add_argument("--old-html", default=None, help="Path to the Doxygen HTML output directory of the OLD version (needed for call/inheritance graph diffs and doc-links; requires DOT_CLEANUP=NO)")
    parser.add_argument("--new-html", default=None, help="Path to the Doxygen HTML output directory of the NEW version")
    parser.add_argument("--out", required=True, help="Output directory for the generated HTML report")
    parser.add_argument("--dot", default="dot", help="Path to the Graphviz 'dot' executable (default: 'dot' on PATH)")
    parser.add_argument(
        "--mmdc", default="npx --yes @mermaid-js/mermaid-cli",
        help="Command used to render Mermaid diagrams (\\mermaid ... \\endmermaid) via the Mermaid CLI. "
        "Requires Node.js; default downloads/runs the CLI on demand via npx so no global install is needed.",
    )
    parser.add_argument("--name", default="Project", help="Project name shown in the report header")

    ci_group = parser.add_argument_group(
        "CI / regression checks",
        "If any of these thresholds is exceeded, doxydiff exits with code 1 so a CI pipeline "
        "can fail the build (e.g. to catch accidentally deleted documentation).",
    )
    ci_group.add_argument("--max-removed-members", type=int, default=None, help="Fail if more than N members (functions/variables/...) were removed")
    ci_group.add_argument("--max-removed-compounds", type=int, default=None, help="Fail if more than N compounds (classes/namespaces/files/...) were removed")
    ci_group.add_argument("--max-doc-lines-removed", type=int, default=None, help="Fail if more than N documentation lines were removed")
    ci_group.add_argument("--max-doc-lines-removed-pct", type=float, default=None, help="Fail if more than X%% of the OLD version's total documentation lines were removed")
    ci_group.add_argument("--json-summary", default=None, metavar="PATH", help="Write a machine-readable JSON summary of the change statistics to PATH")

    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase log verbosity: -v for progress info, -vv for debug details (e.g. every parsed dot file). "
        "Without this flag only warnings/errors are printed.",
    )

    args = parser.parse_args(argv)

    log_level = {0: logging.WARNING, 1: logging.INFO}.get(args.verbose, logging.DEBUG)
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    result = build_report(
        old_xml=args.old_xml,
        new_xml=args.new_xml,
        out_dir=args.out,
        old_html=args.old_html,
        new_html=args.new_html,
        dot_exe=args.dot,
        mmdc_cmd=args.mmdc,
        project_name=args.name,
    )
    stats = result.stats

    print(f"Report written to: {result.out_path}")
    print(
        "Summary: "
        f"compounds +{stats.compounds_added}/-{stats.compounds_removed}/~{stats.compounds_modified}, "
        f"members +{stats.members_added}/-{stats.members_removed}/~{stats.members_modified}/moved:{stats.members_moved}, "
        f"images changed: {stats.images_changed}, graphs changed: {stats.graphs_changed}, "
        f"mermaid diagrams changed: {stats.mermaid_changed}, "
        f"doc lines +{stats.lines_added}/-{stats.lines_removed} "
        f"({stats.lines_removed_pct}% of old total removed)"
    )

    if args.json_summary:
        with open(args.json_summary, "w", encoding="utf-8") as f:
            json.dump(stats.as_dict(), f, indent=2)
        print(f"JSON summary written to: {args.json_summary}")

    failures = []
    if args.max_removed_members is not None and stats.members_removed > args.max_removed_members:
        failures.append(f"members_removed={stats.members_removed} > --max-removed-members={args.max_removed_members}")
    if args.max_removed_compounds is not None and stats.compounds_removed > args.max_removed_compounds:
        failures.append(f"compounds_removed={stats.compounds_removed} > --max-removed-compounds={args.max_removed_compounds}")
    if args.max_doc_lines_removed is not None and stats.lines_removed > args.max_doc_lines_removed:
        failures.append(f"lines_removed={stats.lines_removed} > --max-doc-lines-removed={args.max_doc_lines_removed}")
    if args.max_doc_lines_removed_pct is not None and stats.lines_removed_pct > args.max_doc_lines_removed_pct:
        failures.append(f"lines_removed_pct={stats.lines_removed_pct}% > --max-doc-lines-removed-pct={args.max_doc_lines_removed_pct}%")

    if failures:
        print("REGRESSION DETECTED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

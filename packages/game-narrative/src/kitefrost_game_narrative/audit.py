"""Continuity-audit your own Ink / Yarn files - from Python or CI.

Hand-written (not generated): reads local files and calls the generated
``continuity.audit_files`` endpoint. Concept game-narrative-file-audit-surface.

CI usage::

    kitefrost-gn-audit dialogue/ --project <project_id> --fail-on error --sarif audit.sarif

Exit codes: 0 = no finding at/above --fail-on; 1 = findings; 2 = usage / API error.
Needs KITEFROST_API_KEY (and KITEFROST_BASE_URL while in alpha).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

EXTENSIONS = (".ink", ".yarn")
SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}


def collect_files(root: str | Path) -> list[dict[str, str]]:
    """Every .ink / .yarn file under ``root`` (or ``root`` itself), paths relative to it."""
    base = Path(root)
    paths = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
    out = []
    for p in paths:
        if p.suffix.lower() in EXTENSIONS:
            rel = p.name if base.is_file() else str(p.relative_to(base))
            out.append({"path": rel, "content": p.read_text(encoding="utf-8")})
    return out


def audit_path(client: Any, project_id: str, root: str | Path, *, entities: dict | None = None, sarif: bool = False):
    """Audit the Ink / Yarn files under ``root``. ``client`` is a GameNarrativeClient."""
    files = collect_files(root)
    if not files:
        raise ValueError(f"no .ink or .yarn files under {root}")
    body: dict[str, Any] = {"files": files, "sarif": sarif}
    if entities:
        body["entities"] = entities
    return client.continuity.audit_files(project_id, body)


def failing_findings(result: dict, fail_on: str) -> list[dict]:
    threshold = SEVERITY_RANK[fail_on]
    findings = (result.get("report") or {}).get("findings") or []
    return [f for f in findings if SEVERITY_RANK.get(str(f.get("severity", "")).lower(), 0) >= threshold]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kitefrost-gn-audit", description=__doc__.splitlines()[0])
    ap.add_argument("path", help="directory (or single file) of .ink / .yarn files")
    ap.add_argument("--project", required=True, help="KiteFrost project id")
    ap.add_argument("--fail-on", choices=list(SEVERITY_RANK), default="error")
    ap.add_argument("--sarif", help="write a SARIF 2.1.0 log to this path (CI annotations)")
    ap.add_argument("--entities", help="JSON file: variable -> [type, ref, attribute]")
    args = ap.parse_args(argv)

    api_key = os.environ.get("KITEFROST_API_KEY")
    if not api_key:
        print("kitefrost-gn-audit: set KITEFROST_API_KEY", file=sys.stderr)
        return 2
    from .client import GameNarrativeClient  # noqa: PLC0415

    client = GameNarrativeClient.from_api_key(api_key)
    entities = json.loads(Path(args.entities).read_text(encoding="utf-8")) if args.entities else None
    try:
        result = audit_path(client, args.project, args.path, entities=entities, sarif=bool(args.sarif))
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 2
        print(f"kitefrost-gn-audit: {exc}", file=sys.stderr)
        return 2
    if args.sarif and result.get("sarif"):
        Path(args.sarif).write_text(json.dumps(result["sarif"], indent=2), encoding="utf-8")
    bad = failing_findings(result, args.fail_on)
    for f in (result.get("report") or {}).get("findings") or []:
        print(f"{str(f.get('severity', '')).upper():7} {f.get('source_locus') or ''}  {f.get('message', '')}")
    print(f"kitefrost-gn-audit: {result.get('files_audited', 0)} file(s), {len(bad)} at/above {args.fail_on}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

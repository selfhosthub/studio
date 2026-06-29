#!/usr/bin/env python3
# scripts/parse-codeql-sarif.py
#
# Parse a CodeQL SARIF file: print a per-language summary, exit 1 if any
# error-severity result is present. Warnings are reported, not failed.
#
# Two exclusion layers (both read from the shared .github/codeql/ dir):
#   1. Rule-level: rule IDs under query-filters/exclude in config.yml are dropped
#      (the standalone CLI ignores query-filters at create time; GitHub honors them
#      at analyze - this keeps both on the same exclusion list).
#   2. Result-level: rule+path pairs in suppressions.json are dropped. Equivalent
#      to GitHub's "dismiss alert" for the local gate; the CLI does not honor
#      inline # codeql[rule-id] source comments in SARIF output.
#
# Usage: parse-codeql-sarif.py <sarif-path> <language-label> [config-path]

import json
import os
import re
import sys


def excluded_rule_ids(config_path):
    """Return rule IDs under query-filters/exclude in the codeql config (empty set if missing)."""
    try:
        with open(config_path) as f:
            text = f.read()
    except OSError:
        return set()
    block = re.split(r"^\s*paths-ignore:", text, maxsplit=1, flags=re.MULTILINE)[0]
    if "query-filters:" not in block:
        return set()
    qf = block.split("query-filters:", 1)[1]
    return set(re.findall(r"^\s*id:\s*(\S+)", qf, flags=re.MULTILINE))


def load_suppressions(config_path):
    """Return set of (rule_id, path) tuples from suppressions.json next to config."""
    suppress_path = os.path.join(os.path.dirname(config_path), "suppressions.json")
    try:
        with open(suppress_path) as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return set()
    return {(e["rule"], e["path"]) for e in entries if "rule" in e and "path" in e}


def severity(result, rules_by_id):
    """Resolve a result's level, falling back to its rule's default config."""
    level = result.get("level")
    if level:
        return level
    rule = rules_by_id.get(result.get("ruleId", ""), {})
    return rule.get("defaultConfiguration", {}).get("level", "warning")


def result_uri(result):
    """Return the primary artifact URI for a result, or ''."""
    locs = result.get("locations", [])
    if not locs:
        return ""
    phys = locs[0].get("physicalLocation", {})
    return phys.get("artifactLocation", {}).get("uri", "")


def location(result):
    """Return the result's primary 'file:line', or '?' when unavailable."""
    locs = result.get("locations", [])
    if not locs:
        return "?"
    phys = locs[0].get("physicalLocation", {})
    uri = phys.get("artifactLocation", {}).get("uri", "?")
    line = phys.get("region", {}).get("startLine")
    return f"{uri}:{line}" if line else uri


def main():
    if not 3 <= len(sys.argv) <= 4:
        print(
            "usage: parse-codeql-sarif.py <sarif-path> <language-label> [config-path]",
            file=sys.stderr,
        )
        return 2
    path, lang = sys.argv[1], sys.argv[2]
    config = sys.argv[3] if len(sys.argv) == 4 else None
    excluded = excluded_rule_ids(config) if config else set()
    suppressed = load_suppressions(config) if config else set()

    try:
        with open(path) as f:
            sarif = json.load(f)
    except (OSError, ValueError) as e:
        print(f"  {lang}: could not read SARIF ({e})")
        return 1

    errors, warnings = [], []
    for run in sarif.get("runs", []):
        rules_by_id = {
            r.get("id", ""): r
            for r in run.get("tool", {}).get("driver", {}).get("rules", [])
        }
        for result in run.get("results", []):
            rule_id = result.get("ruleId", "?")
            if rule_id in excluded:
                continue
            # Skip results suppressed via suppressions.json (rule+path match).
            uri = result_uri(result)
            if (rule_id, uri) in suppressed:
                continue
            # Skip results suppressed inline in source (kind: inSource in SARIF).
            if any(s.get("kind") == "inSource" for s in result.get("suppressions", [])):
                continue
            level = severity(result, rules_by_id)
            # Collapse multi-line CodeQL messages to their first line.
            msg = result.get("message", {}).get("text", "").splitlines()[0:1]
            msg = msg[0] if msg else ""
            entry = (rule_id, location(result), msg)
            if level == "error":
                errors.append(entry)
            elif level == "warning":
                warnings.append(entry)

    if not errors and not warnings:
        print(f"  {lang}: clean")
        return 0

    print(f"  {lang}: {len(errors)} error(s), {len(warnings)} warning(s)")
    for rule_id, loc, msg in errors:
        print(f"    ERROR  {loc}  [{rule_id}] {msg}")
    for rule_id, loc, msg in warnings:
        print(f"    warn   {loc}  [{rule_id}] {msg}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

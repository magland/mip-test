#!/usr/bin/env python3
"""Validate or apply a build request described in a GitHub issue.

The issue's job is just to **trigger a build** of a package already
present in this channel under `packages/<name>/<version>/`. The
workflow does not clone, copy, or commit anything — it only dispatches
the per-package build workflow on approval.

Free-form input. The body (or title) needs to contain:

  1. A package path `packages/<name>/<version>` (the path can appear
     bare or inside a GitHub URL — only the path portion is used).
  2. Exactly one architecture keyword:
     `any`, `linux_x86_64`, `macos_arm64`, `windows_x86_64`.

Subcommands:

    validate --output-file PATH [--title-file PATH] [--repo-root DIR]
        Render the comment to post on issue-open. Confirms the named
        package folder exists in this repo.

    apply --dispatch-file PATH [--errors-file PATH] [--repo-root DIR]
        Re-parse the issue and write `<package_path>\\t<architecture>`
        to --dispatch-file so the workflow can dispatch the build.
"""

import argparse
import os
import re
import sys
from pathlib import Path


PACKAGE_PATH_RE = re.compile(
    r"\bpackages/[A-Za-z0-9._+\-]+/[A-Za-z0-9._+\-]+"
)

VALID_ARCHITECTURES = (
    "any", "linux_x86_64", "macos_arm64", "windows_x86_64",
)

ARCH_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(a) for a in VALID_ARCHITECTURES) + r")\b"
)

URL_RE = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/tree/[^/\s]+/[^\s)]+"
)

PATH_FORMAT_HINT = "    packages/<name>/<version>"


def get_effective_body():
    """Title + body, joined; lets users put the request in the title."""
    body = os.environ.get("ISSUE_BODY", "")
    title = os.environ.get("ISSUE_TITLE", "")
    if title.strip():
        return title + "\n\n" + body
    return body


def parse_issue(body, repo_root):
    """Return (entry_or_None, errors)."""
    body = body.replace("\r", "")

    # Find unique package paths (deduped, preserving order).
    paths = list(dict.fromkeys(PACKAGE_PATH_RE.findall(body)))

    # Strip URLs and package paths so arch detection isn't fooled by
    # a version that happens to be named e.g. "any".
    body_for_arch = URL_RE.sub("", body)
    body_for_arch = PACKAGE_PATH_RE.sub("", body_for_arch)
    arch_hits = list(dict.fromkeys(ARCH_RE.findall(body_for_arch)))

    errors = []
    if not paths:
        errors.append(
            "- No package path found. Include a path of the form:\n\n"
            f"{PATH_FORMAT_HINT}"
        )
    elif len(paths) > 1:
        joined = ", ".join(f"`{p}`" for p in paths)
        errors.append(
            f"- Multiple package paths detected ({joined}); submit one "
            "build request per issue."
        )

    if not arch_hits:
        errors.append(
            "- No architecture specified. Include exactly one of: "
            + ", ".join(f"`{a}`" for a in VALID_ARCHITECTURES) + "."
        )
    elif len(arch_hits) > 1:
        joined = ", ".join(f"`{a}`" for a in arch_hits)
        errors.append(
            f"- Multiple architectures detected ({joined}); include "
            "exactly one."
        )

    if errors:
        return None, errors

    package_path = paths[0]
    architecture = arch_hits[0]
    parts = package_path.split("/")
    name, version = parts[1], parts[2]

    folder = repo_root / package_path
    exists = folder.is_dir()
    if not exists:
        errors.append(
            f"- `{package_path}` does not exist in this channel."
        )
        return None, errors

    return {
        "package_path": package_path,
        "name": name,
        "version": version,
        "architecture": architecture,
    }, []


def render_validation_comment(entry, errors):
    if errors or not entry:
        lines = ["The issue is not formatted correctly."]
        lines += ["", "Errors:"] + errors
        lines += [
            "",
            "Edit the issue body or open a new one with a package path "
            "and an architecture keyword.",
        ]
        return "\n".join(lines) + "\n"

    pkg_label = (
        f"{entry['name']}@{entry['version']} ({entry['architecture']})"
    )
    lines = [
        f"Detected build request: `{pkg_label}`",
        "",
        f"- Package: `{entry['package_path']}`",
        f"- Architecture: `{entry['architecture']}`",
        "",
        "An admin (anyone with write access on this repo) can approve "
        "this request by replying with `approve` on its own line. On "
        "approval, `build-package.yml` will be dispatched for this "
        "(package, architecture) pair — no files are copied or "
        "modified.",
    ]
    return "\n".join(lines) + "\n"


def canonical_title(entry):
    if not entry:
        return None
    return (
        f"Build: `{entry['package_path']}` ({entry['architecture']})"
    )


def cmd_validate(args):
    body = get_effective_body()
    repo_root = Path(args.repo_root).resolve()
    entry, errors = parse_issue(body, repo_root)
    Path(args.output_file).write_text(
        render_validation_comment(entry, errors)
    )
    if args.title_file:
        title = canonical_title(entry) or ""
        Path(args.title_file).write_text(title + ("\n" if title else ""))
    return 0


def cmd_apply(args):
    body = get_effective_body()
    repo_root = Path(args.repo_root).resolve()
    entry, errors = parse_issue(body, repo_root)
    if entry is None:
        Path(args.dispatch_file).write_text("")
        if args.errors_file:
            Path(args.errors_file).write_text(
                "\n".join(errors) + ("\n" if errors else "")
            )
        return 1
    Path(args.dispatch_file).write_text(
        f"{entry['package_path']}\t{entry['architecture']}\n"
    )
    if args.errors_file:
        Path(args.errors_file).write_text("")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    v = sub.add_parser("validate")
    v.add_argument("--output-file", required=True)
    v.add_argument("--title-file", default=None)
    v.add_argument("--repo-root", default=".")
    v.set_defaults(func=cmd_validate)

    a = sub.add_parser("apply")
    a.add_argument("--dispatch-file", required=True)
    a.add_argument("--errors-file", default=None)
    a.add_argument("--repo-root", default=".")
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

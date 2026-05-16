#!/usr/bin/env python3
"""Validate or apply a single package addition described in a GitHub issue.

The issue is expected to come from .github/ISSUE_TEMPLATE/add-package.yml,
whose form produces a body shaped like:

    ### Package URL

    https://github.com/<owner>/<repo>/tree/<branch>/packages/<name>/<version>

    ### Architecture

    linux_x86_64

This script extracts the URL and architecture from the body (read via
$ISSUE_BODY).

Subcommands:

    validate --output-file PATH [--title-file PATH]
        Render the comment to post on issue-open.

    apply --report-file PATH --errors-file PATH --dispatch-file PATH \
            [--repo-root DIR]
        Clone the source repo, copy packages/<name>/<version> into
        --repo-root, and write `<package_path>\t<architecture>` to
        --dispatch-file on success so the workflow can dispatch a build.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


URL_RE = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/tree/[^/\s]+/[^\s)]+"
)

VALID_ARCHITECTURES = {
    "any", "linux_x86_64", "macos_arm64", "windows_x86_64",
}

URL_FORMAT_HINT = (
    "    https://github.com/<owner>/<repo>/tree/<branch>"
    "/packages/<name>/<version>"
)


def _parse_url(url):
    """Return (owner, repo, branch, path) or None."""
    if not url.startswith("https://github.com/"):
        return None
    rest = url[len("https://github.com/"):].rstrip("/")
    parts = rest.split("/")
    if len(parts) < 5 or parts[2] != "tree":
        return None
    owner, repo, _, branch = parts[:4]
    path = "/".join(parts[4:])
    if not owner or not repo or not branch or not path:
        return None
    return owner, repo, branch, path


def _extract_section(body, heading):
    """Pull the text under a `### <heading>` block from an issue-form body.

    Form bodies use the literal pattern '### <Label>' followed by a blank
    line and then the value. Returns the stripped value, or '' if absent.
    """
    pattern = re.compile(
        rf"^###\s+{re.escape(heading)}\s*\n+(.*?)(?=\n###\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(body)
    if not m:
        return ""
    return m.group(1).strip()


def parse_issue(body):
    """Return (entry_or_None, errors).

    entry on success: dict with keys url, owner, repo, branch, path,
    name, version, architecture, package_path.
    """
    body = body.replace("\r", "")
    url_section = _extract_section(body, "Package URL")
    arch_section = _extract_section(body, "Architecture")

    errors = []

    url = None
    if url_section:
        m = URL_RE.search(url_section)
        if m:
            url = m.group(0).rstrip("/").rstrip(")")
    if not url:
        # Fall back to any URL anywhere in the body (handles users editing
        # the body free-form after submission).
        m = URL_RE.search(body)
        if m:
            url = m.group(0).rstrip("/").rstrip(")")

    parsed_url = _parse_url(url) if url else None
    if not parsed_url:
        errors.append(
            "- Could not find a conforming package URL. Expected:\n\n"
            f"{URL_FORMAT_HINT}"
        )
        owner = repo = branch = path = name = version = None
    else:
        owner, repo, branch, path = parsed_url
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "packages" or ".." in parts:
            errors.append(
                f"- URL path `{path}` must be exactly "
                "`packages/<name>/<version>`."
            )
            name = version = None
        else:
            name, version = parts[1], parts[2]
            if not name or not version:
                errors.append(
                    "- URL path is missing package name or version."
                )

    architecture = arch_section.strip().split()[0] if arch_section else ""
    if not architecture:
        errors.append("- No architecture specified.")
    elif architecture not in VALID_ARCHITECTURES:
        errors.append(
            f"- Architecture `{architecture}` is not one of "
            f"{sorted(VALID_ARCHITECTURES)}."
        )

    if errors:
        return None, errors

    return {
        "url": url,
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "path": path,
        "name": name,
        "version": version,
        "architecture": architecture,
        "package_path": f"packages/{name}/{version}",
    }, []


def render_validation_comment(entry, errors, repo_root):
    if errors or not entry:
        lines = ["The issue is not formatted correctly."]
        lines += ["", "Errors:"] + errors
        lines += [
            "",
            "Please open a new issue using the *Add package* template.",
        ]
        return "\n".join(lines) + "\n"

    pkg_label = f"{entry['name']}@{entry['version']} ({entry['architecture']})"
    dest_exists = (
        repo_root / "packages" / entry['name'] / entry['version']
    ).is_dir()
    repo_id = f"{entry['owner']}/{entry['repo']}"
    repo_url = f"https://github.com/{entry['owner']}/{entry['repo']}"

    marker = (
        " **(already exists — will be replaced)**" if dest_exists else ""
    )

    lines = [
        f"Thanks for the request. Detected: `{pkg_label}`{marker}",
        "",
        f"- Source: [{repo_id}]({repo_url}) @ `{entry['branch']}`, "
        f"folder `{entry['path']}`",
        f"- Architecture: `{entry['architecture']}`",
        "",
        "An admin (anyone with write access on this repo) can approve "
        "this request by replying with `approve` on its own line. On "
        "approval, the source folder will be copied into `packages/` "
        "and the per-package build workflow will be dispatched for "
        f"architecture `{entry['architecture']}`.",
    ]
    if dest_exists:
        lines += [
            "",
            "Note: this package version already exists in the channel "
            "and will be completely replaced (no merging).",
        ]
    return "\n".join(lines) + "\n"


def canonical_title(entry):
    if not entry:
        return None
    return (
        f"Add package: `{entry['package_path']}` "
        f"({entry['architecture']})"
    )


def apply_entry(entry, repo_root):
    report = []
    errors = []
    changed = False

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_url = (
            f"https://github.com/{entry['owner']}/{entry['repo']}.git"
        )
        res = subprocess.run(
            ["git", "clone", "--depth", "1",
             "--branch", entry['branch'], clone_url, tmpdir],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            err_lines = (res.stderr or res.stdout).strip().splitlines()
            err_msg = err_lines[-1] if err_lines else "git clone failed"
            errors.append(
                f"- Failed to clone "
                f"`{entry['owner']}/{entry['repo']}@{entry['branch']}`: "
                f"{err_msg}"
            )
            return report, errors, changed

        src = Path(tmpdir) / entry['path']
        if not src.is_dir():
            errors.append(
                f"- Path `{entry['path']}` not found in "
                f"`{entry['owner']}/{entry['repo']}@{entry['branch']}`."
            )
            return report, errors, changed

        dest = repo_root / entry['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        replaced = dest.exists()
        if replaced:
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        verb = "Replaced" if replaced else "Added"
        report.append(
            f"- {verb} `{entry['package_path']}` from {entry['url']}"
        )
        changed = True
    return report, errors, changed


def cmd_validate(args):
    body = os.environ.get("ISSUE_BODY", "")
    repo_root = Path(args.repo_root).resolve()
    entry, errors = parse_issue(body)
    Path(args.output_file).write_text(
        render_validation_comment(entry, errors, repo_root)
    )
    if args.title_file:
        title = canonical_title(entry) or ""
        Path(args.title_file).write_text(title + ("\n" if title else ""))
    return 0


def cmd_apply(args):
    body = os.environ.get("ISSUE_BODY", "")
    repo_root = Path(args.repo_root).resolve()
    entry, parse_errors = parse_issue(body)

    if entry is None:
        Path(args.report_file).write_text("")
        Path(args.errors_file).write_text(
            "\n".join(parse_errors) + ("\n" if parse_errors else "")
        )
        Path(args.dispatch_file).write_text("")
        print("changed=false")
        return 0

    report, apply_errors, changed = apply_entry(entry, repo_root)
    errors = parse_errors + apply_errors

    Path(args.report_file).write_text(
        "\n".join(report) + ("\n" if report else "")
    )
    Path(args.errors_file).write_text(
        "\n".join(errors) + ("\n" if errors else "")
    )
    if changed:
        Path(args.dispatch_file).write_text(
            f"{entry['package_path']}\t{entry['architecture']}\n"
        )
    else:
        Path(args.dispatch_file).write_text("")
    print(f"changed={'true' if changed else 'false'}")
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
    a.add_argument("--report-file", required=True)
    a.add_argument("--errors-file", required=True)
    a.add_argument("--dispatch-file", required=True)
    a.add_argument("--repo-root", default=".")
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

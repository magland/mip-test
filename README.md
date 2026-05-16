# mip-test

Experimental MIP channel hosted at https://github.com/magland/mip-test. It uses a **per-package, per-architecture** build pipeline instead of the monolithic "build everything on every push" workflow of the older channels.

## Layout

```
packages/<name>/<release>/    # Same shape as other channels
  recipe.yaml                  # Required: source spec (git/zip, or inline)
  mip.yaml                     # Optional: overrides mip.yaml from source repo
  compile.m                    # Optional: arch-specific compile
  *.m                          # Optional: test scripts, etc.

scripts/
  channel_config.py            # Resolve owner/repo, build URLs, release tags
  prepare_one.py               # Prepare ONE (package, release, arch)
  bundle_one.m                 # Bundle ONE prepared dir via `mip bundle`
  test_one.m                   # mip install/load/test on a single .mhl
  upload_one.py                # Upload ONE .mhl + .mip.json to its release
  assemble_index.py            # Probe releases, write index.json

site/
  index.html                   # Static page that reads index.json
  README.md

.github/workflows/
  build-package.yml            # Per-package, per-arch pipeline (3 jobs)
  assemble-index.yml           # Manual: reassemble index without building
  add-package.yml              # Issue-driven submission + admin approval

.github/ISSUE_TEMPLATE/
  add-package.yml              # Issue form for submitters
```

## Build pipeline (`build-package.yml`)

Triggered manually via `workflow_dispatch`, or programmatically via `workflow_call`. Inputs:

- `package_path` — e.g. `packages/with_test/1.0.0`
- `architecture` — one of `any`, `linux_x86_64`, `macos_arm64`, `windows_x86_64`
- `force` (optional) — rebuild even if a matching .mhl is already published

Three jobs:

1. **build** — runs `prepare_one.py` then `bundle_one`. The runner OS is derived from `architecture`. Output is a single `.mhl` (+ `.mip.json`) uploaded as a workflow artifact. If the requested architecture isn't listed in the package's `mip.yaml`, or if a matching `.mhl` is already published with the same source hash, the job exits successfully with no artifact and downstream jobs are skipped.

2. **test-and-upload** — downloads the `.mhl`, runs `mip install` / `mip load` / `mip test`, and only on success uploads the `.mhl` + `.mip.json` to a GitHub Release named `{name}-{version}`.

3. **assemble-and-deploy** — runs `assemble_index.py` to walk all releases, regenerate `index.json`, and deploy along with `site/` to GitHub Pages.

Concurrent runs serialize at the Pages-deploy step via a single concurrency group (`pages`).

## Triggering a build

```
gh workflow run build-package.yml \
  -f package_path=packages/with_test/1.0.0 \
  -f architecture=any
```

Or programmatically from another workflow:

```yaml
jobs:
  build_one:
    uses: ./.github/workflows/build-package.yml
    with:
      package_path: packages/mex_dot/1.0.0
      architecture: linux_x86_64
```

A dispatcher workflow that auto-detects which `(package, arch)` pairs need rebuilding and fans out to `build-package.yml` is planned but not yet implemented.

## Issue-driven submission flow

A submitter opens an issue using the **Add package** template (`.github/ISSUE_TEMPLATE/add-package.yml`), supplying:

- a GitHub URL to the source release folder, in the exact form
  `https://github.com/<owner>/<repo>/tree/<branch>/packages/<name>/<version>`
- a target architecture (`any` / `linux_x86_64` / `macos_arm64` / `windows_x86_64`)

One package release + one architecture per issue.

On open, `add-package.yml` runs `scripts/add_package_from_issue.py validate`, posts a comment summarising what was parsed (and whether the destination already exists), and rewrites the title to `Add package: \`packages/<name>/<version>\` (<arch>)`.

To approve, any user with write access on the repo replies with `approve` on its own line. The workflow then:

1. Clones the source repo at the specified branch and copies the folder into `packages/`.
2. Commits and pushes to `main` using `secrets.MIP_SYNC_TOKEN`.
3. Dispatches `build-package.yml` with the parsed `(package_path, architecture)`.
4. Reports the result back as a comment, including a link to the dispatched build.

**Secrets required:** `MIP_SYNC_TOKEN` (PAT with `contents:write` + `workflow` scopes on this repo).

## Manual reindex

If a release is restored, deleted, or hand-edited without a package build, you can refresh the index in isolation:

```
gh workflow run assemble-index.yml
```

## Seed packages

- `packages/with_test/1.0.0/` — pure MATLAB, `architectures: [any]`, exercises the no-compile path.
- `packages/mex_dot/1.0.0/` — MEX dot-product, `architectures: [linux_x86_64, macos_arm64, windows_x86_64]`, exercises `compile_script` on each native arch.

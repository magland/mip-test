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
  build-request.yml            # Issue-driven build trigger + admin approval
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

## Submitting a build via issue

Issues are used to **request builds** of packages already in this channel — not to add new packages. The workflow does not clone, copy, commit, or push anything; on admin approval it dispatches one `build-package.yml` run per `(package, architecture)` pair listed in the issue.

### Step 1 — Open an issue

- **Title** must start with `Build` (case-insensitive).
- **Body** lists one or more build lines, free-form. Each non-empty line that contains a package path is parsed; lines without a path are ignored as free-form context.

Each build line should look like:

```
packages/<name>/<version> <architecture>
```

### Architecture keywords

| Keyword | Runner |
| --- | --- |
| `any` | ubuntu-latest (arch-independent / pure MATLAB) |
| `linux_x86_64` | ubuntu-latest |
| `macos_arm64` | macos-latest (Apple Silicon) |
| `windows_x86_64` | windows-latest |
| `all` | expands to every supported architecture declared in the package's `mip.yaml` |

Multiple keywords on one line dispatch multiple builds for that package.

### Skip-if-unchanged (default) and `force`

By default, `prepare_one.py` hashes the package source + channel-side overlay files and compares against the `source_hash` in the `.mip.json` of the latest published `.mhl`. If they match, the build silently no-ops (the `Check for prepared package` step short-circuits the rest of the pipeline). So submitting the same issue twice does not re-publish anything.

Append `force` to a build line to rebuild that pair anyway:

```
packages/fmm2d/main macos_arm64 force
```

`force` applies only to dispatches from the same line. Use it once per line you want forced.

### Examples

**One package, one arch:**

```
packages/with_test/1.0.0 any
```

**One package, all architectures it supports:**

```
packages/fmm2d/main all
```

**Multiple packages in a single issue:**

```
packages/chebfun/5.7.0 any
packages/fmm2d/main all
packages/mex_dot/1.0.0 linux_x86_64 macos_arm64
```

**Force rebuild of a single pair:**

```
packages/fmm2d/main macos_arm64 force
```

**Inside a sentence works too:**

```
Please build packages/with_test/1.0.0 on any.
```

### Step 2 — Workflow validates

On open, `build-request.yml` parses the issue and replies with the list of `(package, architecture)` pairs it detected. If parsing fails (no path, no arch, path doesn't exist in the channel, etc.) the comment lists the errors and nothing is dispatched.

For single-build requests, the issue title is rewritten to a canonical form. Multi-build requests keep their original title.

### Step 3 — Admin approval

A user with write access on the repo (`author_association` in `OWNER`/`MEMBER`/`COLLABORATOR`) approves by replying with `approve` on its own line. The workflow then dispatches `build-package.yml` once per pair and posts a final comment with the dispatched list.

**Secrets required:** none beyond the default `GITHUB_TOKEN`.

## Manual reindex

If a release is restored, deleted, or hand-edited without a package build, you can refresh the index in isolation:

```
gh workflow run assemble-index.yml
```

## Seed packages

- `packages/with_test/1.0.0/` — pure MATLAB, `architectures: [any]`, exercises the no-compile path.
- `packages/mex_dot/1.0.0/` — MEX dot-product, `architectures: [linux_x86_64, macos_arm64, windows_x86_64]`, exercises `compile_script` on each native arch.

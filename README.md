# mip-test

A MIP package channel hosted at https://github.com/magland/mip-test. Builds are launched **one package, one architecture at a time**, via GitHub issues — no PR, no commit, no local setup.

> **You want to trigger a build of a package that already exists in this channel?** Read the next section. That's the whole flow.

---

## Launching a build by opening an issue

### TL;DR

Open a new issue here: https://github.com/magland/mip-test/issues/new

**Title:** must start with the word `Build` (case-insensitive).
**Body:** one or more build lines. Each line names a package and one or more architectures.

Example body that builds `with_test` on the `any` (arch-independent) runner:

```
packages/with_test/1.0.0 any
```

That's the whole syntax. Submit the issue, wait for the bot to validate it (one comment, ~30s), then an admin replies `approve` and the builds dispatch.

### Quick recipes

| Goal | Body |
|---|---|
| Build one package on one arch | `packages/with_test/1.0.0 any` |
| Build one package on every arch it supports | `packages/fmm2d/main all` |
| Build one package on two specific arches | `packages/mex_dot/1.0.0 linux_x86_64 macos_arm64` |
| Build several packages in one issue | one build line per package (newline-separated) |
| Build **every** package in the channel | `all-packages <arch-or-all>` |
| Force-rebuild even when nothing changed | append `force` to the line |

A combined body:

```
packages/chebfun/5.7.0 any
packages/fmm2d/main all force
packages/mex_dot/1.0.0 linux_x86_64
```

### Architecture keywords

| Keyword | Meaning | Runner |
|---|---|---|
| `any` | Arch-independent / pure MATLAB | ubuntu-latest |
| `linux_x86_64` | Linux x86_64 native | ubuntu-latest |
| `macos_arm64` | macOS Apple Silicon native | macos-latest |
| `windows_x86_64` | Windows x86_64 native | windows-latest |
| `all` | Expand to every arch this package's `mip.yaml` declares (intersected with the four above) |
| `force` | Modifier: rebuild this line even if nothing has changed |

A line can list multiple arch keywords — each becomes one dispatch. `force` applies only to the line it's on.

If you ask to build a package on an arch its `mip.yaml` doesn't declare, the build job dispatches but exits cleanly with nothing to do.

### The `all-packages` shortcut

```
all-packages linux_x86_64    # every package, on linux only
all-packages all             # every package, every arch it declares
all-packages all force       # same, but rebuild even if unchanged
```

**The literal `all-packages` must be the first token of its line** (after any leading whitespace). This avoids prose like *"the all-packages keyword is great"* being misread as a directive.

### Skip-if-unchanged

By default, a build that would produce a `.mhl` matching what's already published (same source hash, same metadata) **skips silently**. The dispatch still runs, the prepare step notices, and the rest of the pipeline short-circuits — total runtime ~30s, no MATLAB spin-up.

This means re-submitting the same issue is harmless. Use `force` only when you really do need to rebuild (e.g. to pick up a workflow change that affects bundling).

### What the bot does

1. **Validation comment** (within ~30s of opening): lists every `(package, architecture)` pair the parser found, or the errors it hit (unknown path, missing architecture, etc.). If errors, fix the issue body and reopen — re-editing does not re-trigger validation; you need a fresh issue.
2. **Title rewrite** (single-build requests only): the title becomes `Build: \`packages/<name>/<version>\` (<arch>)`.
3. **Dispatch** (after approval — see below): one `build-package.yml` run per pair. Final comment lists the dispatched runs and links to the Actions tab.

### Approval

For safety (builds consume runner minutes), a build only dispatches after an admin approves. **Admin** = anyone with write access to this repo. To approve, reply to the issue with **`approve`** on its own line. Nothing else triggers the dispatch — not a 👍, not a comment containing the word "approve" buried in prose.

### Examples that don't work, and why

| Body | Result |
|---|---|
| `Please build packages/foo/1.0` | error — no architecture keyword |
| `packages/foo/1.0 packages/bar/2.0 any` | error — multiple paths on one line; put one per line |
| `all-packages` (no arch) | error — `all-packages` needs an architecture |
| `  the all-packages keyword` | ignored — `all-packages` isn't first on the line |
| `Please build packages/with_test/1.0.0 on any.` | works — natural-language wrapping is fine as long as the line has one path + one arch |

### Common questions

**Can I submit a build for a package that isn't in this channel yet?**
No. Issues only trigger builds of `packages/<name>/<version>/` directories that already exist on the `main` branch. To add a new package, open a PR.

**Where do the build outputs end up?**
Each successful build uploads `<name>-<version>-<arch>.mhl` and `.mip.json` to the GitHub Release tagged `<name>-<version>`. The channel index at https://magland.github.io/mip-test/index.json is regenerated on every successful build.

**Does my build need a personal access token?**
No. The repo's default `GITHUB_TOKEN` is enough.

---

## Other ways to trigger a build

For the same effect without an issue:

```bash
gh workflow run build-package.yml \
  -f package_path=packages/with_test/1.0.0 \
  -f architecture=any \
  -f force=false
```

Or call from another workflow:

```yaml
jobs:
  build:
    uses: ./.github/workflows/build-package.yml
    with:
      package_path: packages/mex_dot/1.0.0
      architecture: linux_x86_64
```

To regenerate the channel index without rebuilding anything (e.g. after manually editing a release):

```bash
gh workflow run assemble-index.yml
```

---

## Channel internals (for maintainers)

### Layout

```
packages/<name>/<release>/
  recipe.yaml            # required: source spec (git/zip, or inline)
  mip.yaml               # optional: overrides upstream mip.yaml
  compile.m              # optional: per-arch compile
  *.m                    # optional: test scripts, etc.

mexopts/<arch>/          # static-linking MEX compiler XMLs (gcc/g++_static.xml)

scripts/
  channel_config.py             # owner/repo + URL helpers
  prepare_one.py                # prepare ONE (package, release, arch); also enforces skip-if-unchanged
  bundle_one.m                  # mip.bundle on the prepared dir
  test_one.m                    # mip install/load/test on a single .mhl
  upload_one.py                 # upload .mhl + .mip.json to the release
  assemble_index.py             # walk releases, rebuild index.json
  package_setup.py              # run the build entry's per-OS `setup:` block
  setup_mex_compilers.m         # point MEX at mexopts/<arch>/*.xml
  build_request_from_issue.py   # parse + validate issue bodies
  bundle_runtime_libs.m         # bundle MEX dylib deps next to the .mex
  copy_and_sanitize_lib.m       # SONAME / install_name rewriting helper
  system_echo.m, dynamic_lib_ext.m

site/
  index.html             # static page that reads index.json

.github/workflows/
  build-package.yml      # the per-(package, arch) pipeline (4 jobs)
  assemble-index.yml     # manual reindex without rebuilding
  build-request.yml      # issue-driven trigger + admin-approval gate
```

### Pipeline (`build-package.yml`)

Inputs: `package_path`, `architecture`, `force` (optional bool).

Four jobs:

1. **setup** — maps the architecture keyword to a runner OS.
2. **build** — runs `prepare_one.py` (which may short-circuit on skip-if-unchanged), runs the package's `setup:` block via `scripts/package_setup.py`, then `bundle_one`. Output is one `.mhl` + `.mip.json` uploaded as a workflow artifact.
3. **test-and-upload** — strips the build toolchain off the runner, verifies it's gone (Linux), then `mip install` / `mip load` / `mip test` on the `.mhl`. On success, uploads to the GitHub Release tagged `{name}-{version}`. macOS arm64 tolerates a known exit-time SIGSEGV via a marker file.
4. **assemble-and-deploy** — `assemble_index.py` rebuilds `index.json` from all releases, deploys with `site/` to GitHub Pages. Serialized by the `pages` concurrency group; the github-pages environment may also cancel deploys when multiple runs queue, but each run's preceding upload to the Release still succeeds.

### Per-package `setup:` block

Each `builds:` entry in a package's `mip.yaml` may declare per-OS shell commands run after `prepare_one.py` and before MATLAB starts, e.g.:

```yaml
builds:
  - architectures: [linux_x86_64, macos_arm64]
    compile_script: compile.m
    setup:
      linux:
        - "sudo apt update"
        - "sudo apt install -y libfftw3-dev"
      macos:
        - "brew install fftw"
```

Values are lists of strings (one shell command per item) — block scalars (`|`, `>`) are intentionally not used because mip's MATLAB-side YAML parser doesn't support them.

### Dependency resolution gotcha

Bare-name deps in `mip.yaml` always resolve to `mip-org/core`. To depend on a package in this channel, use the FQN form `magland/test/<name>` (note the channel name is the github repo name with the `mip-` prefix stripped). See `chunkie/master/mip.yaml` for an example.

### Seed packages

- `packages/with_test/1.0.0/` — pure MATLAB, exercises the no-compile path.
- `packages/mex_dot/1.0.0/` — MEX dot-product on linux/macos/windows native arches.

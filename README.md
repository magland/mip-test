# MIP channel

A MIP package channel. Builds run one (package, architecture) at a time and are triggered by GitHub issues.

## Submitting a build

Open an issue. The title must start with `Build` (case-insensitive). The body lists one or more build lines:

```
packages/<name>/<version> <architecture>
```

Multiple architectures on one line dispatch multiple builds for that package. Multiple lines dispatch multiple packages. Lines without a package path are ignored.

Example body:

```
packages/foo/1.0.0 any
packages/bar/2.0 linux_x86_64 macos_arm64
```

Within ~30s the request bot replies with the list of `(package, architecture)` pairs it parsed (or an error list). An admin — anyone with write access on the repo — then replies `approve` on its own line to dispatch.

### Architecture keywords

- `any` — pure MATLAB; runs on ubuntu.
- `linux_x86_64`, `macos_arm64`, `windows_x86_64` — native; run on the matching OS.
- `all` — expand to every arch declared in the package's `mip.yaml` (intersected with the four above).

A build for an architecture the package does not declare exits cleanly with nothing to do.

### Building every package in one go

Replace the path with the literal keyword `all-packages` to fan out across the channel:

```
all-packages linux_x86_64
all-packages all
```

`all-packages` must be the first token of the line (after any leading whitespace).

### Skip-if-unchanged and `force`

By default, a build that would produce a `.mhl` matching what is already published (same source hash, same metadata) short-circuits. Re-submitting the same issue is therefore a no-op.

To rebuild anyway, append `force` to a build line:

```
packages/foo/1.0.0 linux_x86_64 force
```

`force` applies only to the line it is on.

### Approval

Builds dispatch only when an admin replies with `approve` on its own line. Emoji reactions and `approve` embedded in prose do not count.

### Editing an issue

Editing a submitted issue does not re-validate. To change anything, open a new issue.

## Direct dispatch

The same effect from the command line:

```bash
gh workflow run build-package.yml \
  -f package_path=packages/<name>/<version> \
  -f architecture=<arch> \
  -f force=false
```

Regenerate the channel index without rebuilding:

```bash
gh workflow run assemble-index.yml
```

## Layout

```
packages/<name>/<release>/
  recipe.yaml            # required: source spec (git/zip)
  mip.yaml               # optional: overrides upstream mip.yaml
  compile.m              # optional: per-arch compile
  *.m                    # optional: test scripts, etc.

mexopts/<arch>/          # static-linking MEX compiler XMLs

scripts/                 # workflow helpers
site/                    # static page reading index.json

.github/workflows/
  build-package.yml      # per-(package, arch) pipeline (4 jobs)
  assemble-index.yml     # manual reindex
  build-request.yml      # issue trigger + admin approval
```

## Pipeline (`build-package.yml`)

Inputs: `package_path`, `architecture`, `force` (optional bool). Four jobs:

1. **setup** — map architecture to runner OS.
2. **build** — `prepare_one.py` (which may short-circuit on skip-if-unchanged), the package's per-OS `setup:` block (via `scripts/package_setup.py`), then `bundle_one`. Output: one `.mhl` + `.mip.json` artifact.
3. **test-and-upload** — strip the build toolchain off the runner, verify it is gone (Linux), `mip install` / `load` / `test` on the `.mhl`, then upload to the GitHub Release tagged `{name}-{version}`.
4. **assemble-and-deploy** — rebuild `index.json` from all releases and deploy to GitHub Pages.

## Package `setup:` block

Each `builds:` entry in `mip.yaml` may declare per-OS shell commands run after `prepare_one.py` and before MATLAB starts:

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

Values are lists of strings, one command per item. Block scalars (`|`, `>`) are not used because mip's MATLAB-side YAML parser does not support them.

## Dependencies

Bare-name dependencies in `mip.yaml` always resolve to `mip-org/core`. To depend on a package in this channel, use the FQN form `<owner>/<channel>/<name>`, where `<channel>` is the github repo name with the `mip-` prefix stripped.

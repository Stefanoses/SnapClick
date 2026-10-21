# AGENTS.md — guide for AI agents working on SnapClick

Read this first. It describes what the project is, how work flows through it,
and the rules for git / releases. Follow them unless the user explicitly says
otherwise.

## What this project is

**SnapClick** — a portable, vision-based desktop automation tool (visual block
editor → screenshot/template matching → synthetic mouse/keyboard input).
It is deliberately *not* described as a game bot; it targets games, desktop
apps and browsers. UI is PySide6; the app is bilingual (PL/EN via
`snapclick/i18n`). Code comments are in Polish — keep that convention.

- Package: `snapclick/` (core engine, GUI, platform backends, i18n)
- Entry point: `main.py`
- Tests: `tests/` (pytest, headless-safe; run `python -m pytest tests -q`)
- Data is portable: settings/projects/logs live in `snapclick-data/` next to
  the executable / `.AppImage` (see `snapclick/core/paths.py`; honors the
  `APPIMAGE` env var). Never move user data into `~/.config` or the repo.
- Project files: `*.snapclick` (legacy `*.m2proj` auto-migrates on load).

## Day-to-day flow

1. Make changes, keep tests green: `python -m pytest tests -q` (must be 100%
   passing on both Windows and Linux semantics — platform-specific tests use
   `skipif`).
2. **Commit meaningful, finished units of work to `main` and push** as you go
   (remote: `git@github.com:Stefanoses/SnapClick.git`, SSH key already set up
   on this machine). Use clear, imperative commit messages.
3. Do NOT create tags or releases on your own initiative.

## Releases — only when the user says so

A release happens **only when the user explicitly declares the current state
a new version they are happy with** (e.g. "release 1.1.0", "this is good,
make a release"). Then run:

```bash
python scripts/release.py 1.1.0
```

That script is the single release path: it bumps `snapclick/version.py`
(single source of truth for the version), runs the tests, commits
`Release vX.Y.Z`, tags `vX.Y.Z`, pushes branch + tag. The GitHub Actions
workflow `.github/workflows/release.yml` then builds and attaches:

- `SnapClick-X.Y.Z-windows.zip` (PyInstaller one-file exe, zipped)
- `SnapClick-X.Y.Z-x86_64.AppImage` (built by `scripts/build_appimage.sh`)
- `SnapClick-X.Y.Z-linux.tar.gz` (portable folder archive)

and publishes a GitHub Release (`softprops/action-gh-release`, with
`overwrite_files`/`prune_files` so re-running a tag stays clean).

After pushing a tag, watch the run until it is green:

```bash
# poll via API (no gh CLI installed on this machine)
curl -s https://api.github.com/repos/Stefanoses/SnapClick/actions/runs?per_page=3
```

and verify the assets with `.../releases/latest`. If a re-release of the same
tag is needed: delete the tag locally + remotely, re-create, push
(`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z && git tag -a ...`).
Alternatively the Release workflow supports manual `workflow_dispatch` from
the Actions tab.

Do NOT ship self-extracting `.sh` installers — they were removed on purpose
(base64 bloat, "installer-ish" look). Linux formats are AppImage + tar.gz.

## CI facts / gotchas (learned the hard way)

- `.github/workflows/ci.yml` runs the suite on windows-latest + ubuntu-latest.
- Linux runners need Qt system libs (`libegl1 libgl1 libxkbcommon-x11-0
  libdbus-1-3 libxcb-*`) and `QT_QPA_PLATFORM=offscreen` — already wired in
  the workflows; keep it that way.
- YAML gotcha: never put `": "` inside an unquoted `- name:` string (breaks
  the whole workflow with a parse error). Quote such names.
- `ctypes.wintypes` raises `ValueError` (not ImportError) on Linux — any test
  importing `snapclick.core.platform.win32` must be
  `@pytest.mark.skipif(sys.platform != "win32")`.
- Wayland is unsupported by design (X11 only); the app detects and reports it.
- If a file keeps reverting edits, an unsaved VS Code editor buffer may be
  overwriting it — check open tabs before rewriting files.

## Style

- Keep user-visible text in both PL and EN catalogs (`snapclick/i18n/catalogs.py`).
- README is English, casual tone, no personal data (no names/emails/paths).
- Never commit personal projects, logs, or anything under `snapclick-data/`,
  `dist/`, `build/`, `.venv/` (see `.gitignore`).

# RapidOCR CLI — Standalone Packaging Design

## Overview

RapidOCR is a lightweight OCR deployment runtime that uses PaddleOCR-derived models. This document describes the design for packaging RapidOCR as a standalone CLI binary that requires no Python installation, with an optional HTTP server mode for network-based OCR.

---

## Problem

The CLI currently only supports single-shot local file OCR. Users need:

1. A way to call OCR over the network (browser, curl, other programs) without installing Python.
2. A zero-dependency binary they can download and run immediately.
3. Cross-platform support (Linux, macOS, Windows).

---

## Constraints

- Fork repo — **upstream `python/rapidocr/` must not be modified**.
- All new code lives under `packaging/pyinstaller/`.
- CI workflow lives at `.github/workflows/build-cli.yml`.
- Final artifact is a PyInstaller single-directory binary.

---

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Sync from upstream RapidOCR. No local changes beyond what upstream provides. |
| `dev` | Active development branch. All local modifications and new features go here. |
| `release` | CI/CD branch. Pushes and tags on this branch trigger the build and release pipeline. |

**Workflow:**

1. `main` is kept in sync with the upstream repo via periodic pulls/merges.
2. `dev` is branched from `main` and contains all packaging and feature work.
3. When ready to release, `dev` is merged into `release`, triggering the CI/CD pipeline.

---

## Relationship to PaddleOCR

RapidOCR is **based on PaddleOCR models** but is **not the PaddleOCR CLI or package**. The models from PaddleOCR are converted to ONNX format for lightweight, cross-platform inference via ONNX Runtime. Users can also fine-tune models using PaddleOCR and deploy them through RapidOCR.

---

## Design Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Foreground server, no daemon | Simple, cross-platform; users have nohup/systemd/launchd |
| 2 | FastAPI + uvicorn | Auto JSON validation, auto `/docs`, +8 MB acceptable |
| 3 | JSON-only API (base64 image) | Uniform with CLI params, no multipart complexity |
| 4 | `sys.argv` intercept in `cli_entry.py` | Avoids touching upstream `parse_args()` |
| 5 | Platform info in archive/folder name only | Executable stays stable across platforms; suits package managers |
| 6 | Models not bundled in binary | Keeps download size small; models cached on first run |

---

## Naming

### Executable Name

The canonical executable name is **`rapidocr`**.

### Archive vs Executable Naming

Platform and architecture belong in the **archive and folder name**, not in the executable name. This keeps the command stable for package managers (e.g. Homebrew) and user muscle memory. Users should never have to type OS or arch to run the binary.

| Layer | Name Pattern | Example |
|---|---|---|
| Release archive | `rapidocr-<os>-<arch>.tar.gz` (`.zip` on Windows) | `rapidocr-macos-arm64.tar.gz` |
| Extracted folder | `rapidocr-<os>-<arch>/` | `rapidocr-macos-arm64/` |
| Executable | `rapidocr(.exe)` | `rapidocr` |

---

## CLI Interface

> **Note:** The existing CLI interface (default single-shot OCR, `config`, `download_models`, `check` subcommands and their options) remains unchanged from upstream. Only `serve` is new.

### Serve Options

| Flag | Description | Default |
|---|---|---|
| `--host` | Listen address | `127.0.0.1` |
| `--port` | Listen port | `9003` |
| `--open` | Open browser on start | off |

Background usage: `nohup rapidocr serve --host 0.0.0.0 &`

---

## Model Management

Models are **not bundled** in the binary. They are downloaded automatically on first run.

| Item | Value |
|---|---|
| Default cache directory | `~/.cache/rapidocr/models/` |
| Override | `RAPIDOCR_MODEL_DIR` environment variable |
| Trigger | First OCR invocation or explicit `rapidocr download_models` |

The entry point (`cli_entry.py`) creates the cache directory and injects `model_root_dir` into the RapidOCR engine params before any upstream code runs. This avoids modifying upstream `parse_args()`.

---

## HTTP API (serve subcommand)

| Method | Path | Description |
|---|---|---|
| POST | `/api/ocr` | OCR endpoint (JSON in, JSON out) |
| GET | `/health` | Health check → `{"status": "ok"}` |
| GET | `/` | Web UI (drag-and-drop) |
| GET | `/docs` | Interactive API docs (Swagger) |

### POST /api/ocr

> **Note:** Request fields and validation should mimic what the existing upstream RapidOCR engine already accepts.

> **Note:** Response fields should utilize what the app already returns from the RapidOCR engine.

---

## File Inventory

All new and modified files in this fork, grouped by location.

### `packaging/pyinstaller/`

| File | Purpose |
|---|---|
| `cli_entry.py` | PyInstaller entry point; sets up model cache dir, injects `model_root_dir`, delegates to upstream `parse_args()` and `RapidOCR` engine; handles subcommand dispatch for `config`, `download_models`, `check`, and default OCR with optional visualization |
| `build_cli.py` | Build script; detects OS/arch, collects YAML data files from `python/rapidocr/`, invokes PyInstaller with hidden imports |
| `pyproject.toml` | Locks Python 3.12, declares all runtime dependencies |

### `packaging/`

| File | Purpose |
|---|---|
| `README.md` | User-facing quick-start for building and running the CLI |

### `.github/workflows/`

| File | Purpose |
|---|---|
| `build-cli.yml` | CI workflow: builds on all supported platforms |

### `serve/` (planned, under `packaging/pyinstaller/`)

| File | Purpose |
|---|---|
| `serve/__init__.py` | Package init for the serve subcommand |
| `serve/app.py` | FastAPI application implementing `/api/ocr`, `/health`, `/`, `/docs` |
| `serve/index.html` | Inline single-file Web UI for drag-and-drop OCR, build with babel, react, ant design |

---

## Cross-Platform Packaging

### Target Matrix

| Platform | Arch | Artifact Name | CI Runner |
|---|---|---|---|
| Linux | x86_64 | `rapidocr-linux-x86_64` | `ubuntu-latest` |
| Linux | arm64 | `rapidocr-linux-arm64` | `ubuntu-24.04-arm` |
| macOS | arm64 | `rapidocr-macos-arm64` | `macos-14` |
| Windows | x86_64 | `rapidocr-windows-x86_64` | `windows-latest` |

### Key Choices

| Choice | Why |
|---|---|
| `--onedir` (not `--onefile`) | Faster startup, easier to debug missing libs |
| Models not bundled | Downloaded on first run to `~/.cache/rapidocr/models/` (~50 MB) |
| Python 3.12 locked | Same ABI across all platforms |
| `uv` as package manager | Fast, reproducible builds |

### Build

Run from `packaging/pyinstaller/` using `uv run python build_cli.py`. The build script automatically detects OS and architecture, collects all `.yaml` config files from the upstream `python/rapidocr/` package as data files, and invokes PyInstaller with the correct hidden imports and collection flags.

### CI/CD Pipeline

Trigger: manual `workflow_dispatch` or push tag matching `v*`.

**Build job** (runs in parallel on all platforms):

1. Upload `dist/<artifact>/` as a GitHub Actions artifact.

**Release job** (runs only on tag push, after all builds succeed):

1. Download all artifacts.
2. Create `tar.gz` for Linux and macOS artifacts, `zip` for Windows.
3. Publish a GitHub Release with auto-generated release notes.

---

## Distribution

### Directory Layout

```
rapidocr-<os>-<arch>/
  rapidocr(.exe)        ← canonical entry point
  _internal/            ← bundled Python runtime and dependencies
```

### Download and Run

Download the platform-appropriate archive → extract → run. No Python installation needed.

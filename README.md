# RapidOCR CLI (Standalone)

RapidOCR CLI (Standalone) packages RapidOCR as a zero-Python-install command line tool with an optional HTTP server and browser UI. Download the archive for your platform, extract it, and run `rapidocr` immediately.

RapidOCR uses PaddleOCR-derived OCR models converted to ONNX format for lightweight cross-platform inference. The PaddleOCR model lineage gives strong OCR accuracy, while the standalone package keeps deployment simple and does not require installing PaddlePaddle or Python on target machines.

## Highlights

- **Easy to deploy**: extract one archive and run `rapidocr`; no system Python required.
- **Cross-platform**: builds target Linux, macOS, and Windows.
- **PaddleOCR model compatibility**: uses PaddleOCR-derived ONNX models and can deploy models fine-tuned through PaddleOCR after conversion/configuration.
- **Small artifacts**: OCR models are not bundled; they download on first OCR use or via `rapidocr download_models`.
- **CLI and server modes**: use local file OCR from the terminal or start an HTTP API with a bundled web UI.

## Supported Artifacts

| Platform | Architecture | Archive / Folder Name | Executable |
|---|---:|---|---|
| Linux | x86_64 | `rapidocr-linux-x86_64` | `rapidocr` |
| Linux | arm64 | `rapidocr-linux-arm64` | `rapidocr` |
| macOS | arm64 | `rapidocr-macos-arm64` | `rapidocr` |
| Windows | x86_64 | `rapidocr-windows-x86_64` | `rapidocr.exe` |

The archive or extracted folder includes the platform and architecture. The executable name does not, so scripts and package managers can always call the same command.

Expected layout:

```text
rapidocr-<os>-<arch>/
  rapidocr(.exe)
  _internal/
```

## Quick Start

### 1. Download and extract

Download the archive for your platform from the release page and extract it.

Linux / macOS:

```bash
tar -xzf rapidocr-<os>-<arch>.tar.gz
cd rapidocr-<os>-<arch>
./rapidocr --help
```

Windows PowerShell:

```powershell
Expand-Archive rapidocr-windows-x86_64.zip
cd rapidocr-windows-x86_64
.\rapidocr.exe --help
```

### 2. Run OCR from the CLI

Use the same RapidOCR CLI interface as upstream:

```bash
./rapidocr -img path/to/image.png
```

Common commands:

```bash
./rapidocr --help
./rapidocr config
./rapidocr download_models
./rapidocr check
```

On Windows, replace `./rapidocr` with `.\rapidocr.exe`.

### 3. Start the HTTP server

```bash
./rapidocr serve --host 127.0.0.1 --port 9003 --open
```

Then open:

- Web UI: `http://127.0.0.1:9003/`
- Health check: `http://127.0.0.1:9003/health`
- Swagger docs: `http://127.0.0.1:9003/docs`

For LAN or container deployment:

```bash
./rapidocr serve --host 0.0.0.0 --port 9003
```

Background process example:

```bash
nohup ./rapidocr serve --host 0.0.0.0 --port 9003 > rapidocr.log 2>&1 &
```

## HTTP API

### Health check

```bash
curl http://127.0.0.1:9003/health
```

Expected response:

```json
{"status":"ok"}
```

### OCR request

`POST /api/ocr` accepts JSON only. The `image` field is required and must contain base64-encoded image bytes. Data URLs are also accepted.

```bash
IMAGE_B64=$(base64 -i path/to/image.png | tr -d '\n')

curl -X POST http://127.0.0.1:9003/api/ocr \
  -H "Content-Type: application/json" \
  -d "{\"image\":\"${IMAGE_B64}\"}"
```

Optional OCR parameters include:

- `use_det`
- `use_cls`
- `use_rec`
- `return_word_box`
- `return_single_char_box`
- `text_score`
- `box_thresh`
- `unclip_ratio`

Typical response:

```json
{
  "results": [],
  "elapse": 0.0
}
```

When word-level results are requested and available, the response may also include `word_results`.

## Web UI

The server bundles a self-contained browser UI at `/`.

It supports:

- Drag-and-drop image upload
- File picker upload
- Clipboard image paste
- Automatic OCR after image selection
- Plain text output for quick copying
- Raw JSON output for integration testing

No separate frontend build or static file server is required.

## Model Management

Models are not bundled in the standalone artifact. This keeps downloads small and makes deployment predictable.

Default model cache:

```text
~/.cache/rapidocr/models/
```

Override with `RAPIDOCR_MODEL_DIR`:

```bash
export RAPIDOCR_MODEL_DIR=/opt/rapidocr/models
./rapidocr download_models
./rapidocr serve --host 0.0.0.0 --port 9003
```

Behavior:

- First OCR call automatically downloads missing models.
- `rapidocr download_models` downloads models explicitly.
- CLI mode and server mode use the same cache location.
- PyInstaller artifacts are validated so OCR model files are not accidentally bundled.

## PaddleOCR Model Notes

RapidOCR is based on PaddleOCR model architecture and model assets, but the standalone CLI is not the PaddleOCR Python package. The packaged runtime uses ONNX Runtime for CPU-friendly, cross-platform inference.

This means:

- Target machines do not need PaddlePaddle installed.
- Target machines do not need Python installed.
- Models can stay outside the binary and be managed through the RapidOCR model cache.
- PaddleOCR-trained or fine-tuned models can be deployed through RapidOCR when converted/configured for the supported RapidOCR runtime.

## Build from Source

Builds are created with PyInstaller from `packaging/pyinstaller/`.

Prerequisites:

- Python `3.12`
- `uv`

Build command:

```bash
cd packaging/pyinstaller
uv run python build_cli.py
```

Output:

```text
packaging/pyinstaller/dist/rapidocr-<os>-<arch>/
  rapidocr(.exe)
  _internal/
```

The build script automatically:

- Detects OS and architecture.
- Uses PyInstaller `--onedir` for faster startup and easier debugging.
- Includes RapidOCR YAML config files.
- Includes the bundled server Web UI.
- Collects ONNX Runtime binaries.
- Excludes heavyweight optional backends such as Paddle, TensorRT, Torch, OpenVINO, and MNN.
- Fails if OCR model files are found inside the artifact.

## Smoke Test

After building or extracting an artifact:

```bash
./rapidocr --help
./rapidocr config
./rapidocr download_models
./rapidocr check
./rapidocr serve --host 127.0.0.1 --port 9003
```

In another terminal:

```bash
curl http://127.0.0.1:9003/health
```

Expected:

```json
{"status":"ok"}
```

Also verify the web UI at `http://127.0.0.1:9003/` and API docs at `http://127.0.0.1:9003/docs`.

## Deployment Tips

- **Desktop use**: run `rapidocr serve --open` and use the browser UI.
- **Local automation**: call `rapidocr path/to/image.png` directly from scripts.
- **Server use**: run `rapidocr serve --host 0.0.0.0 --port 9003` behind your process manager or reverse proxy.
- **Containers**: mount `RAPIDOCR_MODEL_DIR` as a persistent volume to avoid downloading models on every container start.
- **Offline environments**: run `rapidocr download_models` once in a connected environment, then copy the model cache to the target machine and set `RAPIDOCR_MODEL_DIR`.
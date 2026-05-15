from __future__ import annotations

import hashlib
import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


EXECUTABLE_NAME = "rapidocr"
CONTENTS_DIR_NAME = "_internal"

PACKAGING_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGING_DIR.parents[1]
PYTHON_DIR = REPO_ROOT / "python"
RAPIDOCR_PACKAGE_DIR = PYTHON_DIR / "rapidocr"
ENTRY_SCRIPT = PACKAGING_DIR / "cli_entry.py"
SERVE_INDEX_HTML = PACKAGING_DIR / "serve" / "index.html"
DIST_DIR = PACKAGING_DIR / "dist"
BUILD_DIR = PACKAGING_DIR / "build"
PYINSTALLER_BUILD_DIR = BUILD_DIR / "pyinstaller"
MODEL_CACHE_DIR = BUILD_DIR / "model_cache"
BUNDLED_MODEL_DESTINATION = Path("rapidocr") / "models"
SUPPORTED_BUNDLED_ENGINE = "onnxruntime"
DEFAULT_MODEL_SECTIONS = (
    ("Det", "use_det"),
    ("Cls", "use_cls"),
    ("Rec", "use_rec"),
)

HIDDEN_IMPORTS = [
    "serve",
    "serve.app",
    "rapidocr",
    "rapidocr.cli",
    "rapidocr.main",
    "rapidocr.cal_rec_boxes",
    "rapidocr.cal_rec_boxes.main",
    "rapidocr.ch_ppocr_cls",
    "rapidocr.ch_ppocr_cls.main",
    "rapidocr.ch_ppocr_cls.utils",
    "rapidocr.ch_ppocr_det",
    "rapidocr.ch_ppocr_det.main",
    "rapidocr.ch_ppocr_det.utils",
    "rapidocr.ch_ppocr_rec",
    "rapidocr.ch_ppocr_rec.main",
    "rapidocr.ch_ppocr_rec.typings",
    "rapidocr.ch_ppocr_rec.utils",
    "rapidocr.inference_engine",
    "rapidocr.inference_engine.base",
    "rapidocr.inference_engine.onnxruntime",
    "rapidocr.inference_engine.onnxruntime.main",
    "rapidocr.inference_engine.onnxruntime.provider_config",
    "rapidocr.utils.download_file",
    "rapidocr.utils.download_models",
    "rapidocr.utils.load_image",
    "rapidocr.utils.log",
    "rapidocr.utils.output",
    "rapidocr.utils.parse_parameters",
    "rapidocr.utils.process_img",
    "rapidocr.utils.to_json",
    "rapidocr.utils.to_markdown",
    "rapidocr.utils.typings",
    "rapidocr.utils.utils",
    "rapidocr.utils.vis_res",
    "fastapi",
    "fastapi.exceptions",
    "fastapi.responses",
    "fastapi.routing",
    "pydantic",
    "pydantic_core",
    "pydantic_core._pydantic_core",
    "starlette",
    "uvicorn",
    "uvicorn.config",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "onnxruntime",
    "onnxruntime.capi",
    "onnxruntime.capi.onnxruntime_pybind11_state",
    "cv2",
    "numpy",
    "omegaconf",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageOps",
    "pyclipper",
    "requests",
    "shapely",
    "yaml",
]

COLLECT_BINARIES = [
    "onnxruntime",
]

EXCLUDED_MODULES = [
    "MNN",
    "openvino",
    "paddle",
    "tensorrt",
    "torch",
    "torchvision",
    "rapidocr.inference_engine.mnn",
    "rapidocr.inference_engine.openvino",
    "rapidocr.inference_engine.paddle",
    "rapidocr.inference_engine.pytorch",
    "rapidocr.inference_engine.tensorrt",
]


@dataclass(frozen=True)
class DataFile:
    source: Path
    destination: Path

    @property
    def pyinstaller_arg(self) -> str:
        return f"{self.source}{os.pathsep}{self.destination.as_posix()}"

    @property
    def runtime_relative_path(self) -> Path:
        return self.destination / self.source.name


@dataclass(frozen=True)
class BundledModelFile:
    url: str
    source: Path
    destination: Path
    sha256: Optional[str] = None

    @property
    def runtime_relative_path(self) -> Path:
        return self.destination / self.source.name


def detect_os() -> str:
    system_name = platform.system().lower()
    if system_name == "linux":
        return "linux"
    if system_name == "darwin":
        return "macos"
    if system_name == "windows":
        return "windows"

    raise RuntimeError(f"Unsupported OS: {platform.system()}")


def detect_architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"

    raise RuntimeError(f"Unsupported architecture: {platform.machine()}")


def artifact_name(os_name: str, architecture: str) -> str:
    return f"rapidocr-{os_name}-{architecture}"


def executable_filename(os_name: str) -> str:
    if os_name == "windows":
        return f"{EXECUTABLE_NAME}.exe"
    return EXECUTABLE_NAME


def ensure_repo_python_on_sys_path() -> None:
    python_dir_str = str(PYTHON_DIR)
    if python_dir_str not in sys.path:
        sys.path.insert(0, python_dir_str)


def cache_file_from_url(url: str) -> Path:
    return MODEL_CACHE_DIR / Path(url).name


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_bundled_model_file(
    model_files: Dict[Path, BundledModelFile],
    url: str,
    sha256: Optional[str],
) -> None:
    source = cache_file_from_url(url)
    runtime_relative_path = BUNDLED_MODEL_DESTINATION / source.name
    existing = model_files.get(runtime_relative_path)
    if existing is not None:
        if existing.url != url or (
            existing.sha256 is not None
            and sha256 is not None
            and existing.sha256 != sha256
        ):
            raise RuntimeError(
                "Conflicting bundled model metadata for "
                f"{runtime_relative_path}: {existing.url} vs {url}"
            )
        return

    model_files[runtime_relative_path] = BundledModelFile(
        url=url,
        source=source,
        destination=BUNDLED_MODEL_DESTINATION,
        sha256=sha256,
    )


def resolve_default_model_files() -> List[BundledModelFile]:
    """Use RapidOCR's default model resolver to determine files to bundle."""
    ensure_repo_python_on_sys_path()

    from rapidocr.inference_engine.base import FileInfo, InferSession
    from rapidocr.utils.parse_parameters import ParseParams

    cfg = ParseParams.load(RAPIDOCR_PACKAGE_DIR / "config.yaml")
    model_files: Dict[Path, BundledModelFile] = {}

    for section_name, use_key in DEFAULT_MODEL_SECTIONS:
        if not cfg.Global.get(use_key, True):
            continue

        section = getattr(cfg, section_name)
        if section.get("model_path"):
            raise RuntimeError(
                "Bundled default model resolution expects upstream defaults to use "
                f"model_root_dir, but {section_name}.model_path is set."
            )

        engine_type = section.engine_type.value
        if engine_type != SUPPORTED_BUNDLED_ENGINE:
            raise RuntimeError(
                "Standalone PyInstaller packaging currently supports bundled "
                f"{SUPPORTED_BUNDLED_ENGINE} defaults only, but {section_name} "
                f"uses {engine_type}."
            )

        model_info = InferSession.get_model_url(
            FileInfo(
                section.engine_type,
                section.ocr_version,
                section.task_type,
                section.lang_type,
                section.model_type,
            )
        )
        add_bundled_model_file(
            model_files,
            model_info["model_dir"],
            model_info.get("SHA256"),
        )

        if section_name == "Rec":
            dict_url = model_info.get("dict_url")
            if dict_url:
                add_bundled_model_file(model_files, dict_url, None)

    if not model_files:
        raise RuntimeError("No default OCR models were resolved for bundling.")

    return [model_files[path] for path in sorted(model_files)]


def download_bundled_model_files() -> None:
    """Download defaults through RapidOCR's own download_models implementation."""
    ensure_repo_python_on_sys_path()

    from omegaconf import OmegaConf
    from rapidocr.utils.download_models import download_models

    cfg = OmegaConf.load(RAPIDOCR_PACKAGE_DIR / "config.yaml")
    cfg.Global.model_root_dir = str(MODEL_CACHE_DIR)

    with tempfile.TemporaryDirectory() as temp_dir:
        download_config_path = Path(temp_dir) / "config.yaml"
        OmegaConf.save(config=cfg, f=download_config_path)
        download_models(download_config_path)


def prepare_bundled_default_models() -> List[BundledModelFile]:
    model_files = resolve_default_model_files()
    download_bundled_model_files()
    return model_files


def collect_data_files(model_files: Sequence[BundledModelFile]) -> List[DataFile]:
    data_files: List[DataFile] = []

    for yaml_path in sorted(RAPIDOCR_PACKAGE_DIR.rglob("*.yaml")):
        relative_path = yaml_path.relative_to(RAPIDOCR_PACKAGE_DIR)
        if relative_path.parts and relative_path.parts[0] == "models":
            continue

        data_files.append(
            DataFile(
                source=yaml_path,
                destination=Path("rapidocr") / relative_path.parent,
            )
        )

    for model_file in model_files:
        data_files.append(
            DataFile(source=model_file.source, destination=model_file.destination)
        )

    data_files.append(DataFile(source=SERVE_INDEX_HTML, destination=Path("serve")))
    return data_files


def ensure_required_paths(data_files: Sequence[DataFile]) -> None:
    required_paths = [
        PYTHON_DIR,
        RAPIDOCR_PACKAGE_DIR,
        ENTRY_SCRIPT,
        SERVE_INDEX_HTML,
    ]
    required_paths.extend(data_file.source for data_file in data_files)

    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        missing_list = "\n".join(f"  - {path}" for path in missing_paths)
        raise FileNotFoundError(f"Required build inputs are missing:\n{missing_list}")


def clean_previous_outputs() -> None:
    for path in (DIST_DIR, PYINSTALLER_BUILD_DIR):
        if path.exists():
            shutil.rmtree(path)


def build_pyinstaller_args(data_files: Sequence[DataFile]) -> List[str]:
    args = [
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        EXECUTABLE_NAME,
        "--contents-directory",
        CONTENTS_DIR_NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(PYINSTALLER_BUILD_DIR),
        "--specpath",
        str(PYINSTALLER_BUILD_DIR),
        "--paths",
        str(PYTHON_DIR),
        "--paths",
        str(PACKAGING_DIR),
    ]

    for data_file in data_files:
        args.extend(["--add-data", data_file.pyinstaller_arg])

    for hidden_import in HIDDEN_IMPORTS:
        args.extend(["--hidden-import", hidden_import])

    for package_name in COLLECT_BINARIES:
        args.extend(["--collect-binaries", package_name])

    for module_name in EXCLUDED_MODULES:
        args.extend(["--exclude-module", module_name])

    args.append(str(ENTRY_SCRIPT))
    return args


def run_pyinstaller(args: Sequence[str]) -> None:
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller is not installed. Run this script with `uv run python build_cli.py`."
        ) from exc

    PyInstaller.__main__.run(list(args))


def finalize_artifact(final_artifact_name: str) -> Path:
    pyinstaller_output_dir = DIST_DIR / EXECUTABLE_NAME
    artifact_dir = DIST_DIR / final_artifact_name

    if not pyinstaller_output_dir.exists():
        raise FileNotFoundError(f"PyInstaller output directory is missing: {pyinstaller_output_dir}")

    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)

    pyinstaller_output_dir.rename(artifact_dir)
    return artifact_dir


def runtime_file_exists(artifact_dir: Path, relative_path: Path) -> bool:
    return find_runtime_file(artifact_dir, relative_path) is not None


def find_runtime_file(artifact_dir: Path, relative_path: Path) -> Optional[Path]:
    for root in (artifact_dir / CONTENTS_DIR_NAME, artifact_dir):
        candidate = root / relative_path
        if candidate.exists():
            return candidate
    return None


def validate_artifact(
    artifact_dir: Path,
    os_name: str,
    data_files: Iterable[DataFile],
    bundled_model_files: Sequence[BundledModelFile],
) -> None:
    executable_path = artifact_dir / executable_filename(os_name)
    internal_dir = artifact_dir / CONTENTS_DIR_NAME

    if not executable_path.is_file():
        raise FileNotFoundError(f"Expected executable is missing: {executable_path}")

    if not internal_dir.is_dir():
        raise FileNotFoundError(f"Expected PyInstaller contents directory is missing: {internal_dir}")

    missing_runtime_files = [
        data_file.runtime_relative_path
        for data_file in data_files
        if not runtime_file_exists(artifact_dir, data_file.runtime_relative_path)
    ]
    if missing_runtime_files:
        missing_list = "\n".join(f"  - {path}" for path in missing_runtime_files)
        raise FileNotFoundError(f"Expected runtime data files are missing:\n{missing_list}")

    invalid_model_files = []
    for model_file in bundled_model_files:
        runtime_path = find_runtime_file(artifact_dir, model_file.runtime_relative_path)
        if runtime_path is None or not model_file.sha256:
            continue

        if file_sha256(runtime_path) != model_file.sha256:
            invalid_model_files.append(runtime_path)

    if invalid_model_files:
        invalid_list = "\n".join(f"  - {path}" for path in invalid_model_files)
        raise RuntimeError(f"Bundled OCR model checksum mismatch:\n{invalid_list}")


def main() -> None:
    os_name = detect_os()
    architecture = detect_architecture()
    final_artifact_name = artifact_name(os_name, architecture)
    print("Preparing bundled default OCR models...")
    bundled_model_files = prepare_bundled_default_models()
    data_files = collect_data_files(bundled_model_files)

    ensure_required_paths(data_files)
    clean_previous_outputs()

    pyinstaller_args = build_pyinstaller_args(data_files)
    print(f"Building {final_artifact_name} with PyInstaller...")
    run_pyinstaller(pyinstaller_args)

    artifact_dir = finalize_artifact(final_artifact_name)
    validate_artifact(artifact_dir, os_name, data_files, bundled_model_files)
    print(f"Created {artifact_dir}")


if __name__ == "__main__":
    main()

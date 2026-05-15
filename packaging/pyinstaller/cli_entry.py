from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9003
MODEL_DIR_ENV_VAR = "RAPIDOCR_MODEL_DIR"
BUNDLED_MODEL_DIR = Path("rapidocr") / "models"


def _freeze_multiprocessing_support() -> None:
    """Handle PyInstaller multiprocessing helper process command lines."""
    if not getattr(sys, "frozen", False):
        return

    from multiprocessing import freeze_support

    freeze_support()


def _add_repo_python_to_sys_path() -> None:
    """Make the upstream rapidocr package importable from a source checkout."""
    candidates = []

    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.extend(
            [
                bundle_root / "python",
                Path(sys.executable).resolve().parent / "python",
                Path(sys.executable).resolve().parent / "_internal" / "python",
            ]
        )

    current_file = Path(__file__).resolve()
    candidates.extend(
        [
            current_file.parents[2] / "python",
            current_file.parent / "python",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)


def bundled_path(relative_path: str | Path) -> Path:
    """Resolve a data file path from either the PyInstaller bundle or source tree."""
    relative_path = Path(relative_path)
    candidates = []

    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        executable_root = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                bundle_root / relative_path,
                bundle_root / "python" / relative_path,
                executable_root / relative_path,
                executable_root / "python" / relative_path,
                executable_root / "_internal" / relative_path,
                executable_root / "_internal" / "python" / relative_path,
            ]
        )

    current_file = Path(__file__).resolve()
    candidates.extend(
        [
            current_file.parent / relative_path,
            current_file.parents[2] / relative_path,
            current_file.parents[2] / "python" / relative_path,
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0] if candidates else current_file.parent / relative_path


def _patch_upstream_data_paths() -> None:
    """Point upstream defaults at bundled data files when PyInstaller relocates them."""
    try:
        import rapidocr.cli as rapidocr_cli
        import rapidocr.main as rapidocr_main
    except ImportError:
        return

    config_path = bundled_path(Path("rapidocr") / "config.yaml")
    if not config_path.exists():
        return

    rapidocr_main.DEFAULT_CFG_PATH = config_path
    rapidocr_cli.DEFAULT_CFG_PATH = config_path


def resolve_model_cache_dir() -> Path:
    """Return the configured model cache directory without creating it."""
    override = os.environ.get(MODEL_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()

    return (Path.home() / ".cache" / "rapidocr" / "models").resolve()


def ensure_model_cache_dir() -> Path:
    """Create the model cache directory and seed bundled defaults when available."""
    model_cache_dir = resolve_model_cache_dir()
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    seed_model_cache_from_bundle(model_cache_dir)
    return model_cache_dir


def seed_model_cache_from_bundle(model_cache_dir: Path) -> None:
    """Copy bundled default models into the writable cache without overwriting users."""
    bundled_model_dir = bundled_path(BUNDLED_MODEL_DIR)
    if not bundled_model_dir.is_dir():
        return

    for bundled_model_file in sorted(bundled_model_dir.iterdir()):
        if not bundled_model_file.is_file():
            continue

        cache_model_file = model_cache_dir / bundled_model_file.name
        if cache_model_file.exists():
            continue

        shutil.copy2(bundled_model_file, cache_model_file)


def model_cache_params() -> Dict[str, str]:
    """Build RapidOCR params that force model loading/downloading into the cache."""
    return {"Global.model_root_dir": str(ensure_model_cache_dir())}


def _download_models(config_path: Optional[str]) -> None:
    """Run upstream model download with the standalone model cache injected."""
    from rapidocr.main import DEFAULT_CFG_PATH
    from rapidocr.utils.download_models import download_models
    from rapidocr.utils.parse_parameters import ParseParams

    model_cache_dir = ensure_model_cache_dir()
    cfg_path = config_path or str(DEFAULT_CFG_PATH)

    original_load = ParseParams.__dict__["load"]
    original_load_func = original_load.__func__

    @classmethod
    def load_with_model_cache(cls, file_path):
        cfg = original_load_func(cls, file_path)
        cfg.Global.model_root_dir = str(model_cache_dir)
        return cfg

    ParseParams.load = load_with_model_cache
    try:
        download_models(cfg_path)
    finally:
        ParseParams.load = original_load


def _run_upstream_cli(arg_list: Optional[List[str]] = None) -> None:
    import rapidocr.main as rapidocr_main

    upstream_rapidocr = rapidocr_main.RapidOCR
    upstream_download_models = rapidocr_main.download_models

    class CachedRapidOCR(upstream_rapidocr):
        def __init__(self, config_path=None, params=None):
            merged_params = {
                **(params or {}),
                **model_cache_params(),
            }
            super().__init__(config_path=config_path, params=merged_params)

    rapidocr_main.RapidOCR = CachedRapidOCR
    rapidocr_main.download_models = _download_models
    try:
        rapidocr_main.main(arg_list)
    finally:
        rapidocr_main.RapidOCR = upstream_rapidocr
        rapidocr_main.download_models = upstream_download_models


def _parse_serve_args(arg_list: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=f"{Path(sys.argv[0]).name} serve",
        description="Start the RapidOCR HTTP server in the foreground.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Listen address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port")
    parser.add_argument(
        "--open",
        action="store_true",
        default=False,
        help="Open the web UI in the default browser after startup",
    )
    return parser.parse_args(arg_list)


def _browser_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/"


def _run_serve(arg_list: List[str]) -> None:
    args = _parse_serve_args(arg_list)
    ensure_model_cache_dir()
    _patch_upstream_data_paths()

    if args.open:
        threading.Timer(1.0, webbrowser.open, args=(_browser_url(args.host, args.port),)).start()

    import uvicorn

    uvicorn.run("serve.app:app", host=args.host, port=args.port)


def main(arg_list: Optional[List[str]] = None) -> None:
    _add_repo_python_to_sys_path()

    argv = list(sys.argv[1:] if arg_list is None else arg_list)
    if argv and argv[0] == "serve":
        _run_serve(argv[1:])
        return

    _patch_upstream_data_paths()
    _run_upstream_cli(argv)


if __name__ == "__main__":
    _freeze_multiprocessing_support()
    main()

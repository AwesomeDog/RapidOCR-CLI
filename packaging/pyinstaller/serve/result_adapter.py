from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict

try:
    import numpy as np
except ImportError:  # pragma: no cover - final packaged runtime includes numpy
    np = None


def json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if np is not None:
        if isinstance(value, np.generic):
            return value.item()

        if isinstance(value, np.ndarray):
            return value.tolist()

    if is_dataclass(value):
        return json_compatible(asdict(value))

    if isinstance(value, dict):
        return {str(k): json_compatible(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]

    return value


def upstream_json_result(result: Any) -> Any:
    if not hasattr(result, "to_json"):
        return json_compatible(result)

    json_results = result.to_json()
    return [] if json_results is None else json_compatible(json_results)


def serialize_ocr_result(result: Any) -> Dict[str, Any]:
    response = {
        "results": upstream_json_result(result),
        "elapse": float(getattr(result, "elapse", 0.0) or 0.0),
    }

    word_results = getattr(result, "word_results", None)
    if word_results:
        response["word_results"] = json_compatible(word_results)

    return response

"""Benchmark Sionna sampling levels against the highest configured reference."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from laesim_scene.config import load_config
from laesim_scene.pipeline import generate


def _error_stats(current: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    error = np.abs(np.asarray(current, dtype=float) - np.asarray(reference, dtype=float))
    return {
        "mean_abs_error": float(np.mean(error)),
        "median_abs_error": float(np.median(error)),
        "p95_abs_error": float(np.percentile(error, 95)),
        "max_abs_error": float(np.max(error)),
    }


def _masked_error_stats(
    current: np.ndarray,
    reference: np.ndarray,
    mask: np.ndarray,
) -> dict[str, float | int]:
    error = np.abs(np.asarray(current, dtype=float) - np.asarray(reference, dtype=float))[mask]
    if error.size == 0:
        return {"sample_count": 0}
    return {"sample_count": int(error.size), **_error_stats(error, np.zeros_like(error))}


def _load_arrays(run_dir: Path) -> dict[str, np.ndarray]:
    with np.load(run_dir / "radio_volume.npz") as data:
        return {
            "rsrp_dbm": np.asarray(data["rsrp_dbm"], dtype=float),
            "sinr_db": np.asarray(data["sinr_db"], dtype=float),
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--samples", type=int, nargs="+", default=[65536, 262144, 1048576])
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    project_root = args.project_root.resolve()
    sample_levels = sorted(set(args.samples))
    if not sample_levels or sample_levels[0] <= 0:
        raise ValueError("samples must contain positive integers")

    base = load_config(args.config)
    if not base.radio.enabled:
        raise ValueError("benchmark config must enable the radio stage")

    runs: list[dict[str, Any]] = []
    arrays: dict[int, dict[str, np.ndarray]] = {}
    for samples in sample_levels:
        config = replace(
            base,
            name=f"{base.name}-samples-{samples}",
            radio=replace(base.radio, samples_per_logical_sector=samples),
        )
        started = time.perf_counter()
        result = generate(config, project_root=project_root)
        wall_elapsed_s = time.perf_counter() - started
        run_dir = Path(result["output_dir"])
        manifest = json.loads((run_dir / "radio_manifest.json").read_text(encoding="utf-8"))
        arrays[samples] = _load_arrays(run_dir)
        runs.append(
            {
                "samples_per_logical_sector": samples,
                "run_id": result["run_id"],
                "output_dir": str(run_dir),
                "reused": bool(result.get("reused", False)),
                "wall_elapsed_s": round(wall_elapsed_s, 6),
                "solver_elapsed_s": manifest.get("runtime", {}).get("solver_elapsed_s"),
                "shape": manifest["shape"],
                "transmitter_count": len(manifest["transmitter_ids"]),
            }
        )

    reference_samples = sample_levels[-1]
    reference = arrays[reference_samples]
    comparisons = []
    reference_serving = np.argmax(reference["rsrp_dbm"], axis=0)
    reference_best_rsrp = np.max(reference["rsrp_dbm"], axis=0)
    reference_best_sinr = np.take_along_axis(
        reference["sinr_db"], reference_serving[None, ...], axis=0
    )[0]
    for samples in sample_levels[:-1]:
        current = arrays[samples]
        current_serving = np.argmax(current["rsrp_dbm"], axis=0)
        current_best_rsrp = np.max(current["rsrp_dbm"], axis=0)
        current_best_sinr = np.take_along_axis(
            current["sinr_db"], current_serving[None, ...], axis=0
        )[0]
        reference_detectable = reference_best_rsrp >= -125.0
        current_detectable = current_best_rsrp >= -125.0
        common_detectable = reference_detectable & current_detectable
        comparisons.append(
            {
                "samples_per_logical_sector": samples,
                "reference_samples_per_logical_sector": reference_samples,
                "rsrp_db": _error_stats(current["rsrp_dbm"], reference["rsrp_dbm"]),
                "sinr_db": _error_stats(current["sinr_db"], reference["sinr_db"]),
                "serving_cell_agreement": float(
                    np.mean(current_serving == reference_serving)
                ),
                "detectable_region": {
                    "reference_fraction": float(np.mean(reference_detectable)),
                    "current_fraction": float(np.mean(current_detectable)),
                    "common_fraction": float(np.mean(common_detectable)),
                    "best_rsrp_db": _masked_error_stats(
                        current_best_rsrp, reference_best_rsrp, common_detectable
                    ),
                    "serving_sinr_db": _masked_error_stats(
                        current_best_sinr, reference_best_sinr, common_detectable
                    ),
                    "serving_cell_agreement": (
                        float(np.mean((current_serving == reference_serving)[common_detectable]))
                        if np.any(common_detectable)
                        else None
                    ),
                },
            }
        )

    report = {
        "schema_version": "wireless-city-radio-sampling-benchmark-v1",
        "status": "complete",
        "config": str(args.config),
        "reference_samples_per_logical_sector": reference_samples,
        "runs": runs,
        "comparisons": comparisons,
    }
    output = args.output or (
        project_root / "examples" / "outputs" / f"{base.name}-report.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({**report, "report": str(output)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

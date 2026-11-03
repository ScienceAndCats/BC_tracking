"""User-facing .env settings and fixed pipeline wiring.

Output filenames, report columns, sample filtering, and execution order live here
rather than in the user config. Legacy YAML/JSON configs remain readable.
"""

from __future__ import annotations

import csv
from pathlib import Path


def boolean(value: str) -> bool:
    if value.lower() not in {"true", "false"}:
        raise ValueError("expected true or false")
    return value.lower() == "true"


def file_list(value: str) -> list[str]:
    return [name.strip() for name in next(csv.reader([value], skipinitialspace=True)) if name.strip()]


def threads(value: str):
    if value.lower() == "auto":
        return "auto"
    number = int(value)
    if number < 1:
        raise ValueError("expected auto or a positive integer")
    return number


# ENV name: (destination, Python key, default, parser). These are the settings
# retained in the simplified user config; everything else is fixed below.
OPTIONS = {
    "THREADS": ("shared", "threads", "auto", threads),
    "UPSTREAM": ("bun_extract", "upstream", "TCATAGTGAGCTCAGCG", str),
    "DOWNSTREAM": ("bun_extract", "downstream", "GTGCCCCACAAGAGGTT", str),
    "MIN_MATCH": ("bun_extract", "min_match", 11, int),
    "PROGRESS_EVERY": ("bun_extract", "progress_every", 200000, int),
    "EXPECTED_BARCODE_LEN": ("barcode_from_bun_csv", "expected_barcode_len", 24, int),
    "MIN_BARCODE_LEN": ("barcode_from_bun_csv", "min_barcode_len", 1, int),
    "MAX_BARCODE_LEN": ("barcode_from_bun_csv", "max_barcode_len", 100, int),
    "INCLUDE_EMPTY_BARCODES": ("barcode_from_bun_csv", "include_empty_barcodes", True, boolean),
    "MIN_REAL_BARCODE_COUNT": ("barcode_from_bun_csv", "min_real_barcode_count", 3, int),
    "COLLAPSE_BARCODES": ("barcode_from_bun_csv", "collapse_barcodes", True, boolean),
    "STARCODE_PATH": ("barcode_from_bun_csv", "starcode_path", "starcode", str),
    "STARCODE_DISTANCE": ("barcode_from_bun_csv", "starcode_distance", 3, int),
    "STARCODE_CLUSTER_RATIO": ("barcode_from_bun_csv", "starcode_cluster_ratio", 3.0, float),
    "EXPLICIT_FILES": ("ordered_barcode_sample_analysis", "explicit_files", [], file_list),
    "USE_EXISTING_REAL_COLUMN": ("ordered_barcode_sample_analysis", "use_existing_real_column", True, boolean),
    "TOP_N_FOR_EACH_RANKED_OUTPUT": ("ordered_barcode_sample_analysis", "top_n_for_each_ranked_output", 500, int),
    "REAL_BARCODE_SAMPLE": ("plots", "real_barcode_sample", "first", str),
    "MAKE_INTERACTIVE_TRAJECTORY_PLOTS": ("plots", "make_interactive_trajectory_plots", True, boolean),
    "TOP_N_TO_PLOT": ("plots", "top_n_to_plot", 100, int),
    "MAX_BARCODES_IN_HEATMAP": ("plots", "max_barcodes_in_heatmap", 200, int),
    "MAKE_PLOTS": ("plots", "make_plots", True, boolean),
    "MAKE_HEATMAPS": ("plots", "make_heatmaps", True, boolean),
    "MAKE_FIRST_VS_LAST_SCATTER": ("plots", "make_first_vs_last_scatter", True, boolean),
    "MAKE_TOP_TRAJECTORY_PLOTS": ("plots", "make_top_trajectory_plots", True, boolean),
    "MAKE_ALL_BARCODE_TRAJECTORY_PLOT": ("plots", "make_all_barcode_trajectory_plot", True, boolean),
    "ALL_TRAJECTORY_MIN_COUNT_IN_ANY_SAMPLE": ("plots", "all_trajectory_min_count_in_any_sample", 3, int),
    "ALL_TRAJECTORY_MAX_BARCODES_TO_PLOT": ("plots", "all_trajectory_max_barcodes_to_plot", 5000, int),
    "MAKE_GAIN_LOSS_RATIO_HEATMAP": ("plots", "make_gain_loss_ratio_heatmap", True, boolean),
    "GAIN_LOSS_HEATMAP_MIN_COUNT_IN_ANY_SAMPLE": ("plots", "gain_loss_heatmap_min_count_in_any_sample", 3, int),
    "GAIN_LOSS_HEATMAP_MAX_BARCODES": ("plots", "gain_loss_heatmap_max_barcodes", 200, int),
    "GAIN_LOSS_HEATMAP_SORT": ("plots", "gain_loss_heatmap_sort", "last_vs_first", str),
    "GAIN_LOSS_HEATMAP_SHOW_NUMBERS": ("plots", "gain_loss_heatmap_show_numbers", True, boolean),
    "GAIN_LOSS_HEATMAP_NUMBER_DECIMALS": ("plots", "gain_loss_heatmap_number_decimals", 1, int),
    "LOG_SCALE_Y_AXIS": ("plots", "log_scale_y_axis", True, boolean),
    "DPI": ("plots", "dpi", 300, int),
}


def load_env_config(path: Path) -> dict:
    from dotenv.parser import parse_stream

    # Parse literal values without importing them into os.environ or expanding
    # ${...}. Unlike dotenv_values, reject malformed lines instead of skipping them.
    values = {}
    with path.open(encoding="utf-8-sig") as handle:
        for binding in parse_stream(handle):
            if binding.error:
                raise ValueError(f"{path}:{binding.original.line}: invalid .env assignment")
            if binding.key is not None:
                if binding.key in values:
                    raise ValueError(f"Duplicate config.env setting: {binding.key}")
                values[binding.key] = binding.value
    unknown = set(values) - set(OPTIONS) - {"INPUT_DIR", "OUTPUT_DIR", "BARCODE_GROUPS_CSV"}
    if unknown:
        raise ValueError("Unknown config.env settings: " + ", ".join(sorted(unknown)))
    if not values.get("INPUT_DIR"):
        raise ValueError("config.env requires INPUT_DIR")
    if "OUTPUT_DIR" in values and not values["OUTPUT_DIR"]:
        raise ValueError("OUTPUT_DIR cannot be empty")
    base = path.resolve().parent

    def resolve(value):
        result = Path(value).expanduser()
        return str(result.resolve() if result.is_absolute() else (base / result).resolve())

    output = Path(resolve(values.get("OUTPUT_DIR", "outputs")))
    buns, barcodes, analysis = output / "bun_matches", output / "barcodes", output / "analysis"
    steps = {
        "bun_extract": {
            "input_dir": resolve(values["INPUT_DIR"]),
            "out_dir": str(buns), "cross_file_barcode_csv": str(buns / "barcode_file_membership.csv"),
            "max_reads": None,
        },
        "barcode_from_bun_csv": {
            "in_csv_dir": str(buns), "in_csv_glob": "*_bun_matches.csv",
            "out_csv_dir": str(barcodes / "augmented"),
            "out_barcode_report_dir": str(barcodes / "per_file_reports"),
            "out_multi_file_barcode_report": str(barcodes / "barcode_multi_file_membership.csv"),
            "out_file_summary_report": str(barcodes / "barcode_file_summary.csv"),
            "out_additional_barcodes": str(barcodes / "additional_barcodes.csv"),
            "starcode_clustering_algorithm": "message_passing", "starcode_threads": 1,
        },
        "ordered_barcode_sample_analysis": {
            "input_dir": str(barcodes / "per_file_reports"), "output_dir": str(analysis),
            "csv_pattern": "*_barcode_counts.csv",
            "require_expected_length": True, "min_count_to_call_barcode_present": 3,
            "min_samples_present_to_retain_barcode": 1, "min_total_count_across_all_samples": 0,
            "frequency_denominator": "all_barcodes", "before_n_samples": 1, "after_n_samples": 1,
        },
    }
    cfg = {"barcode_groups_csv": resolve(values["BARCODE_GROUPS_CSV"]) if values.get("BARCODE_GROUPS_CSV") else None}
    plots = {}
    for name, (scope, key, default, parser) in OPTIONS.items():
        target = cfg if scope == "shared" else plots if scope == "plots" else steps[scope]
        if name in values:
            if values[name] is None:
                raise ValueError(f"{name} requires a value after '='")
            try:
                target[key] = parser(values[name])
            except ValueError as exc:
                raise ValueError(f"Invalid {name}: {exc}") from exc
        else:
            target[key] = default
    barcode_cfg = steps["barcode_from_bun_csv"]
    starcode = barcode_cfg["starcode_path"]
    if "/" in starcode or "\\" in starcode:
        barcode_cfg["starcode_path"] = resolve(starcode)
    steps["ordered_barcode_sample_analysis"]["expected_barcode_length"] = barcode_cfg["expected_barcode_len"]
    steps["ordered_barcode_sample_analysis"]["plots"] = plots
    cfg["run_order"] = list(steps)
    cfg["scripts"] = {name: {"enabled": True, "config": settings} for name, settings in steps.items()}
    return cfg

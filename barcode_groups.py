"""Barcode catalog loading, shared trajectory styles, and unmatched-read reports."""

from __future__ import annotations

import colorsys
import csv
from collections import Counter
from pathlib import Path


UNLISTED_LABEL = "Not in barcode CSV"
UNLISTED_COLOR = "#808080"
GROUP_COLORS = (
    "#636efa", "#ef553b", "#00a878", "#ab63fa", "#e58f00",
    "#19b5c4", "#d45087", "#7c9a00", "#a05a2c", "#3366aa",
)


def load_barcode_groups(path) -> dict[str, str] | None:
    """Read exact sequence-to-group assignments; None disables catalog features."""
    if not path:
        return None
    groups = {}
    with Path(path).expanduser().open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        reader.fieldnames = [name.strip() for name in (reader.fieldnames or [])]
        if not {"barcode", "group"}.issubset(reader.fieldnames):
            raise ValueError(f"{path}: barcode groups CSV requires 'barcode' and 'group' columns")
        for line, row in enumerate(reader, start=2):
            barcode = (row.get("barcode") or "").strip().upper()
            if not barcode:
                continue
            group = (row.get("group") or "").strip()
            if not group:
                raise ValueError(f"{path}: missing group for barcode {barcode} at row {line}")
            if barcode in groups and groups[barcode] != group:
                raise ValueError(f"{path}: conflicting groups for barcode {barcode} at row {line}")
            groups[barcode] = group
    return groups


def configure_barcode_groups(cfg: dict) -> None:
    groups = load_barcode_groups(cfg.get("barcode_groups_csv"))
    cfg["_barcode_groups"] = groups
    colors = {}
    # Use the complete catalog, so subsets and reordered trajectories keep their colors.
    for index, group in enumerate(sorted(set((groups or {}).values()))):
        if index < len(GROUP_COLORS):
            color = GROUP_COLORS[index]
        else:
            rgb = colorsys.hsv_to_rgb((index * 0.61803398875) % 1, 0.65, 0.8)
            color = "#" + "".join(f"{round(component * 255):02x}" for component in rgb)
        colors[group] = color
    cfg["_barcode_group_colors"] = colors


def trajectory_style(barcode: str, cfg: dict):
    """Return (group, color, opacity), or None for the original per-barcode colors."""
    groups = cfg.get("_barcode_groups")
    if groups is None:
        return None
    group = groups.get(str(barcode).strip().upper())
    if group is None:
        return UNLISTED_LABEL, UNLISTED_COLOR, 0.5
    return group, cfg["_barcode_group_colors"][group], 1.0


def trajectory_legend(barcodes, cfg: dict):
    """One legend entry per represented group, with unmatched barcodes last."""
    styles = {trajectory_style(barcode, cfg) for barcode in barcodes}
    return sorted((style for style in styles if style is not None),
                  key=lambda style: (style[2] == 0.5, style[0]))


def write_additional_barcodes(path: Path, per_file_counts: dict[str, Counter]) -> None:
    """Write one row per unmatched, nonempty extracted sequence, before filtering."""
    totals = Counter()
    files = {}
    for label, counts in per_file_counts.items():
        totals.update(counts)
        for barcode in counts:
            files.setdefault(barcode, []).append(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "barcode", "barcode_len", "total_count", "num_files", "files",
        ])
        writer.writeheader()
        for barcode, count in sorted(totals.items(), key=lambda item: (-item[1], item[0])):
            labels = sorted(files[barcode])
            writer.writerow(dict(barcode=barcode, barcode_len=len(barcode), total_count=count,
                                 num_files=len(labels), files=";".join(labels)))

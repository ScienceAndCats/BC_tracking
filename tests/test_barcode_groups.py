"""Catalog matching, grouped trajectories, and exact unmatched-barcode reporting."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml

import barcode_from_bun_csv as extraction
import ordered_barcode_sample_analysis as analysis
from barcode_groups import (
    UNLISTED_COLOR, UNLISTED_LABEL, configure_barcode_groups, load_barcode_groups,
    trajectory_legend, trajectory_style,
)
from config_helpers import load_script_config


class BarcodeGroupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = self.root / "groups.csv"
        self.catalog.write_text("well,barcode,group\nA1,AAAA,LB\nA2,CCCC,LB\nB1,GGGG,Spent SA\nA3,,LB\n")
        self.cfg = {"barcode_groups_csv": str(self.catalog)}
        configure_barcode_groups(self.cfg)

    def test_catalog_ignores_blank_rows_and_same_group_duplicates(self):
        self.catalog.write_text("\ufeffwell,barcode,group\nA1, aaaa ,LB\nA2,AAAA,LB\nA3,,LB\nB1, cgcn ,Spent SA\n")
        self.assertEqual(load_barcode_groups(self.catalog), {"AAAA": "LB", "CGCN": "Spent SA"})

    def test_invalid_catalog_is_reported_instead_of_silently_recoloring(self):
        for contents, message in [
            ("barcode,well\nAAAA,A1\n", "requires 'barcode' and 'group'"),
            ("barcode,group\nAAAA,\n", "missing group"),
            ("barcode,group\nAAAA,LB\naaaa,Spent SA\n", "conflicting groups"),
        ]:
            with self.subTest(contents=contents):
                self.catalog.write_text(contents)
                with self.assertRaisesRegex(ValueError, message):
                    load_barcode_groups(self.catalog)

    def test_group_styles_are_shared_and_independent_of_plot_subset(self):
        self.assertEqual(trajectory_style("AAAA", self.cfg), trajectory_style("cccc", self.cfg))
        self.assertNotEqual(trajectory_style("AAAA", self.cfg)[1], trajectory_style("GGGG", self.cfg)[1])
        self.assertEqual(trajectory_style("TTTT", self.cfg), (UNLISTED_LABEL, UNLISTED_COLOR, 0.5))
        full = trajectory_legend(["TTTT", "AAAA", "CCCC", "GGGG"], self.cfg)
        self.assertEqual([item[0] for item in full], ["LB", "Spent SA", UNLISTED_LABEL])
        self.assertEqual(trajectory_legend(["CCCC"], self.cfg), [full[0]])

    def test_empty_catalog_marks_everything_unlisted_but_absent_catalog_disables_feature(self):
        self.catalog.write_text("barcode,group\n,LB\n")
        configure_barcode_groups(self.cfg)
        self.assertEqual(trajectory_style("AAAA", self.cfg)[2], 0.5)
        configure_barcode_groups(empty := {})
        self.assertIsNone(trajectory_style("AAAA", empty))

    def test_catalog_path_is_relative_to_config_for_shared_and_standalone_configs(self):
        config = self.root / "pipeline.yaml"
        config.write_text(yaml.safe_dump({"barcode_groups_csv": "groups.csv", "scripts": {
            "barcode_from_bun_csv": {"config": {}},
            "ordered_barcode_sample_analysis": {"config": {"barcode_groups_csv": None}},
        }}))
        self.assertEqual(load_script_config(config, "barcode_from_bun_csv")["barcode_groups_csv"], str(self.catalog))
        self.assertIsNone(load_script_config(config, "ordered_barcode_sample_analysis")["barcode_groups_csv"])
        config.write_text("barcode_groups_csv: groups.csv\n")
        self.assertEqual(load_script_config(config, "barcode_from_bun_csv")["barcode_groups_csv"], str(self.catalog))

    def test_png_trajectories_have_shared_colors_half_opaque_unlisted_and_group_legend(self):
        analysis.ensure_analysis_dependencies()
        fig, ax = analysis.plt.subplots()
        cfg = {**self.cfg, "pseudocount_for_log_plots": 1e-9, "dpi": 50}
        freqs = pd.DataFrame([[0.2, 0.1], [0.1, 0.2], [0.3, 0.1]],
                             index=["AAAA", "CCCC", "TTTT"], columns=["first", "last"])
        with patch.object(analysis.plt, "subplots", return_value=(fig, ax)):
            analysis.save_trajectory_plot(list(freqs.index), freqs, self.root / "plot.png", "Groups", cfg)
        self.assertEqual(ax.lines[0].get_color(), ax.lines[1].get_color())
        self.assertEqual(ax.lines[2].get_color(), UNLISTED_COLOR)
        self.assertEqual(ax.lines[2].get_alpha(), 0.5)
        self.assertEqual([text.get_text() for text in ax.get_legend().get_texts()], ["LB", UNLISTED_LABEL])
        self.assertTrue((self.root / "plot.png").is_file())

    def test_extraction_reports_all_unlisted_sequences_before_length_and_count_filters(self):
        inputs = self.root / "buns"
        inputs.mkdir()
        for label, barcodes in [("first", ["AAAA", "TTTT", "TTTT", "G", "A" * 10, ""]),
                                ("last", ["CCCC", "TTTT"])]:
            with (inputs / f"{label}_bun_matches.csv").open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["barcode", "barcode_len"])
                writer.writerows((barcode, len(barcode)) for barcode in barcodes)
        cfg = {"barcode_groups_csv": "groups.csv", "in_csv_dir": str(inputs),
               "out_csv_dir": str(self.root / "augmented"),
               "out_barcode_report_dir": str(self.root / "counts"),
               "out_multi_file_barcode_report": str(self.root / "membership.csv"),
               "out_file_summary_report": str(self.root / "summary.csv"),
               "out_additional_barcodes": str(self.root / "additional.csv"),
               "min_barcode_len": 3, "max_barcode_len": 6, "min_real_barcode_count": 5, "threads": 2}
        path = self.root / "config.yaml"
        path.write_text(yaml.safe_dump(cfg))
        with patch.object(sys, "argv", ["extract", "--config", str(path)]):
            extraction.main()
        with (self.root / "additional.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["barcode"] for row in rows], ["TTTT", "A" * 10, "G"])
        self.assertEqual(rows[0]["total_count"], "3")
        self.assertEqual(rows[0]["files"], "first;last")
        self.assertEqual(rows[0]["num_files"], "2")
        counts = pd.read_csv(self.root / "counts/first_barcode_counts.csv")
        self.assertEqual(set(counts.barcode), {"AAAA", "TTTT"})
        self.assertFalse(counts.is_real_barcode.any())

    def test_single_file_all_known_writes_header_only_and_rerun_replaces_old_report(self):
        source = self.root / "single.csv"
        source.write_text("barcode,barcode_len\nTTTT,4\n")
        cfg = {"barcode_groups_csv": "groups.csv", "in_csv": str(source),
               "out_csv": str(self.root / "augmented.csv"),
               "out_barcode_report": str(self.root / "counts.csv"),
               "out_file_summary_report": str(self.root / "summary.csv"), "threads": 1}
        path = self.root / "config.yaml"
        path.write_text(yaml.safe_dump(cfg))
        for sequence, expected in [("TTTT", ["TTTT"]), ("AAAA", [])]:
            source.write_text(f"barcode,barcode_len\n{sequence},4\n")
            with patch.object(sys, "argv", ["extract", "--config", str(path)]):
                extraction.main()
            report = pd.read_csv(self.root / "additional_barcodes.csv")
            self.assertEqual(report.barcode.tolist(), expected)


if __name__ == "__main__":
    unittest.main()

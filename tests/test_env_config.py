"""Typed .env configuration, fixed pipeline wiring, and command-line integration."""

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config_helpers import load_config_file, load_script_config
from run_pipeline import load_pipeline_config, selected_script_names


REPO = Path(__file__).resolve().parents[1]


class EnvConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "config.env"

    def config(self, contents):
        self.path.write_text(contents)
        return load_config_file(self.path)

    def test_retained_settings_types_shared_catalog_and_single_output_root(self):
        cfg = self.config('''# Comment
INPUT_DIR="input reads"
OUTPUT_DIR='results #1' # inline comment
BARCODE_GROUPS_CSV="groups.csv"
THREADS=2
EXPECTED_BARCODE_LEN=20
EXPLICIT_FILES='first.fastq.gz,last.fastq.gz'
COLLAPSE_BARCODES=false
STARCODE_CLUSTER_RATIO=4.5
TOP_N_TO_PLOT=100
''')
        self.assertEqual(selected_script_names(cfg), ["bun_extract", "barcode_from_bun_csv", "ordered_barcode_sample_analysis"])
        bun = load_script_config(self.path, "bun_extract")
        barcode = load_script_config(self.path, "barcode_from_bun_csv")
        analysis = load_script_config(self.path, "ordered_barcode_sample_analysis")
        self.assertEqual(bun["input_dir"], str(self.root / "input reads"))
        self.assertEqual(bun["threads"], 2)
        self.assertEqual(analysis["barcode_groups_csv"], str(self.root / "groups.csv"))
        self.assertEqual(analysis["explicit_files"], ["first.fastq.gz", "last.fastq.gz"])
        self.assertEqual(analysis["expected_barcode_length"], 20)
        self.assertFalse(barcode["collapse_barcodes"])
        self.assertEqual(barcode["starcode_cluster_ratio"], 4.5)
        self.assertEqual(barcode["starcode_threads"], 1)
        self.assertEqual(analysis["plots"]["top_n_to_plot"], 100)
        for step, keys in [(bun, ["out_dir", "cross_file_barcode_csv"]),
                           (barcode, ["out_csv_dir", "out_barcode_report_dir", "out_multi_file_barcode_report",
                                      "out_file_summary_report", "out_additional_barcodes"]),
                           (analysis, ["output_dir"])]:
            for key in keys:
                self.assertTrue(Path(step[key]).is_relative_to(self.root / "results #1"), step[key])

    def test_no_shell_expansion_or_process_environment_override(self):
        with patch.dict(os.environ, {"OUTPUT_DIR": "/ignored", "THREADS": "99"}):
            cfg = self.config('INPUT_DIR="${UNEXPANDED}/reads"\nBARCODE_GROUPS_CSV=\n')
        self.assertEqual(cfg["scripts"]["bun_extract"]["config"]["input_dir"],
                         str(self.root / "${UNEXPANDED}/reads"))
        self.assertIsNone(cfg["barcode_groups_csv"])
        self.assertEqual(cfg["threads"], "auto")
        self.assertEqual(cfg["scripts"]["ordered_barcode_sample_analysis"]["config"]["output_dir"],
                         str(self.root / "outputs/analysis"))

    def test_invalid_settings_fail_clearly(self):
        for text, message in [
            ("OUTPUT_DIR=outputs\n", "requires INPUT_DIR"),
            ("INPUT_DIR=data\nOUTPUT_DIR=\n", "OUTPUT_DIR cannot be empty"),
            ("INPUT_DIR=data\nMAKE_PLOTS=maybe\n", "Invalid MAKE_PLOTS"),
            ("INPUT_DIR=data\nTHREADS=0\n", "Invalid THREADS"),
            ("INPUT_DIR=data\nMIN_MATCH=eleven\n", "Invalid MIN_MATCH"),
            ("INPUT_DIR=data\nTYPO_SETTING=true\n", "Unknown config.env settings"),
            ("INPUT_DIR=data\nINPUT_DIR=other\n", "Duplicate config.env setting"),
            ('INPUT_DIR=data\nUPSTREAM="unterminated\n', "invalid .env assignment"),
            ("INPUT_DIR=data\nMIN_MATCH\n", "requires a value"),
        ]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                self.config(text)

    def test_full_pipeline_from_another_working_directory_for_one_or_multiple_inputs(self):
        for samples in [("first",), ("first", "last")]:
            with self.subTest(samples=samples):
                run = self.root / str(len(samples))
                reads = run / "input reads"
                reads.mkdir(parents=True)
                (run / "groups.csv").write_text("well,barcode,group\nA1,AAAA,LB\nA2,,LB\n")
                for sample in samples:
                    with (reads / f"{sample}.fastq").open("w") as handle:
                        for i, barcode in enumerate(["AAAA"] * 4 + ["CCCC"] * 3):
                            seq = "TCATAGTGAGCTCAGCG" + barcode + "GTGCCCCACAAGAGGTT"
                            handle.write(f"@read{i}\n{seq}\n+\n" + "I" * len(seq) + "\n")
                config = run / "config.env"
                config.write_text('INPUT_DIR="input reads"\nOUTPUT_DIR="output files"\n'
                                  'BARCODE_GROUPS_CSV=groups.csv\nTHREADS=2\nEXPECTED_BARCODE_LEN=4\n'
                                  'COLLAPSE_BARCODES=false\nMAKE_PLOTS=false\n')
                commands = [[sys.executable, str(REPO / "run_pipeline.py"), "--config", str(config)]]
                if len(samples) == 1:
                    # Comparing ordered samples requires two; extraction also supports one.
                    commands = [[sys.executable, str(REPO / script), "--config", str(config)]
                                for script in ["bun_extract.py", "barcode_from_bun_csv.py"]]
                for command in commands:
                    result = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                output = run / "output files"
                with (output / "barcodes/additional_barcodes.csv").open() as handle:
                    extras = list(csv.DictReader(handle))
                self.assertEqual([row["barcode"] for row in extras], ["CCCC"])
                self.assertEqual(int(extras[0]["total_count"]), 3 * len(samples))
                if len(samples) > 1:
                    with (output / "analysis/retained_counts_matrix.csv").open() as handle:
                        counts = list(csv.DictReader(handle))
                    self.assertEqual({row["barcode"] for row in counts}, {"AAAA", "CCCC"})
                    self.assertTrue((output / "analysis/analysis_summary.txt").is_file())
                self.assertEqual(len(list((output / "bun_matches").glob("*_bun_matches.csv"))), len(samples))
                self.assertEqual({p.name for p in run.iterdir()}, {"input reads", "output files", "groups.csv", "config.env"})


if __name__ == "__main__":
    unittest.main()

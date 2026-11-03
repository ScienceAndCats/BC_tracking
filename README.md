# BC_tracking

A FASTA/FASTQ analysis toolkit for extracting barcodes between known flanking
sequences, quantifying diversity, and comparing barcode abundance across samples.

## Install

Create the Conda environment with all runtime dependencies, including Starcode:

```bash
conda env create -f environment.yml
conda activate BC_tracking
```

To update an existing environment after pulling changes:

```bash
conda env update -f environment.yml --prune
```

Alternatively, use Python 3.12 with `python -m pip install -r requirements.txt`
and install Starcode separately on your `PATH`. The Python dependencies are
Biopython, pandas, NumPy, matplotlib, PyYAML (for legacy configs), Plotly, and
python-dotenv. Starcode is required when barcode collapsing is enabled.

## Configure and run

Edit **`config.env`**. It contains only user-facing settings; output filenames,
report columns, pipeline order, and other fixed settings are defined in Python
(`env_config.py` and the analysis scripts).

The supplied config preserves the input/catalog paths and sample order from the
local example. Point those paths at your own files. The main settings look like:

```dotenv
INPUT_DIR=/path/to/fastq_files
OUTPUT_DIR=outputs
BARCODE_GROUPS_CSV=/path/to/02Nov2026_96barcodes.csv
THREADS=auto
UPSTREAM=TCATAGTGAGCTCAGCG
DOWNSTREAM=GTGCCCCACAAGAGGTT
EXPECTED_BARCODE_LEN=24
EXPLICIT_FILES=Initial_S254_R1_001.fastq.gz,16hr_S255_R1_001.fastq.gz,22hr_S256_R1_001.fastq.gz
```

All relative paths are resolved against the config file's folder. Quote paths
containing spaces or `#`. Leave `BARCODE_GROUPS_CSV=` empty to use per-barcode
colors without catalog matching. Leave `EXPLICIT_FILES=` empty for alphabetical
sample order, or list original FASTA/FASTQ filenames separated by commas. Names
must have distinct sample stems; do not use barcode-report CSV filenames.

Settings are read directly from the file: you do not need to source it or export
variables. Shell expressions and `${...}` are not expanded. Boolean values are
`true` or `false`; misspelled settings and invalid values produce an error.
Omitted settings use the defaults in `env_config.py`.

Run all three stages, or preview their commands:

```bash
python run_pipeline.py
python run_pipeline.py --dry-run
```

Use another config with `python run_pipeline.py --config /path/to/config.env`.
Every stage also reads the same config when run individually:

```bash
python bun_extract.py --config config.env
python barcode_from_bun_csv.py --config config.env
python ordered_barcode_sample_analysis.py config.env
```

The full pipeline always runs flank detection, barcode extraction, then ordered
analysis. Run a stage individually to reuse outputs from an earlier run. Legacy
YAML/JSON configs are still accepted through the same CLI arguments; their old
path and step-enable settings remain in effect. `config.env` replaces the shipped
`pipeline_config.yaml` as the default.

## Outputs

**All outputs from `config.env` are placed under `OUTPUT_DIR`.** Each stage uses
subfolders within that one root, so you only configure one output location:

```text
outputs/
  bun_matches/                 # Per-input flank matches and barcode membership
  barcodes/
    augmented/                 # Flank-match CSVs with extracted barcodes
    per_file_reports/          # Per-sample barcode counts and Starcode clusters
    barcode_file_summary.csv
    barcode_multi_file_membership.csv
    additional_barcodes.csv   # When a barcode catalog is supplied
  analysis/
    retained_counts_matrix.csv
    retained_frequency_matrix.csv
    retained_presence_matrix.csv
    all_barcode_ordered_sample_stats.csv
    barcode_filter_summary.csv
    plot_eligible_barcode_stats.csv
    sample_barcode_counts_summary.csv
    analysis_summary.txt
    plots/                     # All-barcode trajectories, heatmaps, scatter plots
    largest_increase_first_to_last/
    largest_decrease_first_to_last/
    highest_frequency_before/
    highest_frequency_after/   # Ranked tables, matrix subsets, and plots
```

The multi-file membership report is written for multiple inputs. Flank/barcode
extraction supports a single input; ordered comparison requires at least two
samples. Use a new `OUTPUT_DIR` for a different input dataset to avoid including
old per-sample reports left over from a previous dataset.

## Barcode groups and unmatched sequences

The catalog CSV must contain `barcode` and `group` columns. Additional columns,
such as `well`, are ignored:

```csv
well,barcode,group
A1,CCGTCTGAATCGCCTGGTGCGGTT,LB
A2,GGGGATGTGCTGGTTCGACTGCGT,LB
A3,,LB
B1,TACGTGGTCAGAGGGGTCGTGGGG,Spent SA
```

Blank/whitespace-only barcode rows are ignored. Matching trims whitespace and
ignores sequence case, but otherwise uses exact sequences (`N` is literal, not a
wildcard). Duplicate barcodes within a group are accepted. Conflicting groups or
nonempty barcodes without a group produce an error.

All trajectory line plots, including ranked plots, use consistent group colors
and group legends in both PNG and HTML. Unlisted barcodes use gray lines and
points at **50% opacity**, labeled "Not in barcode CSV".

`barcodes/additional_barcodes.csv` lists every nonempty extracted sequence absent
from the catalog. Columns are `barcode`, `barcode_len`, `total_count`, `num_files`,
and `files` (semicolon-separated file labels). Counts are exact observations
before length/count filtering and Starcode collapsing, so rare variants are
included even when they do not appear in plots. The report has only a header if
nothing is unmatched. Run the barcode extraction stage to refresh it; ordered
analysis alone does not rescan the reads.

## Interactive trajectories

With `MAKE_INTERACTIVE_TRAJECTORY_PLOTS=true`, each trajectory PNG has an HTML
file beside it. Open the HTML in a browser; Plotly is embedded and works offline.

- **Groups:** uncheck a group to hide all its trajectories, including gray
  backgrounds. This also works for "Not in barcode CSV". Select all / Hide all
  apply to groups only. This panel appears when a catalog is configured.
- **Barcodes:** uncheck an individual barcode to gray out its trajectory. Search
  filters the checkbox list without changing selections. Select all / Gray out
  all affect every barcode, even those hidden by search.
- **Samples:** uncheck a sample to gray out its points and adjacent segments.

These controls work together. Restoring a group preserves individual barcode and
sample selections; changing barcode selections does not re-enable hidden groups.
Group colors, the 50% opacity of unlisted barcodes, counts, and frequencies stay
unchanged. PNG exports are static.

## Analysis settings

`config.env` retains the tunable settings from the simplified config:

- **Flanks:** `UPSTREAM`, `DOWNSTREAM`, `MIN_MATCH`, and `PROGRESS_EVERY`.
- **Barcodes:** `EXPECTED_BARCODE_LEN`, `MIN_BARCODE_LEN`, `MAX_BARCODE_LEN`,
  `INCLUDE_EMPTY_BARCODES`, and `MIN_REAL_BARCODE_COUNT`.
- **Collapsing:** `COLLAPSE_BARCODES`, `STARCODE_PATH`, `STARCODE_DISTANCE`, and
  `STARCODE_CLUSTER_RATIO`. Starcode uses message passing and one thread per
  file, while `THREADS` controls file-level parallelism.
- **Ordering/filtering:** `EXPLICIT_FILES`, `USE_EXISTING_REAL_COLUMN`, and
  `TOP_N_FOR_EACH_RANKED_OUTPUT`.
- **Plots:** the `MAKE_*` switches, plot limits, heatmap settings, `LOG_SCALE_Y_AXIS`,
  and `DPI`. `TOP_N_TO_PLOT` defaults to 100.

Flank detection searches both orientations. R2 files are not treated as primary
samples; a paired R2 is used to verify the barcode extracted from R1.

Ordered analysis requires the expected barcode length, uses at least three reads
for presence, and retains barcodes present in at least one sample. The expected
length is shared with extraction through `EXPECTED_BARCODE_LEN`. Frequencies use
all barcode counts as the denominator; before/after comparisons use the first
and last samples. These fixed rules, report naming, and other removed settings
live in Python rather than the config.

**Every plot uses retained barcodes marked REAL in the first ordered sample.**
Real status in later samples does not restrict plots. This rule also applies
when `USE_EXISTING_REAL_COLUMN=false`. `REAL_BARCODE_SAMPLE` must remain `first`.
The first report must contain the real flag column. Analysis tables can include
barcodes real only in later samples; `barcode_filter_summary.csv` records plot
eligibility. Catalog membership changes styling, not these eligibility rules.

## Tests

```bash
python -m unittest discover -s tests -v
```

Browser tests additionally require `python -m pip install -r requirements-dev.txt`
and system Chromium (`chromium` on `PATH`); they are explicitly skipped if absent.
Tests cover group/barcode/sample selections, offline HTML, catalog matching,
unmatched-sequence reports, config parsing, single/multiple-input pipelines,
ordering, and real-barcode filtering.

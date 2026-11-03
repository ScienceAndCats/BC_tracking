"""Optional browser regression tests using Playwright and system Chromium."""

import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from interactive_trajectories import save_interactive_trajectory_plot
from barcode_groups import UNLISTED_COLOR, UNLISTED_LABEL, configure_barcode_groups

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright and shutil.which("chromium"), "Requires Playwright and system Chromium")
class InteractiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "trajectories.html"
        self.freqs = pd.DataFrame([[0.2, 0.1, 0.4], [0.1, 0.0, 0.05]],
                                  index=["AAAA", "CCCC"], columns=["first", "middle", "last"])
        self.cfg = {"pseudocount_for_log_plots": 1e-9, "log_scale_y_axis": True}
        self.context = self.browser.new_context(offline=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def open_plot(self):
        save_interactive_trajectory_plot(list(self.freqs.index), self.freqs, self.path, "Test trajectories", self.cfg)
        # Render the standalone document in memory; managed Chromium can block file:// navigation.
        self.page.set_content(self.path.read_text(), wait_until="load")
        self.page.wait_for_selector('.sample-list input[type="checkbox"]')

    def test_samples_gray_out_restore_and_preserve_values_offline(self):
        self.open_plot()
        self.assertEqual(self.page.locator('.sample-list input[type="checkbox"]').count(), 3)
        initial = self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[1].y)")
        self.assertAlmostEqual(initial[0], 0.2 + 1e-9)
        self.page.locator('.sample-list input[type="checkbox"]').nth(1).uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y[1] === null")
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[0].y)"), initial)
        self.assertEqual(self.page.evaluate("document.getElementById('barcode-trajectories').data[0].line.color"), "#b8b8b8")
        self.assertFalse(self.page.evaluate("document.getElementById('barcode-trajectories').data[1].connectgaps"))
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[1].customdata)"), [0.2, 0.1, 0.4])
        self.page.locator('.sample-list input[type="checkbox"]').nth(1).check()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y[1] !== null")
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[1].y)"), initial)
        self.page.locator('.sample-controls').get_by_role("button", name="Gray out all", exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y.every(v => v === null)")
        self.assertEqual(self.page.locator('.sample-list input:checked').count(), 0)
        self.page.locator('.sample-controls').get_by_role("button", name="Select all", exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y.every(v => v !== null)")
        self.assertEqual(self.page.locator('.sample-list input:checked').count(), 3)
        self.assertEqual(self.errors, [])

    def test_barcode_and_sample_selection_combine_without_resetting_each_other(self):
        self.open_plot()
        barcodes = self.page.locator('.barcode-list input[type="checkbox"]')
        self.assertEqual(barcodes.count(), 2)
        initial = self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[1].y)")
        self.page.locator('.sample-list input').nth(1).uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y[1] === null")
        barcodes.nth(0).uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y.every(v => v === null)")
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[0].y)"), initial)
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[3].y)"),
                         [0.1 + 1e-9, None, 0.05 + 1e-9])
        barcodes.nth(0).check()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y[0] !== null")
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[1].y)"),
                         [initial[0], None, initial[2]])
        barcodes.nth(1).uncheck()
        self.page.locator('.sample-controls').get_by_role("button", name="Select all", exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y[1] !== null")
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[1].y)"), initial)
        self.assertTrue(self.page.evaluate("document.getElementById('barcode-trajectories').data[3].y.every(v => v === null)"))
        self.assertEqual(self.page.locator('.barcode-controls .selection-status').inner_text(), '1 of 2 selected')
        self.assertEqual(self.errors, [])

    def test_barcode_search_preserves_selection_and_bulk_buttons_apply_to_all(self):
        self.open_plot()
        search = self.page.get_by_role('searchbox', name='Search barcodes')
        search.fill('aaaa')
        self.assertEqual(self.page.locator('.barcode-list label:visible').count(), 1)
        self.assertEqual(self.page.locator('.barcode-list label:visible').inner_text(), 'AAAA')
        self.assertEqual(self.page.locator('.barcode-list input:checked').count(), 2)
        self.page.locator('.barcode-list input').nth(0).uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y.every(v => v === null)")
        search.fill('CCCC')
        self.assertEqual(self.page.locator('.barcode-list label:visible').inner_text(), 'CCCC')
        self.page.locator('.barcode-controls').get_by_role('button', name='Select all', exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y.every(v => v !== null)")
        self.assertEqual(self.page.locator('.barcode-list input:checked').count(), 2)
        self.page.locator('.barcode-controls').get_by_role('button', name='Gray out all', exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data.filter((_, i) => i % 2 === 1).every(trace => trace.y.every(v => v === null))")
        self.assertEqual(self.page.locator('.barcode-list input:checked').count(), 0)
        search.fill('no matching barcode')
        self.assertEqual(self.page.locator('.barcode-list label:visible').count(), 0)
        search.fill('')
        self.assertEqual(self.page.locator('.barcode-list label:visible').count(), 2)
        self.assertEqual(self.page.locator('.sample-list input:checked').count(), 3)
        self.assertEqual(self.errors, [])

    def test_sample_labels_are_literal_and_linear_axis_is_supported(self):
        sample = "</script><script>window.labelExecuted=true</script>"
        self.freqs.columns = ["first", sample, "last"]
        self.freqs.index = [sample, "CCCC"]
        self.cfg["log_scale_y_axis"] = False
        self.open_plot()
        self.assertIn(sample, self.page.locator('.sample-list').inner_text())
        self.assertIn(sample, self.page.locator('.barcode-list').inner_text())
        self.assertIsNone(self.page.evaluate("window.labelExecuted"))
        self.assertEqual(self.page.evaluate("document.getElementById('barcode-trajectories').layout.yaxis.type"), "linear")
        self.assertEqual(self.errors, [])

    def test_group_legend_and_unlisted_opacity_survive_selection(self):
        catalog = Path(self.temp.name) / "groups.csv"
        catalog.write_text("well,barcode,group\nA1,AAAA,LB\nA2,,LB\nA3,GGGG,LB\n")
        self.cfg["barcode_groups_csv"] = str(catalog)
        configure_barcode_groups(self.cfg)
        self.freqs.loc["GGGG"] = [0.3, 0.4, 0.2]
        self.open_plot()
        legend = self.page.locator('.legend .legendtext')
        self.assertEqual(legend.all_text_contents(), ["LB", UNLISTED_LABEL])
        state = self.page.evaluate("""() => {
            const data = document.getElementById('barcode-trajectories').data;
            return {first: data[1].line.color, sameGroup: data[5].line.color,
                    unlisted: data[2].line.color, opacity: data[2].opacity,
                    overlay: Array.from(data[3].y)};
        }""")
        self.assertEqual(state['first'], state['sameGroup'])
        self.assertEqual(state['unlisted'], UNLISTED_COLOR)
        self.assertEqual(state['opacity'], 0.5)
        self.assertEqual(state['overlay'], [None, None, None])
        original = self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[2].y)")
        self.page.locator('.sample-list input').nth(1).uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y[1] === null")
        self.page.locator('.barcode-controls').get_by_role('button', name='Gray out all', exact=True).click()
        self.page.locator('.barcode-controls').get_by_role('button', name='Select all', exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[1].y[0] !== null")
        self.assertEqual(self.page.evaluate("Array.from(document.getElementById('barcode-trajectories').data[2].y)"), original)
        self.assertEqual(legend.all_text_contents(), ["LB", UNLISTED_LABEL])
        self.assertEqual(self.errors, [])

    def test_groups_hide_both_traces_and_preserve_barcode_and_sample_selections(self):
        catalog = Path(self.temp.name) / "groups.csv"
        catalog.write_text("barcode,group\nAAAA,LB\nGGGG,LB\nTTTT,Spent SA\n")
        self.cfg["barcode_groups_csv"] = str(catalog)
        configure_barcode_groups(self.cfg)
        self.freqs.loc["GGGG"] = [0.3, 0.4, 0.2]
        self.freqs.loc["TTTT"] = [0.2, 0.1, 0.1]
        self.open_plot()
        groups = self.page.locator('.group-list label')
        self.assertEqual(groups.all_text_contents(), ["LB", "Spent SA", UNLISTED_LABEL])
        self.page.locator('.sample-list input').nth(1).uncheck()
        self.page.locator('.barcode-list input').nth(0).uncheck()
        groups.filter(has_text="LB").locator('input').uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[0].visible === false")
        self.assertEqual(self.page.evaluate("[0,1,4,5].map(i => document.getElementById('barcode-trajectories').data[i].visible)"),
                         [False, False, False, False])
        self.assertTrue(self.page.evaluate("document.getElementById('barcode-trajectories').data[6].visible"))
        groups.filter(has_text="LB").locator('input').check()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[0].visible === true")
        self.assertTrue(self.page.evaluate("document.getElementById('barcode-trajectories').data[1].y.every(v => v === null)"))
        self.assertIsNone(self.page.evaluate("document.getElementById('barcode-trajectories').data[5].y[1]"))
        self.assertIsNotNone(self.page.evaluate("document.getElementById('barcode-trajectories').data[5].y[0]"))
        groups.filter(has_text=UNLISTED_LABEL).locator('input').uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[2].visible === false")
        self.assertFalse(self.page.evaluate("document.getElementById('barcode-trajectories').data[3].visible"))
        self.page.locator('.group-controls').get_by_role('button', name='Hide all', exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data.slice(0,8).every(t => t.visible === false)")
        self.page.locator('.group-controls').get_by_role('button', name='Select all', exact=True).click()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data.slice(0,8).every(t => t.visible === true)")
        self.assertEqual(self.page.locator('.group-controls .selection-status').inner_text(), '3 of 3 selected')
        self.assertEqual(self.page.locator('.barcode-list input:checked').count(), 3)
        self.assertEqual(self.page.locator('.sample-list input:checked').count(), 2)
        self.assertEqual(self.page.evaluate("document.getElementById('barcode-trajectories').data[2].opacity"), 0.5)
        self.assertEqual(self.errors, [])

    def test_group_names_are_literal_text(self):
        catalog = Path(self.temp.name) / "groups.csv"
        group = "</script><script>window.groupExecuted=true</script>"
        catalog.write_text(f"barcode,group\nAAAA,{group}\n")
        self.cfg["barcode_groups_csv"] = str(catalog)
        configure_barcode_groups(self.cfg)
        self.open_plot()
        self.assertIn(group, self.page.locator('.group-list').inner_text())
        self.assertIsNone(self.page.evaluate("window.groupExecuted"))
        self.page.locator('.group-list input').nth(0).uncheck()
        self.page.wait_for_function("document.getElementById('barcode-trajectories').data[0].visible === false")
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()

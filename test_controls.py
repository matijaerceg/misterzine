"""Feed compatibility: explicit zero, absent counts and curated precedence."""
import csv
import io
import unittest

import misterzine as mz


def mad(**values):
    fields = ["setname", "move_inputs", "special_controls", "num_buttons"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerow({"setname": "unit", **values})
    return mz.parse_mad(stream.getvalue())["unit"]


def web_row(curated, fallback):
    row = {key: "" for key in ["beta", "first_seen", "genre", "last_changed",
        "last_update", "manufacturer", "path", "rbf", "release_date", "setname",
        "source_id", "system", "title", "year"]}
    row.update(system="arcade", title="Unit", setname="unit", beta=False,
               source_id="distribution_mister", path="_Arcade/Unit.mra",
               rbf="unit", release_date="2026-09-01")
    return mz._web_row(row, arcade_mad={"unit": curated}, arcade_specs={"unit": fallback})


class ControlFeedTests(unittest.TestCase):
    def test_mad_zero_and_missing_are_distinct(self):
        zero = mad(move_inputs="4-way", num_buttons="0")
        missing = mad(move_inputs="4-way", num_buttons="")
        self.assertEqual(zero["buttons"], 0)
        self.assertEqual(zero["ctl"], "4-way · 0 buttons")
        self.assertNotIn("buttons", missing)
        self.assertEqual(missing["ctl"], "4-way")

    def test_special_controls_and_positive_count_survive(self):
        value = mad(special_controls="spinner", num_buttons="1")
        self.assertEqual(value, {"buttons": 1, "ctl": "1 button", "spc": "Spinner"})

    def test_mame_zero_missing_and_positive(self):
        specs = mz.parse_specs('''<game name="zero"><input players="1" control="joy4way" buttons="0"/></game>
            <game name="missing"><input control="joy4way"/></game>
            <game name="spinner"><input control="dial" buttons="1"/></game>''')
        self.assertEqual(specs["zero"]["buttons"], 0)
        self.assertEqual(specs["zero"]["ctl"], "4-way · 0 buttons")
        self.assertNotIn("buttons", specs["missing"])
        self.assertEqual(specs["spinner"]["spc"], "Dial")
        self.assertEqual(specs["spinner"]["buttons"], 1)

    def test_curated_zero_wins_over_provisional_positive(self):
        row = web_row(mad(move_inputs="4-way", num_buttons="0"), {"buttons": 2, "ctl": "8-way · 2 buttons"})
        self.assertEqual(row["buttons"], 0)
        self.assertEqual(row["ctl"], "4-way · 0 buttons")
        self.assertNotIn("buttons", row.get("prov", []))

    def test_provisional_zero_is_present_and_marked(self):
        row = web_row({}, {"buttons": 0, "ctl": "4-way · 0 buttons"})
        self.assertEqual(row["buttons"], 0)
        self.assertIn("buttons", row["prov"])
        self.assertIn("ctl", row["prov"])

    def test_old_cache_does_not_invent_zero(self):
        row = web_row({}, {"ctl": "4-way"})
        self.assertNotIn("buttons", row)

    def test_corrections_update_both_representations(self):
        row = mz.specs_for("nibbler", {"nibbler": {"ctl": "8-way · 2 buttons", "buttons": 2}}, {})
        self.assertEqual(row["buttons"], 0)
        self.assertEqual(row["ctl"], "4-way · 0 buttons")


if __name__ == "__main__":
    unittest.main()

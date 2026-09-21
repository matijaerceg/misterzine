"""Provisional feed contracts: precedence, provenance and conservative parsing."""
import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import misterzine as mz
from arcade_specs import merge_specs, parse_current_specs, parse_mra_specs


def row(curated=None, fallback=None, launch=None):
    catalog = dict.fromkeys(("beta", "first_seen", "genre", "last_changed",
        "last_update", "manufacturer", "path", "rbf", "release_date", "setname",
        "source_id", "system", "title", "year"), "")
    catalog.update(system="arcade", title="Unit", setname="unit", beta=False,
                   source_id="distribution_mister", path="_Arcade/Unit.mra",
                   rbf="unit", release_date="2026-09-01")
    return mz._web_row(catalog, arcade_mad={"unit": curated or {}},
        arcade_specs={"unit": fallback or {}}, mra_specs=launch or {})


def local_specs(legacy, current):
    """Run local_specs() over in-memory legacy/current MAME caches."""
    with tempfile.TemporaryDirectory() as tmp:
        old_gz, cur_gz = Path(tmp) / "old.gz", Path(tmp) / "cur.gz"
        old_gz.write_bytes(gzip.compress(json.dumps(legacy).encode("utf-8")))
        cur_gz.write_bytes(gzip.compress(json.dumps({"specs": current}).encode("utf-8")))
        with patch.object(mz, "SPECS_GZ", old_gz), \
             patch.object(mz, "CURRENT_SPECS_GZ", cur_gz), \
             patch.object(mz, "REVIEWED_SPECS_JSON", Path(tmp) / "absent.json"):
            return mz.local_specs()


class ArcadeSpecsTests(unittest.TestCase):
    def test_launch_mapping_slots_are_not_action_buttons(self):
        self.assertEqual(parse_mra_specs('<misterrom><buttons names="Fire,Coin,Start,Pause"/></misterrom>', "mra"), {})
        spec = parse_mra_specs('<misterrom><rotation>horizontal</rotation><num_buttons>0</num_buttons></misterrom>', "mra")
        self.assertEqual(spec, {"rot": "Horizontal", "buttons": 0, "_source": "mra"})

    def test_malformed_mra_comments_cannot_supply_metadata(self):
        xml = '<misterrom><!-- bad -- comment <num_buttons>9</num_buttons> --><num_buttons>2</num_buttons><rotation>vertical</rotation></misterrom>'
        spec = parse_mra_specs(xml, "mra")
        self.assertEqual(spec["buttons"], 2)
        self.assertEqual(spec["rot"], "Vertical")

    def test_unknown_launch_values_are_not_guessed(self):
        self.assertEqual(parse_mra_specs('<misterrom><num_buttons>unknown</num_buttons><rotation>90</rotation></misterrom>', "mra"), {})

    def test_launch_resolution_accepts_scan_classes_not_pixel_sizes(self):
        for raw, expected in (("15 kHz", "15kHz"), ("24kHz", "24kHz"), ("31KHz", "31kHz")):
            self.assertEqual(parse_mra_specs(f'<misterrom><resolution>{raw}</resolution></misterrom>', "mra")["res"], expected)
        self.assertEqual(parse_mra_specs('<misterrom><resolution>240x224</resolution></misterrom>', "mra"), {})

    def test_launch_count_including_coin_start_is_rejected(self):
        xml = '<misterrom><num_buttons>5</num_buttons><buttons names="Punch,Jab,Block,Start,Coin"/></misterrom>'
        self.assertNotIn("buttons", parse_mra_specs(xml, "mra"))

    def test_curated_controls_without_count_stay_unknown(self):
        result = row(curated={"ctl": "8-way"}, fallback={"ctl": "8-way · 9 buttons", "buttons": 9})
        self.assertNotIn("buttons", result)
        self.assertEqual(result["ctl"], "8-way")

    def test_current_mame_multiple_controls_and_no_resolution_inference(self):
        xml = b'''<mame><machine name="unit" sourcefile="sega/unit.cpp">
          <display type="raster" rotate="270" pixclock="28636362" htotal="910"/>
          <input players="2"><control type="joy" player="1" ways="8" buttons="1"/>
            <control type="positional" player="1"/><control type="joy" player="2" ways="8" buttons="1"/>
          </input></machine></mame>'''
        spec = parse_current_specs(io.BytesIO(xml), "mame0289")["unit"]
        self.assertEqual(spec["rot"], "Vertical")
        self.assertEqual(spec["plr"], "2")
        self.assertEqual(spec["ctl"], "8-way · 1 button")
        self.assertEqual(spec["spc"], "Rotary")
        self.assertNotIn("res", spec)
        self.assertIn("mame0289/src/mame/sega/unit.cpp", spec["_sources"]["ctl"])

    def test_missing_button_attribute_is_not_zero_and_mahjong_is_special(self):
        xml = b'''<mame><machine name="unit"><input players="1"><control type="mahjong" buttons="21"/></input></machine>
          <machine name="joy"><input players="1"><control type="joy" ways="4"/></input></machine>
          <machine name="zero"><input players="1"><control type="joy" ways="4" buttons="0"/></input></machine>
          <machine name="device" isdevice="yes"><input players="1"/></machine></mame>'''
        specs = parse_current_specs(io.BytesIO(xml), "mame0289")
        self.assertEqual(specs["unit"]["spc"], "Mahjong")
        self.assertNotIn("buttons", specs["unit"])
        self.assertNotIn("buttons", specs["joy"])
        self.assertEqual(specs["zero"]["buttons"], 0)
        self.assertNotIn("device", specs)

    def test_count_override_keeps_movement_and_both_sources(self):
        spec = merge_specs({"ctl": "8-way · 6 buttons", "buttons": 6, "_source": "mame"},
                           {"buttons": 4, "_source": "launch"})
        self.assertEqual(spec["ctl"], "8-way · 4 buttons")
        self.assertEqual(spec["buttons"], 4)
        self.assertEqual(spec["_sources"]["ctl"], "mame\nlaunch")
        self.assertEqual(spec["_sources"]["buttons"], "launch")

    def test_mra_identity_is_source_and_full_path(self):
        mras = {"distribution_mister": {"_Arcade/Unit.mra": {"buttons": 2, "_source": "right"}},
                "coinop": {"_Arcade/Unit.mra": {"buttons": 9, "_source": "wrong"}}}
        result = row(fallback={"ctl": "8-way · 6 buttons", "buttons": 6}, launch=mras)
        self.assertEqual(result["buttons"], 2)
        self.assertEqual(result["ctl"], "8-way · 2 buttons")
        self.assertEqual(result["prov_src"]["buttons"], "right")

    def test_mad_self_heals_every_field_and_clears_provenance(self):
        fallback = {"rot": "Vertical", "res": "15kHz", "plr": "4", "ctl": "8-way · 3 buttons",
                    "buttons": 3, "spc": "Dial", "_source": "fallback"}
        before = row(fallback=fallback)
        self.assertEqual(set(before["prov"]), {"rot", "res", "plr", "ctl", "buttons", "spc"})
        curated = {"rot": "Horizontal", "res": "31kHz", "plr": "1", "ctl": "4-way · 0 buttons", "buttons": 0, "spc": "Trackball"}
        after = row(curated=curated, fallback=fallback)
        for key, value in curated.items():
            self.assertEqual(after[key], value)
        self.assertNotIn("prov", after)
        self.assertNotIn("prov_src", after)

    def test_only_blank_fields_get_provenance(self):
        result = row(curated={"rot": "Horizontal"}, fallback={"rot": "Vertical", "res": "15kHz", "_source": "timing"})
        self.assertEqual(result["prov"], ["res"])
        self.assertEqual(result["prov_src"], {"res": "timing"})
        self.assertNotIn("flip", result)

    def test_reviewed_correction_wins_over_launch_button_count(self):
        result = row(fallback={"buttons": 6, "ctl": "8-way · 6 buttons",
                              "_reviewed": {"buttons": 4, "_source": "review"}},
                     launch={"distribution_mister": {"_Arcade/Unit.mra": {"buttons": 6}}})
        self.assertEqual(result["ctl"], "8-way · 4 buttons")
        self.assertEqual(result["prov_src"]["buttons"], "review")

    def test_reviewed_resolution_entries_are_explicit_and_sourced(self):
        groups = json.loads(mz.REVIEWED_SPECS_JSON.read_text(encoding="utf-8"))["groups"]
        resolutions = {sn for g in groups if "res" in g["values"] for sn in g["setnames"]}
        self.assertEqual(len(resolutions), 30)
        self.assertTrue(all(g["sources"] and g["evidence"] for g in groups))
        self.assertTrue(resolutions.isdisjoint({"cliffhgr", "elim2", "bonanza", "crkdown"}))

    def test_current_mame_rotation_beats_the_legacy_set_label(self):
        # 0.78 called spec2k horizontal; MAME has since separated Afega's
        # horizontal and vertical builds, and rotation is a hardware fact
        # rather than the input opinion legacy is kept on top for.
        merged = local_specs({"spec2k": {"rot": "Horizontal", "plr": "2"}},
                             {"spec2k": {"rot": "Vertical", "_sources": {"rot": "nmk16.cpp"}}})
        self.assertEqual(merged["spec2k"]["rot"], "Vertical")
        self.assertEqual(merged["spec2k"]["_sources"]["rot"], "nmk16.cpp")

    def test_legacy_rotation_still_fills_sets_current_mame_dropped(self):
        merged = local_specs({"gone": {"rot": "Vertical"}}, {})
        self.assertEqual(merged["gone"]["rot"], "Vertical")
        self.assertEqual(merged["gone"]["_sources"]["rot"], mz.SPECS_URL)

    def test_legacy_still_outranks_current_mame_on_control_descriptions(self):
        merged = local_specs({"unit": {"ctl": "4-way · 1 button", "buttons": 1}},
                             {"unit": {"rot": "Horizontal", "ctl": "8-way · 3 buttons", "buttons": 3}})
        self.assertEqual(merged["unit"]["ctl"], "4-way · 1 button")
        self.assertEqual(merged["unit"]["rot"], "Horizontal")


if __name__ == "__main__":
    unittest.main()

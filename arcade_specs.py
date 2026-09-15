"""Provisional arcade metadata. No network or database side effects on import."""
import re
import xml.etree.ElementTree as ET


FIELDS = ("rot", "res", "plr", "ctl", "spc", "buttons")


def merge_specs(*layers):
    """Merge low-to-high priority layers, keeping count/text and sources in sync."""
    out, sources = {}, {}
    for layer in layers:
        if not layer:
            continue
        for key in FIELDS:
            if key in layer:
                out[key] = layer[key]
                sources[key] = layer.get("_sources", {}).get(key, layer.get("_source", ""))
        if "_move" in layer:
            out["ctl"] = layer["_move"]
            sources["ctl"] = layer.get("_source", "")
        # A launch file may provide only an action-button count. Retain the
        # movement description from MAME, but replace its count in BOTH fields.
        if "buttons" in out:
            move = re.sub(r"(?:\s*·\s*)?\b\d+ buttons?$", "", out.get("ctl", "")).strip()
            n = out["buttons"]
            out["ctl"] = " · ".join(x for x in (move, f"{n} button" + ("" if n == 1 else "s")) if x)
            # ctl can be supported by separate movement and button sources.
            urls = [sources.get("ctl", ""), sources.get("buttons", "")]
            sources["ctl"] = "\n".join(dict.fromkeys(u for s in urls for u in s.splitlines() if u))
    out["_sources"] = sources
    return out


def parse_mra_specs(text, source):
    """Only explicit hardware metadata, never counts of gamepad mapping slots."""
    try:
        root = ET.fromstring(text)
        def value(tag):
            return (root.findtext(tag) or "").strip()
    except ET.ParseError:
        # Some shipped MRAs contain illegal '--' comments. Ignore comments
        # before extracting tags, so an example inside a comment cannot win.
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        def value(tag):
            match = re.search(r"<" + tag + r">\s*([^<]*?)\s*</" + tag + ">", text)
            return match.group(1).strip() if match else ""
    entry = {}
    rot = value("rotation").lower()
    if rot in ("horizontal", "vertical"):
        entry["rot"] = rot.title()
    resolution = value("resolution").replace(" ", "").lower()
    if resolution in ("15khz", "24khz", "31khz"):
        entry["res"] = resolution.replace("khz", "kHz")
    buttons = value("num_buttons")
    # Some MRAs count Coin/Start among num_buttons (e.g. Ring King). Such a
    # total is not an action-button count. Reject it instead of guessing a
    # subtraction from the gamepad mapping.
    mappings = re.search(r'<buttons\s[^>]*names="([^"]*)"', re.sub(r"<!--.*?-->", "", text, flags=re.S))
    system_slot = False
    if buttons.isdigit() and mappings:
        labels = mappings.group(1).split(",")[:int(buttons)]
        system_slot = any(re.search(r"\b(coin|start|pause|service|test|reset)\b", label, re.I) for label in labels)
    if buttons.isdigit() and not system_slot:
        entry["buttons"] = int(buttons)
    if entry:
        entry["_source"] = source
    return entry


def parse_current_specs(stream, release):
    """Read official MAME listxml; do NOT infer CRT class from its raster.

    MAME also reports synthesized/laserdisc presentation timings. Resolution
    must come from separately reviewed sources. Keep orientation coarse, as
    MAME's cabinet rotation is not proof of the FPGA core's boot direction.
    """
    special_names = {
        "dial": "Dial", "paddle": "Paddle", "pedal": "Pedal",
        "lightgun": "Lightgun", "trackball": "Trackball",
        "positional": "Rotary", "mahjong": "Mahjong", "hanafuda": "Hanafuda",
    }
    out = {}
    events = ET.iterparse(stream, events=("start", "end"))
    _, root = next(events)
    for event, machine in events:
        if event != "end" or machine.tag != "machine":
            continue
        if machine.get("isdevice") == "yes" or machine.get("runnable") == "no":
            root.clear()
            continue
        entry = {}
        rotations = {d.get("rotate") for d in machine.findall("display")}
        if rotations and rotations <= {"0", "180"}:
            entry["rot"] = "Horizontal"
        elif rotations and rotations <= {"90", "270"}:
            entry["rot"] = "Vertical"
        inp = machine.find("input")
        if inp is not None:
            players = inp.get("players", "")
            if players.isdigit() and int(players) > 0:
                entry["plr"] = players
            moves, specials, counts = [], [], []
            for control in inp.findall("control"):
                kind = control.get("type")
                ways = control.get("ways", "")
                if kind in ("joy", "doublejoy") and ways in ("2", "4", "8"):
                    moves.append(("Double " if kind == "doublejoy" else "") + ways + "-way")
                elif kind == "stick":
                    moves.append("Analog")
                if kind in special_names:
                    specials.append(special_names[kind])
                count = control.get("buttons", "")
                # Missing != zero: MAME can omit this attribute for no buttons.
                if count.isdigit() and kind not in ("mahjong", "hanafuda"):
                    counts.append(int(count))
            if moves:
                entry["_move"] = " / ".join(dict.fromkeys(moves))
            elif specials:
                entry["_move"] = ""
            if specials:
                entry["spc"] = " / ".join(dict.fromkeys(specials))
            if counts:
                entry["buttons"] = max(counts)
            if any(k in specials for k in ("Mahjong", "Hanafuda")):
                # Alternate joystick inputs in the emulator are not evidence
                # that the cabinet uses an ordinary joystick/button panel.
                entry["_move"] = ""
                entry.pop("buttons", None)
        if entry:
            source = machine.get("sourcefile", "")
            entry["_source"] = f"https://github.com/mamedev/mame/blob/{release}/src/mame/{source}"
            entry = merge_specs(entry)
            if machine.get("cloneof"):
                entry["_parent"] = machine.get("cloneof")
            out[machine.get("name").lower()] = entry
        root.clear()
    return out

"""
Anno 117 Map Template Editor - XML I/O

Reads and writes the plain-XML form of .a7tinfo map templates (after decompression / before compression by FileDBReader).
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement
from typing import Optional, Tuple, List
from models import IslandElement, MapTemplate


# ─── Campaign island size table ──────────────────────────────────────────────
# Fixed campaign islands omit <Size>/<IslandSize> in the XML.
# Key = island name stem after stripping the culture prefix (e.g. "roman_island_").
_CAMPAIGN_FIXED_SIZES: dict = {
    # Celtic / Albion campaign player islands
    "campaign_player_01":               "Large",
    "campaign_player_02":               "Large",
    "campaign_player_03":               "Medium",
    # Roman / Latium campaign player islands
    "campaign_starterisland_tarragon":  "Large",
    "campaign_starterisland_concordia": "Large",
}


def _campaign_fixed_size(map_file: str) -> Optional[str]:
    """Return the hardcoded size for a campaign fixed island, or None if unknown."""
    name = os.path.basename(map_file).replace(".a7m", "").lower()
    for pfx in ("roman_island_", "celtic_island_", "roman_", "celtic_"):
        if name.startswith(pfx):
            name = name[len(pfx):]
            break
    return _CAMPAIGN_FIXED_SIZES.get(name)


# ─── Type mapping (fixed islands) ───────────────────────────────────────────
# Maps internal island_type values to the id strings the game expects in
# RandomIslandConfig/value/Type/id for fixed islands.
# "Normal" is represented as an empty <Type/> element (no id child).
_FIXED_TYPE_XML: dict[str, str] = {
    "Pirate":     "PirateIsland",
    "ThirdParty": "ThirdParty",
    "Starter":    "Starter",
    # Vulcan: fixed Vulcan islands use <Type /> (empty) - game identifies them by file path.
    # Continental: no Type id needed (DLC island identified by TypePerConstructionArea)
}


# ─── Helpers ────────────────────────────────────────────────────────────────

def _int_list(text: Optional[str]) -> List[int]:
    if not text or not text.strip():
        return []
    return [int(v) for v in text.split()]


def _text(elem: Optional[Element], default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _find_text(parent: Element, path: str, default: str = "") -> str:
    e = parent.find(path)
    return _text(e, default)


# ─── Reading ─────────────────────────────────────────────────────────────────

def load_xml(filepath: str, region: str = "Latium") -> MapTemplate:
    """Parse a plain-XML map template file and return a MapTemplate."""
    tree = ET.parse(filepath)
    root = tree.getroot()

    # <Content><MapTemplate> or just <MapTemplate>
    mt = root.find(".//MapTemplate")
    if mt is None:
        raise ValueError("No <MapTemplate> element found in file.")

    # ── header ───────────────────────────────────────────────────────────────
    size_vals   = _int_list(_find_text(mt, "Size"))
    pa_vals     = _int_list(_find_text(mt, "PlayableArea"))
    ipa_vals    = _int_list(_find_text(mt, "InitialPlayableArea"))
    enlarge_off = _int_list(_find_text(mt, "EnlargementOffset", "0 0"))
    is_enlarged = _find_text(mt, "IsEnlargedTemplate", "False").lower() == "true"

    size: Tuple[int, int] = (size_vals[0], size_vals[1]) if len(size_vals) >= 2 else (2048, 2048)
    pa: Tuple[int, int, int, int] = tuple(pa_vals[:4]) if len(pa_vals) >= 4 else (20, 20, *size)  # type: ignore
    ipa: Tuple[int, int, int, int] = tuple(ipa_vals[:4]) if len(ipa_vals) >= 4 else pa            # type: ignore
    e_off: Tuple[int, int] = (enlarge_off[0], enlarge_off[1]) if len(enlarge_off) >= 2 else (0, 0)

    template = MapTemplate(
        region=region,
        size=size,
        playable_area=pa,
        initial_playable_area=ipa,
        is_enlarged=is_enlarged,
        enlargement_offset=e_off,
        source_path=filepath,
    )

    # ── elements ─────────────────────────────────────────────────────────────
    for te in mt.findall("TemplateElement"):
        elem = te.find("Element")
        if elem is None:
            continue

        # ElementType (absent for fixed islands)
        etype_e = te.find("ElementType")
        if etype_e is not None and etype_e.text is not None:
            etype = int(etype_e.text.strip())
        else:
            etype = 0  # fixed island

        # Position
        pos_vals = _int_list(_find_text(elem, "Position"))
        position: Tuple[int, int] = (pos_vals[0], pos_vals[1]) if len(pos_vals) >= 2 else (0, 0)

        # Locked
        locked = _find_text(elem, "Locked", "False").lower() == "true"

        if etype == 2:
            # Ship spawn - only position matters
            isl = IslandElement(position=position, element_type=2, locked=locked)
            template.add_element(isl)
            continue

        # Fixed-island fields (needed early for type/size fallback logic)
        map_file = _find_text(elem, "MapFilePath")

        # Island type
        # Fixed islands store their type in RandomIslandConfig; random islands use Config/Type/id
        if map_file:
            ric_type = _find_text(elem, "RandomIslandConfig/value/Type/id")
            type_id  = ric_type if ric_type else "Normal"
            # Normalise game name to internal name
            if type_id == "PirateIsland":
                type_id = "Pirate"
            # Fixed Vulcan islands export <Type /> (empty) because the game identifies them by file path, not by the Type id.  Infer Vulcan from the path so the editor still shows the correct colour after a save/reload cycle.
            # DLC01 path + no TypePerConstructionArea → Vulcan (Continental has TypePerConstructionArea).
            if type_id == "Normal" and "dlc01" in map_file.lower():
                if elem.find("RandomIslandConfig/value/TypePerConstructionArea") is None:
                    type_id = "Vulcan"
        else:
            type_id = _find_text(elem, "Config/Type/id") or "Normal"

        # Size (random islands use <Size>; fixed use <IslandSize><value><id>)
        size_text = _find_text(elem, "Size")
        if not size_text:
            size_text = _find_text(elem, "IslandSize/value/id")
        if size_text:
            size_str = size_text
        elif type_id == "Starter":
            size_str = "Large" # campaign/pool starter islands omit the size tag
        elif map_file:
            size_str = _campaign_fixed_size(map_file) or "Small"
        else:
            size_str = "Small"
        island_label = _find_text(elem, "IslandLabel")
        rot_text = _find_text(elem, "Rotation90")
        rotation = int(rot_text) if rot_text else 0

        # Fertility GUIDs
        fert_text = _find_text(elem, "FertilityGuids")
        fert_guids = _int_list(fert_text)
        rand_fert_text = _find_text(elem, "RandomizeFertilities", "1")
        rand_fert = rand_fert_text not in ("0", "False", "false")

        isl = IslandElement(
            position=position,
            size=size_str,
            island_type=type_id,
            element_type=etype,
            locked=locked,
            map_file_path=map_file if map_file else None,
            island_label=island_label if island_label else None,
            rotation90=rotation,
            fertility_guids=fert_guids,
            randomize_fertilities=rand_fert,
        )
        template.add_element(isl)

    template.modified = False
    return template


# ─── Writing ─────────────────────────────────────────────────────────────────

def _sub(parent: Element, tag: str, text: str = "") -> Element:
    e = SubElement(parent, tag)
    if text:
        e.text = text
    return e


def _indent(elem: Element, level: int = 0) -> None:
    """Add pretty-print indentation in-place (stdlib ET doesn't do this)."""
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


def save_xml(template: MapTemplate, filepath: str) -> None:
    """Serialise a MapTemplate to a plain-XML file ready for FileDBReader compress."""
    root = Element("Content")
    mt = SubElement(root, "MapTemplate")

    _sub(mt, "Size", f"{template.size[0]} {template.size[1]}")
    # EnlargementOffset is a Latium-only field - never write it for Albion.
    # For Latium only write it when the template actually uses enlargement (is_enlarged flag set) or when the imported file already had a non-zero offset.
    if template.region == "Latium" and template.is_enlarged:
        _sub(mt, "EnlargementOffset",
             f"{template.enlargement_offset[0]} {template.enlargement_offset[1]}")

    pa = template.playable_area
    _sub(mt, "PlayableArea", f"{pa[0]} {pa[1]} {pa[2]} {pa[3]}")

    # InitialPlayableArea is derived from PlayableArea via the model property, ensuring it stays consistent regardless of how the template was created.
    ipa = template.computed_initial_pa
    _sub(mt, "InitialPlayableArea", f"{ipa[0]} {ipa[1]} {ipa[2]} {ipa[3]}")

    if template.is_enlarged:
        _sub(mt, "IsEnlargedTemplate", "True")

    SubElement(mt, "RandomlyPlacedThirdParties")
    _sub(mt, "ElementCount", str(len(template.elements)))

    # Write non-spawn elements first, spawn points last - matches vanilla ordering.
    for isl in sorted(template.elements, key=lambda e: e.is_ship_spawn):
        _write_element(mt, isl, write_locked=template.is_enlarged)

    _indent(root)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")  # Python ≥ 3.9
    with open(filepath, "w", encoding="utf-8") as fh:
        tree.write(fh, encoding="unicode")

    template.source_path = filepath
    template.modified = False


def _write_element(mt: Element, isl: IslandElement, write_locked: bool = True) -> None:
    te = SubElement(mt, "TemplateElement")

    if isl.is_ship_spawn:
        _sub(te, "ElementType", "2")
        elem = SubElement(te, "Element")
        pos = isl.position
        _sub(elem, "Position", f"{pos[0]} {pos[1]}")
        if isl.locked and write_locked:
            _sub(elem, "Locked", "True")
        return

    if not isl.is_fixed:
        _sub(te, "ElementType", "1")

    elem = SubElement(te, "Element")
    pos = isl.position
    _sub(elem, "Position", f"{pos[0]} {pos[1]}")

    if isl.locked and write_locked:
        _sub(elem, "Locked", "True")

    if isl.is_fixed and isl.map_file_path:
        # Fixed island
        _sub(elem, "MapFilePath", isl.map_file_path)
        _sub(elem, "Rotation90", str(isl.rotation90))
        if isl.island_label:
            _sub(elem, "IslandLabel", isl.island_label)

        fert_e = SubElement(elem, "FertilityGuids")
        if isl.fertility_guids:
            fert_e.text = " ".join(str(g) for g in isl.fertility_guids)
        # Write RandomizeFertilities only when the user explicitly disabled it (i.e. chose specific fertility GUIDs).  Omitting the tag lets the game default to randomisation; writing 0 locks in the chosen fertilities.
        if not isl.randomize_fertilities:
            _sub(elem, "RandomizeFertilities", "0")
        if isl.size == "Continental":
            SubElement(elem, "FertilitiesPerAreaIndex")
        SubElement(elem, "MineSlotActivation")

        # RandomIslandConfig - structure matches the game's expected format
        ric = SubElement(elem, "RandomIslandConfig")
        val = SubElement(ric, "value")
        typ = SubElement(val, "Type")
        xml_type_id = _FIXED_TYPE_XML.get(isl.island_type, "")
        # Continental islands are identified by TypePerConstructionArea, not by Type/id
        if xml_type_id and isl.size != "Continental":
            _sub(typ, "id", xml_type_id)
        diff = SubElement(val, "Difficulty")
        _sub(diff, "id", "Normal")
        # TypePerConstructionArea is only needed for Continental islands (DLC).
        # Built via ET.fromstring to guarantee the alternating index/<value> sibling
        # structure survives the indentation pass without corruption.
        if isl.size == "Continental":
            tpca = ET.fromstring(
                "<TypePerConstructionArea>"
                "<None>0</None><None><value><id>0</id></value></None>"
                "<None>1</None><None><value><id>0</id></value></None>"
                "<None>2</None><None><value><id>0</id></value></None>"
                "</TypePerConstructionArea>"
            )
            val.append(tpca)

        SubElement(elem, "FertilitySetGUIDs")

        # IslandSize
        isz = SubElement(elem, "IslandSize")
        isz_v = SubElement(isz, "value")
        _sub(isz_v, "id", isl.size)
    else:
        # Random island - match vanilla format exactly.
        # <Size> is omitted for Small (game default); written for all other sizes.
        if isl.size != "Small":
            _sub(elem, "Size", isl.size)
        SubElement(elem, "Difficulty")
        cfg = SubElement(elem, "Config")
        typ = SubElement(cfg, "Type")
        if isl.island_type and isl.island_type != "Normal":
            _sub(typ, "id", isl.island_type)
        SubElement(cfg, "Difficulty")

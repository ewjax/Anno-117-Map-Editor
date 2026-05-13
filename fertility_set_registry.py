"""
Anno 117 Map Template Editor - Fertility Set Registry

Parses FertilitySet and FertilityPool assets from assets.xml to resolve
automatic fertility assignments for fixed islands with randomize_fertilities=True.

IMPORTANT: This logic is ONLY needed for fixed islands with randomize_fertilities=True.
  • Random (pool) islands get their fertilities assigned by the game engine.
  • Fixed islands with explicit fertility_guids already set are written as-is.
Resolution happens at export time; the editor keeps the island in "random" state
internally and shows an indicator in the canvas label.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set

import config

# ─── Mappings ────────────────────────────────────────────────────────────────

_REGION_MAP = {
    "Roman":  "Latium",
    "Celtic": "Albion",
}

# Only Normal and Starter have FertilitySets in the game assets.
# ThirdParty / Pirate / Vulcan fixed islands must use explicit GUIDs.
_ISLAND_TYPE_MAP = {
    "Normal":  "Normal",
    "Starter": "Starter",
}


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class FertilitySetAsset:
    guid:            int
    name:            str
    island_type:     str           # "Normal" or "Starter"
    region:          str           # "Latium" or "Albion"
    difficulty:      str           # "easy" / "medium" / "hard"
    variant:         str           # "" for Starter; "2nd" or "3rd" for Normal
    fertility_guids: List[int] = field(default_factory=list)


@dataclass
class FertilityPoolAsset:
    guid:            int
    fertility_guids: List[int] = field(default_factory=list)


# ─── Registry ────────────────────────────────────────────────────────────────

class FertilitySetRegistry:
    """
    Singleton registry for FertilitySet and FertilityPool assets.
    Call FertilitySetRegistry.instance().load() after assets.xml is available.
    """

    _instance: Optional["FertilitySetRegistry"] = None

    def __init__(self):
        self._sets:   List[FertilitySetAsset]       = []
        self._pools:  Dict[int, FertilityPoolAsset] = {}
        self._loaded: bool = False

    @classmethod
    def instance(cls) -> "FertilitySetRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, force: bool = False) -> bool:
        """
        Parse assets.xml and build the registry.
        Returns True on success, False if assets.xml is missing or unparseable.
        """
        if self._loaded and not force:
            return True

        assets_path = config.ASSETS_XML
        if not os.path.isfile(assets_path):
            print(f"[fertility_set] assets.xml not found at {assets_path}")
            return False

        try:
            tree = ET.parse(assets_path)
            root = tree.getroot()
        except Exception as exc:
            print(f"[fertility_set] Failed to parse assets.xml: {exc}")
            return False

        pool_count = set_count = 0

        for asset in root.iter("Asset"):
            template_el = asset.find("Template")
            if template_el is None or not template_el.text:
                continue
            template = template_el.text.strip()

            # ── FertilityPool ─────────────────────────────────────────────────
            if template == "FertilityPool":
                guid_el = asset.find("Values/Standard/GUID")
                if guid_el is None or not guid_el.text:
                    continue
                guid = int(guid_el.text.strip())
                guids: List[int] = []
                for item in asset.findall("Values/FertilityPool/FertilityList/Item"):
                    f_el = item.find("Fertility")
                    if f_el is not None and f_el.text:
                        guids.append(int(f_el.text.strip()))
                self._pools[guid] = FertilityPoolAsset(guid=guid, fertility_guids=guids)
                pool_count += 1

            # ── FertilitySet ──────────────────────────────────────────────────
            elif template == "FertilitySet":
                guid_el = asset.find("Values/Standard/GUID")
                name_el = asset.find("Values/Standard/Name")
                if guid_el is None or not guid_el.text:
                    continue
                guid = int(guid_el.text.strip())
                name = name_el.text.strip() if name_el is not None and name_el.text else ""

                # Region - required; skip if absent or unrecognised
                region_el = asset.find("Values/ResourceSetCondition/AllowedRegion")
                if region_el is None or not region_el.text:
                    continue
                region = _REGION_MAP.get(region_el.text.strip())
                if region is None:
                    continue

                # Island type - required; skip if absent or unrecognised
                itype_el = asset.find("Values/ResourceSetCondition/AllowedIslandType")
                if itype_el is None or not itype_el.text:
                    continue
                island_type = _ISLAND_TYPE_MAP.get(itype_el.text.strip())
                if island_type is None:
                    continue

                # Difficulty from Name keyword (easy / medium / hard)
                name_l = name.lower()
                if "easy" in name_l:
                    difficulty = "easy"
                elif "hard" in name_l:
                    difficulty = "hard"
                elif "medium" in name_l:
                    difficulty = "medium"
                else:
                    continue  # no difficulty keyword → skip

                # Variant for Normal islands: 2nd or 3rd island set
                if island_type == "Normal":
                    if "2nd" in name_l or "second" in name_l:
                        variant = "2nd"
                    elif "3rd" in name_l or "third" in name_l:
                        variant = "3rd"
                    else:
                        continue  # Normal set without island-variant keyword → skip
                else:
                    variant = ""   # Starter has no variant

                # Collect fertility GUIDs listed in this set
                fert_guids: List[int] = []
                for item in asset.findall("Values/FertilitySet/Fertilities/Item"):
                    f_el = item.find("Fertility")
                    if f_el is not None and f_el.text:
                        fert_guids.append(int(f_el.text.strip()))

                self._sets.append(FertilitySetAsset(
                    guid=guid, name=name,
                    island_type=island_type, region=region,
                    difficulty=difficulty, variant=variant,
                    fertility_guids=fert_guids,
                ))
                set_count += 1

        self._loaded = True
        print(f"[fertility_set] Loaded {set_count} FertilitySets, {pool_count} FertilityPools.")
        return True

    # ── Resolution ───────────────────────────────────────────────────────────

    def resolve_fertilities(
        self,
        island_type: str,   # "Normal" or "Starter"
        difficulty:  str,   # "easy" / "medium" / "hard"
        region:      str,   # "Latium" / "Albion"
    ) -> List[int]:
        """
        Return a resolved list of concrete fertility GUIDs for one fixed island.

        Starter islands: picks the matching FertilitySet directly.
        Normal islands:  50/50 randomly picks between the "2nd island" and "3rd island" FertilitySets - re-drawn on every call.

        Any GUID in the chosen set that belongs to a FertilityPool is expanded
        by drawing one entry from that pool at random, without duplicates across
        the final result.  If a pool is exhausted (all entries already selected),
        it redraws from the full pool ignoring the no-duplicate constraint.

        Returns [] if no matching set is found (caller should warn the user).
        """
        candidates = [
            s for s in self._sets
            if s.island_type == island_type
            and s.difficulty  == difficulty
            and s.region      == region
        ]
        if not candidates:
            return []

        if island_type == "Starter":
            chosen_set = candidates[0]
        else:
            # Separate 2nd- and 3rd-island sets, then 50/50 pick one group
            second = [s for s in candidates if s.variant == "2nd"]
            third  = [s for s in candidates if s.variant == "3rd"]
            choices: List[FertilitySetAsset] = []
            if second:
                choices.append(random.choice(second))
            if third:
                choices.append(random.choice(third))
            if not choices:
                return []
            chosen_set = random.choice(choices)

        # Resolve GUIDs - expand FertilityPool GUIDs; no duplicate concrete GUIDs
        result: List[int] = []
        used:   Set[int]  = set()

        for guid in chosen_set.fertility_guids:
            if guid in self._pools:
                pool_guids = self._pools[guid].fertility_guids
                available  = [g for g in pool_guids if g not in used]
                if not available:
                    # Pool exhausted - skip slot rather than introduce a duplicate
                    continue
                drawn = random.choice(available)
                result.append(drawn)
                used.add(drawn)
            else:
                # Direct concrete fertility GUID
                if guid not in used:
                    result.append(guid)
                    used.add(guid)

        return result

    def supports_type(self, island_type: str) -> bool:
        """Return True if we have any FertilitySets for this island type."""
        return any(s.island_type == island_type for s in self._sets)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

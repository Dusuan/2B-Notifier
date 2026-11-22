#!/usr/bin/env python3
"""
Genera data/game_data.json (datos estáticos compactos de Clash of Clans) a partir del
dataset comunitario chiefpansancolt/clash-of-clans-data, fijado a un commit concreto.

Uso (después de cada actualización del juego):
    python tools/build_game_data.py                 # usa el commit fijado abajo
    python tools/build_game_data.py --ref main      # usa la última versión del dataset

Formato de salida:
{
  "source": {...},
  "hero_hall_th": {"1": 7, ...},     # nivel de Hero Hall -> TH requerido
  "blacksmith_th": {"1": 8, ...},    # nivel de Blacksmith -> TH requerido
  "units": {
    "<nombre normalizado>": {
      "name": "Barbarian King", "category": "heroes",
      "levels": [[nivel, th_requerido, costo, recurso, segundos], ...]
    }
  }
}
"""
import argparse
import json
import re
import sys
from pathlib import Path

import requests

REPO = "chiefpansancolt/clash-of-clans-data"
PINNED_REF = "7afaa0375e5865c04021836a3a4192ffcfea092d"  # 2026-11-06 (incluye balance de oct-2026)
RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"
TREE = "https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"

# carpeta del dataset -> categoría interna
CATEGORIES = {
    "heroes": "heroes",
    "troops": "troops",
    "spells": "spells",
    "pets": "pets",
    "siege-machines": "siege",
    "hero-equipment": "equipment",
}

OUT = Path(__file__).resolve().parent.parent / "data" / "game_data.json"


def norm(name: str) -> str:
    """Normaliza nombres para casar API oficial <-> dataset (ej. 'P.E.K.K.A' -> 'pekka')."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def seconds(t) -> int:
    if not isinstance(t, dict):
        return 0
    return t.get("days", 0) * 86400 + t.get("hours", 0) * 3600 + t.get("minutes", 0) * 60 + t.get("seconds", 0)


def fetch_json(ref: str, path: str):
    r = requests.get(RAW.format(repo=REPO, ref=ref, path=path), timeout=20)
    r.raise_for_status()
    return r.json()


def building_th_map(ref: str, path: str) -> dict:
    data = fetch_json(ref, path)
    return {str(lv["level"]): lv["townHallRequired"] for lv in data["levels"]}


def compact_levels(category: str, data: dict, hero_hall_th: dict, blacksmith_th: dict) -> list:
    rows = []
    for lv in data.get("levels", []):
        level = lv["level"]
        if category == "heroes":
            th = hero_hall_th.get(str(lv.get("heroHallLevelRequired", 1)), 99)
            cost, res, secs = lv.get("upgradeCost", 0), lv.get("upgradeCostResource", ""), seconds(lv.get("upgradeTime"))
        elif category == "equipment":
            th = blacksmith_th.get(str(lv.get("blacksmithLevelRequired", 1)), 99)
            ores = {k: lv.get(f"upgrade{k}", 0) for k in ("ShinyOre", "GlowingOre", "StarryOre")}
            cost, res, secs = ores, "Ore", 0
        elif category == "pets":
            th = lv.get("townHallRequired", 99)
            cost, res, secs = lv.get("upgradeCost", 0), lv.get("upgradeCostResource", ""), seconds(lv.get("upgradeTime"))
        else:  # troops, spells, siege
            th = lv.get("townHallRequired", 99)
            cost, res, secs = lv.get("researchCost", 0), lv.get("researchCostResource", ""), seconds(lv.get("researchTime"))
        rows.append([level, th, cost, res, secs])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=PINNED_REF, help="commit/branch del dataset")
    args = ap.parse_args()

    tree = requests.get(TREE.format(repo=REPO, ref=args.ref), timeout=20)
    tree.raise_for_status()
    paths = [t["path"] for t in tree.json()["tree"] if t["path"].endswith(".json")]

    hero_hall_th = building_th_map(args.ref, "data/home/army-buildings/hero-hall.json")
    blacksmith_th = building_th_map(args.ref, "data/home/army-buildings/blacksmith.json")

    units = {}
    for folder, category in CATEGORIES.items():
        prefix = f"data/home/{folder}/"
        for path in sorted(p for p in paths if p.startswith(prefix) and p.count("/") == 3):
            data = fetch_json(args.ref, path)
            units[norm(data["name"])] = {
                "name": data["name"],
                "category": category,
                "levels": compact_levels(category, data, hero_hall_th, blacksmith_th),
            }
            print(f"  {category:<10} {data['name']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": {"repo": f"https://github.com/{REPO}", "ref": args.ref},
        "hero_hall_th": hero_hall_th,
        "blacksmith_th": blacksmith_th,
        "units": units,
    }, ensure_ascii=False, separators=(",", ":")))
    print(f"OK: {len(units)} unidades -> {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

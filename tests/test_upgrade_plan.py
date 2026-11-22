"""Pruebas del calculador determinista. Ejecutar: python -m unittest discover -s tests"""
import unittest
from agent.upgrade_plan import build_plan, cap_for_th, remaining, load_game_data

# Datos sintéticos: [nivel, th_requerido, costo, recurso, segundos]
LEVELS = [[1, 1, 0, "Elixir", 0], [2, 3, 100, "Elixir", 3600], [3, 5, 200, "Elixir", 7200], [4, 7, 400, "Elixir", 86400]]

RULES = {
    "category_order": {"farming": ["heroes", "troops", "spells"], "war": ["spells", "troops", "heroes"]},
    "queues": {"hero_hall": ["heroes"], "laboratory": ["troops", "spells"]},
    "focus_units": [],
    "next_th": {"heroes_must_be_maxed": True, "min_offense_completion_pct": 85},
    "max_items": 8,
}


class TestHelpers(unittest.TestCase):
    def test_cap_for_th(self):
        self.assertEqual(cap_for_th(LEVELS, 1), 1)
        self.assertEqual(cap_for_th(LEVELS, 4), 2)
        self.assertEqual(cap_for_th(LEVELS, 7), 4)
        self.assertEqual(cap_for_th(LEVELS, 99), 4)

    def test_remaining_sums_only_pending_levels(self):
        cost, secs = remaining(LEVELS, current=1, cap=3)
        self.assertEqual(cost, {"Elixir": 300})
        self.assertEqual(secs, 3600 + 7200)

    def test_remaining_ores(self):
        lv = [[1, 8, {"ShinyOre": 0}, "Ore", 0], [2, 8, {"ShinyOre": 120, "GlowingOre": 0}, "Ore", 0]]
        cost, _ = remaining(lv, 1, 2)
        self.assertEqual(cost, {"ShinyOre": 120})


class TestBuildPlanRealData(unittest.TestCase):
    """Usa data/game_data.json real para verificar el casado de nombres y topes."""

    def _player(self, th, king, barb, rage, village_extra=()):
        return {
            "townHallLevel": th,
            "heroes": [{"name": "Barbarian King", "level": king, "village": "home"},
                       {"name": "Battle Machine", "level": 5, "village": "builderBase"}],
            "troops": [{"name": "Barbarian", "level": barb, "village": "home"}, *village_extra],
            "spells": [{"name": "Rage Spell", "level": rage, "village": "home"}],
            "heroEquipment": [],
        }

    def test_maxed_account_is_ready(self):
        units = load_game_data()["units"]
        th = 12
        caps = {k: cap_for_th(units[k]["levels"], th) for k in ("barbarianking", "barbarian", "ragespell")}
        plan = build_plan(self._player(th, caps["barbarianking"], caps["barbarian"], caps["ragespell"]), "farming", RULES)
        self.assertEqual(plan["top_priorities"], [])
        self.assertTrue(plan["ready_for_next_th"])
        self.assertEqual(plan["completion_pct"]["heroes"], 100)

    def test_underleveled_hero_blocks_next_th_and_comes_first(self):
        units = load_game_data()["units"]
        th = 12
        barb_cap = cap_for_th(units["barbarian"]["levels"], th)
        rage_cap = cap_for_th(units["ragespell"]["levels"], th)
        plan = build_plan(self._player(th, 10, barb_cap - 1, rage_cap), "farming", RULES)
        self.assertFalse(plan["ready_for_next_th"])
        self.assertTrue(any("Barbarian King" in b for b in plan["blockers"]))
        self.assertEqual(plan["top_priorities"][0]["name"], "Barbarian King")
        self.assertIn("Barbarian", plan["next_per_queue"]["laboratory"])
        # builder base y unidades desconocidas no se planifican como aldea principal
        self.assertNotIn("Battle Machine", [e["name"] for e in plan["top_priorities"]])

    def test_play_style_changes_order(self):
        units = load_game_data()["units"]
        th = 12
        plan = build_plan(self._player(th, 10, 1, 1), "war", RULES)
        self.assertEqual(plan["top_priorities"][0]["category"], "spells")

    def test_unknown_units_reported(self):
        extra = ({"name": "Super Barbarian", "level": 1, "village": "home"},)
        plan = build_plan(self._player(12, 10, 1, 1, extra), "farming", RULES)
        self.assertIn("Super Barbarian", plan["unplanned_units"])

    def test_level_above_cap_is_clamped(self):
        plan = build_plan(self._player(3, 99, 99, 99), "farming", RULES)
        self.assertTrue(all(v <= 100 for v in plan["completion_pct"].values()))


class TestTelegramSplit(unittest.TestCase):
    def test_split_respects_limit(self):
        from bot.telegram_bot import split_message
        text = "\n".join("x" * 100 for _ in range(100))
        chunks = split_message(text, limit=1000)
        self.assertTrue(all(len(c) <= 1000 for c in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), text.replace("\n", ""))


if __name__ == "__main__":
    unittest.main()

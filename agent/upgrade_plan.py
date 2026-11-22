"""
Calculador determinista de mejoras (sin LLM).

Reglas (configurables en agent/priorities.json):
1. Tope por TH: el nivel máximo de cada unidad es el mayor nivel cuyo TH requerido <= TH del jugador
   (héroes vía Hero Hall, equipo vía Blacksmith, según data/game_data.json).
2. Mantener cada cola ocupada: se sugiere la siguiente mejora por cola (Hero Hall, Laboratorio,
   Pet House, Blacksmith). Dentro de una cola gana la unidad más atrasada (menor nivel/tope);
   las unidades en "focus_units" van primero.
3. Ranking global: orden de categorías según el estilo de juego, luego la más atrasada.
4. "¿Listo para el siguiente TH?": héroes al tope (si la regla está activa) y ofensiva
   (tropas+hechizos+máquinas+mascotas) >= min_offense_completion_pct.
Limitación: la API oficial no expone niveles de edificios/defensas/muros.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME_DATA = ROOT / "data" / "game_data.json"
PRIORITIES = Path(__file__).resolve().parent / "priorities.json"
OFFENSE = ("troops", "spells", "siege", "pets")


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@lru_cache(maxsize=1)
def load_game_data() -> dict:
    return json.loads(GAME_DATA.read_text(encoding="utf-8"))


def load_priorities() -> dict:
    return json.loads(PRIORITIES.read_text(encoding="utf-8"))


def cap_for_th(levels: list, th: int) -> int:
    """levels: [[nivel, th_requerido, costo, recurso, segundos], ...]"""
    allowed = [lv[0] for lv in levels if lv[1] <= th]
    return max(allowed) if allowed else 0


def remaining(levels: list, current: int, cap: int) -> tuple:
    """Suma costo (por recurso) y tiempo de los niveles current+1..cap."""
    cost: dict = {}
    secs = 0
    for level, _th, c, res, s in levels:
        if current < level <= cap:
            if isinstance(c, dict):  # equipo: varios minerales
                for k, v in c.items():
                    if v:
                        cost[k] = cost.get(k, 0) + v
            elif c:
                cost[res] = cost.get(res, 0) + c
            secs += s
    return cost, secs


def human_time(secs: int) -> str:
    d, rem = divmod(secs, 86400)
    h = rem // 3600
    return f"{d}d {h}h" if d else f"{h}h"


def build_plan(player: dict, play_style: str = "farming", priorities: dict | None = None) -> dict:
    """player: JSON crudo de la API /players/{tag}. Devuelve JSON compacto."""
    rules = priorities or load_priorities()
    units = load_game_data()["units"]
    th = int(player.get("townHallLevel") or 0)
    order = rules["category_order"].get(play_style) or rules["category_order"]["farming"]
    focus = {norm(n) for n in rules.get("focus_units", [])}

    owned = [u for u in player.get("heroes", []) + player.get("troops", []) + player.get("spells", [])
             if u.get("village") == "home"] + list(player.get("heroEquipment", []))

    entries, unknown = [], []
    totals = {}  # categoría -> [suma niveles, suma topes]
    for u in owned:
        info = units.get(norm(u["name"]))
        if not info:
            unknown.append(u["name"])  # p.ej. super tropas: no se planifican
            continue
        cat = info["category"]
        cap = cap_for_th(info["levels"], th)
        if cap == 0:
            continue
        level = min(int(u["level"]), cap)
        t = totals.setdefault(cat, [0, 0])
        t[0] += level
        t[1] += cap
        if level < cap:
            cost, secs = remaining(info["levels"], level, cap)
            entries.append({
                "name": info["name"], "category": cat, "level": level, "th_cap": cap,
                "missing_levels": cap - level, "remaining_cost": cost,
                "remaining_time": human_time(secs) if secs else None,
                "_ratio": level / cap, "_focus": norm(info["name"]) in focus,
            })

    def key(e):
        rank = order.index(e["category"]) if e["category"] in order else len(order)
        return (not e["_focus"], rank, e["_ratio"], e["name"])

    entries.sort(key=key)

    next_per_queue = {}
    for queue, cats in rules["queues"].items():
        candidates = [e for e in entries if e["category"] in cats]
        if candidates:
            e = min(candidates, key=lambda x: (not x["_focus"], x["_ratio"], x["name"]))
            next_per_queue[queue] = f"{e['name']} {e['level']}->{e['level'] + 1} (tope TH{th}: {e['th_cap']})"
        else:
            next_per_queue[queue] = "nada pendiente" if any(c in totals for c in cats) else "no desbloqueado"

    completion = {c: round(100 * a / b) for c, (a, b) in totals.items() if b}
    off = [totals[c] for c in OFFENSE if c in totals]
    offense_pct = round(100 * sum(a for a, _ in off) / sum(b for _, b in off)) if off else 0

    blockers = []
    if rules["next_th"].get("heroes_must_be_maxed"):
        blockers += [f"{e['name']} {e['level']}/{e['th_cap']}" for e in entries if e["category"] == "heroes"]
    min_off = rules["next_th"].get("min_offense_completion_pct", 85)
    if offense_pct < min_off:
        blockers.append(f"ofensiva al {offense_pct}% (mínimo {min_off}%)")

    clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in entries[: rules.get("max_items", 8)]]
    return {
        "town_hall": th,
        "play_style": play_style,
        "completion_pct": completion,
        "offense_completion_pct": offense_pct,
        "next_per_queue": next_per_queue,
        "top_priorities": clean,
        "total_pending_upgrades": len(entries),
        "ready_for_next_th": not blockers,
        "blockers": blockers,
        "not_covered": "Edificios, defensas y muros (la API oficial no los expone).",
        "unplanned_units": unknown[:10],
    }

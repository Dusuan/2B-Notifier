"""
Herramientas (function tools) que el agente puede invocar. Pocas, gruesas y con salidas compactas.
Cada función devuelve un dict JSON-serializable; los errores se devuelven como {"error": "..."}.
"""
import logging
import time
from config import config
from agent import store, news
from agent.coc_api import fetch_player, player_summary, normalize_tag, CocError
from agent.upgrade_plan import build_plan

logger = logging.getLogger("2B-Notifier.Tools")
PLAY_STYLES = ("farming", "war", "trophy")


def _tag(tag: str | None) -> str:
    tag = tag or store.get("profile").get("player_tag")
    if not tag:
        raise CocError("No hay player tag guardado. Pide al usuario su tag (ej. #ABC123) y guárdalo con update_profile.")
    return tag


def get_player(tag: str = "") -> dict:
    return player_summary(fetch_player(_tag(tag)))


def get_upgrade_plan(tag: str = "") -> dict:
    style = store.get("profile").get("play_style", "farming")
    return build_plan(fetch_player(_tag(tag)), play_style=style)


def get_latest_news(n: int = 5) -> dict:
    posts = news.latest(int(n or 5))
    return {"posts": posts} if posts else {"error": "No hay noticias en caché y no se pudo consultar el blog."}


def get_pokemon_status() -> dict:
    p = store.get("pokemon")
    last = p.get("last_cycle_at") or 0
    return {
        "monitor_enabled": config.enable_pokemon_monitor,
        "stores": ["Costco México", "Amazon México"],
        "watched_amazon_asins": config.amazon_asins,
        "last_scan": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(last)) if last else "nunca",
        "in_stock_at_msrp_last_scan": p.get("last_found", []),
        "recent_alerts": p.get("alerts_sent", [])[-5:],
    }


def get_profile() -> dict:
    return store.get("profile")


def update_profile(player_tag: str = "", play_style: str = "", goals: str = "", add_note: str = "",
                   notify_coc_news: bool | None = None, notify_pokemon_stock: bool | None = None) -> dict:
    if play_style and play_style not in PLAY_STYLES:
        return {"error": f"play_style debe ser uno de {PLAY_STYLES}"}

    def apply(p):
        if player_tag:
            p["player_tag"] = normalize_tag(player_tag)
        if play_style:
            p["play_style"] = play_style
        if goals:
            p["goals"] = goals[:300]
        if add_note:
            p["notes"] = (p.get("notes", []) + [add_note[:300]])[-30:]
        if notify_coc_news is not None:
            p["notify"]["coc_news"] = bool(notify_coc_news)
        if notify_pokemon_stock is not None:
            p["notify"]["pokemon_stock"] = bool(notify_pokemon_stock)

    return {"saved": True, "profile": store.update("profile", apply)}


FUNCTIONS = {f.__name__: f for f in (get_player, get_upgrade_plan, get_latest_news,
                                     get_pokemon_status, get_profile, update_profile)}

_tag_param = {"type": "string", "description": "Tag del jugador (ej. #2PP). Vacío = el guardado en el perfil."}

DECLARATIONS = [
    {"name": "get_player",
     "description": "Resumen de la cuenta de Clash of Clans: TH, héroes, equipo, trofeos, clan.",
     "parameters_json_schema": {"type": "object", "properties": {"tag": _tag_param}}},
    {"name": "get_upgrade_plan",
     "description": "Plan de mejoras calculado por código: qué falta para el TH actual, siguiente mejora por cola, "
                    "prioridades y si está listo para subir de TH. Úsalo para '¿qué mejoro?'.",
     "parameters_json_schema": {"type": "object", "properties": {"tag": _tag_param}}},
    {"name": "get_latest_news",
     "description": "Últimas noticias oficiales del blog de Clash of Clans (título, fecha, resumen, enlace).",
     "parameters_json_schema": {"type": "object", "properties": {
         "n": {"type": "integer", "description": "Cuántos posts (1-10). Default 5."}}}},
    {"name": "get_pokemon_status",
     "description": "Estado del monitor de stock de Pokémon TCG (Costco/Amazon México): último escaneo, "
                    "productos en stock a MSRP y alertas recientes.",
     "parameters_json_schema": {"type": "object", "properties": {}}},
    {"name": "get_profile",
     "description": "Perfil guardado del usuario: player tag, estilo de juego, metas, notas y qué notificaciones recibe.",
     "parameters_json_schema": {"type": "object", "properties": {}}},
    {"name": "update_profile",
     "description": "Guarda datos del usuario SOLO cuando él lo pide: tag, estilo (farming/war/trophy), metas, "
                    "una nota, o activar/desactivar notificaciones push (noticias CoC, stock Pokémon).",
     "parameters_json_schema": {"type": "object", "properties": {
         "player_tag": {"type": "string"},
         "play_style": {"type": "string", "enum": list(PLAY_STYLES)},
         "goals": {"type": "string"},
         "add_note": {"type": "string"},
         "notify_coc_news": {"type": "boolean"},
         "notify_pokemon_stock": {"type": "boolean"}}}},
]


def call(name: str, args: dict) -> dict:
    fn = FUNCTIONS.get(name)
    if not fn:
        return {"error": f"Herramienta desconocida: {name}"}
    try:
        return fn(**(args or {}))
    except CocError as e:
        return {"error": str(e)}
    except TypeError as e:
        return {"error": f"Argumentos inválidos para {name}: {e}"}
    except Exception as e:
        logger.exception(f"Fallo en herramienta {name}")
        return {"error": f"Fallo interno en {name}: {e}"}

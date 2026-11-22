"""Cliente mínimo de la API oficial de Clash of Clans con caché en memoria."""
import logging
import time
import urllib.parse
import requests
from config import config

logger = logging.getLogger("2B-Notifier.CoC")
_cache: dict = {}  # tag -> (timestamp, data)


class CocError(Exception):
    pass


def normalize_tag(tag: str) -> str:
    tag = (tag or "").strip().upper().replace("O", "0")
    return tag if tag.startswith("#") else f"#{tag}"


def fetch_player(tag: str) -> dict:
    """Devuelve el JSON crudo del jugador (cacheado PLAYER_CACHE_MINUTES)."""
    if not config.coc_api_token:
        raise CocError("COC_API_TOKEN no está configurado.")
    tag = normalize_tag(tag)
    cached = _cache.get(tag)
    if cached and time.time() - cached[0] < config.player_cache_minutes * 60:
        return cached[1]

    url = f"{config.coc_api_base}/players/{urllib.parse.quote(tag)}"
    try:
        res = requests.get(url, headers={"Authorization": f"Bearer {config.coc_api_token}"}, timeout=10)
    except requests.RequestException as e:
        raise CocError(f"Error de red con la API de CoC: {e}")

    if res.status_code == 200:
        data = res.json()
        _cache[tag] = (time.time(), data)
        return data
    reasons = {
        403: "403: llave inválida o la IP de este servidor no está en la whitelist de la llave",
        404: f"404: el tag {tag} no existe",
        429: "429: demasiadas peticiones a la API de CoC, intenta más tarde",
        503: "503: API de CoC en mantenimiento",
    }
    msg = reasons.get(res.status_code, f"HTTP {res.status_code}")
    logger.warning(f"[CoC API] {msg}")
    raise CocError(msg)


def player_summary(data: dict) -> dict:
    """Recorta el JSON del jugador a los campos útiles (aldea principal)."""
    home = lambda items: [i for i in items if i.get("village") == "home"]
    return {
        "tag": data.get("tag"),
        "name": data.get("name"),
        "town_hall": data.get("townHallLevel"),
        "exp_level": data.get("expLevel"),
        "trophies": data.get("trophies"),
        "war_stars": data.get("warStars"),
        "clan": (data.get("clan") or {}).get("name"),
        "heroes": {h["name"]: h["level"] for h in home(data.get("heroes", []))},
        "pets_and_troops_count": len(home(data.get("troops", []))),
        "spells_count": len(home(data.get("spells", []))),
        "equipment": {e["name"]: e["level"] for e in data.get("heroEquipment", [])},
    }

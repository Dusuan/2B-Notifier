"""
Almacén persistente mínimo: un único archivo JSON (montado como volumen Docker en la VM).
Guarda perfil del usuario, notas, preferencias de notificación, caché de noticias,
estado del monitor Pokémon y el contador diario de llamadas a Gemini.
"""
import json
import logging
import os
import threading
from copy import deepcopy
from config import config

logger = logging.getLogger("2B-Notifier.Store")
_lock = threading.Lock()

DEFAULT_STATE = {
    "profile": {
        "player_tag": config.coc_player_tag,
        "play_style": "farming",  # farming | war | trophy
        "goals": "",
        "notes": [],
        "notify": {"coc_news": True, "pokemon_stock": True},
    },
    "news": {"fetched_at": 0, "posts": [], "seen_urls": []},
    "pokemon": {"last_cycle_at": 0, "last_found": [], "alerts_sent": []},
    "usage": {"date": "", "count": 0},
}


def _load() -> dict:
    try:
        with open(config.state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"No se pudo leer {config.state_file} ({e}); se usa estado por defecto.")
        data = {}
    state = deepcopy(DEFAULT_STATE)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(state.get(key), dict):
            state[key].update(value)
        else:
            state[key] = value
    return state


def _save(state: dict) -> None:
    os.makedirs(os.path.dirname(config.state_file) or ".", exist_ok=True)
    tmp = config.state_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, config.state_file)


def get(section: str) -> dict:
    with _lock:
        return deepcopy(_load()[section])


def update(section: str, fn) -> dict:
    """Aplica fn(dict_de_la_sección) y persiste. Devuelve la sección resultante."""
    with _lock:
        state = _load()
        fn(state[section])
        _save(state)
        return deepcopy(state[section])

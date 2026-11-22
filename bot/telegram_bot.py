"""
Capa delgada de Telegram (long polling con la Bot API vía requests, sin librerías extra).
Corre en la VM 24/7, así que no hace falta webhook. Sólo responde a TELEGRAM_ALLOWED_USER_IDS.

Comandos (deterministas, no gastan cuota de IA):
  /start [#TAG]  guarda o confirma tu player tag
  /status        resumen de tu cuenta
  /next          prioridades de mejora
  /news          últimas noticias oficiales
  /pokemon       estado del monitor de stock Pokémon
Cualquier otro texto va al agente (Gemini).
"""
import logging
import threading
import requests
from config import config
from agent import core, tools, news

logger = logging.getLogger("2B-Notifier.Telegram")
API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # límite de Telegram: 4096


def _api(method: str, http_timeout: int = 15, **payload):
    url = API.format(token=config.telegram_bot_token, method=method)
    res = requests.post(url, json=payload, timeout=http_timeout)
    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} HTTP {res.status_code}: {data.get('description', res.text[:200])}")
    return data["result"]


def split_message(text: str, limit: int = MAX_LEN) -> list:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks + ([text] if text else [])


def send(chat_id: int, text: str) -> None:
    for chunk in split_message(text):
        try:
            _api("sendMessage", chat_id=chat_id, text=chunk, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"No se pudo enviar mensaje: {e}")


def _fmt_error(result: dict) -> str | None:
    return f"⚠️ {result['error']}" if "error" in result else None


def cmd_start(arg: str) -> str:
    if arg:
        p = tools.update_profile(player_tag=arg)["profile"]
        return f"✅ Tag guardado: {p['player_tag']}\nUsa /status, /next, /news o /pokemon, o pregúntame lo que quieras."
    tag = tools.get_profile().get("player_tag")
    if tag:
        return f"👋 Hola, soy 2B-Notifier. Tu tag es {tag}.\nComandos: /status /next /news /pokemon"
    return "👋 Hola, soy 2B-Notifier. Envía /start #TUTAG para guardar tu player tag de Clash of Clans."


def cmd_status() -> str:
    r = tools.call("get_player", {})
    if err := _fmt_error(r):
        return err
    heroes = "\n".join(f"  • {k}: {v}" for k, v in r["heroes"].items()) or "  (sin héroes)"
    return (f"🏰 {r['name']} ({r['tag']}) — TH{r['town_hall']}\n"
            f"⭐ Exp {r['exp_level']} | 🏆 {r['trophies']} | ⚔️ {r['war_stars']} estrellas de guerra\n"
            f"🛡️ Clan: {r['clan'] or '—'}\n🦸 Héroes:\n{heroes}")


def cmd_next() -> str:
    r = tools.call("get_upgrade_plan", {})
    if err := _fmt_error(r):
        return err
    queues = "\n".join(f"  • {q}: {v}" for q, v in r["next_per_queue"].items())
    top = "\n".join(
        f"  {i}. {e['name']} {e['level']}/{e['th_cap']}"
        + (f" — {', '.join(f'{v:,} {k}' for k, v in e['remaining_cost'].items())}" if e["remaining_cost"] else "")
        + (f" — {e['remaining_time']}" if e["remaining_time"] else "")
        for i, e in enumerate(r["top_priorities"], 1)) or "  ¡Todo al tope para tu TH! 🎉"
    comp = ", ".join(f"{k} {v}%" for k, v in r["completion_pct"].items())
    verdict = "✅ Listo para subir de TH" if r["ready_for_next_th"] else "⛔ Aún no subas de TH: " + "; ".join(r["blockers"])
    return (f"📋 Plan TH{r['town_hall']} ({r['play_style']}) — calculado por código\n"
            f"🔁 Siguiente por cola:\n{queues}\n\n🔝 Prioridades:\n{top}\n\n"
            f"📊 Progreso: {comp}\n{verdict}\nℹ️ {r['not_covered']}")


def cmd_news() -> str:
    r = tools.call("get_latest_news", {"n": 5})
    if err := _fmt_error(r):
        return err
    return "\n\n".join(news.format_post(p) for p in r["posts"])


def cmd_pokemon() -> str:
    r = tools.call("get_pokemon_status", {})
    found = "\n".join(f"  • {x}" for x in r["in_stock_at_msrp_last_scan"]) or "  (nada a MSRP)"
    return (f"🃏 Monitor Pokémon TCG: {'activo' if r['monitor_enabled'] else 'apagado'}\n"
            f"🕒 Último escaneo: {r['last_scan']}\n📦 ASINs vigilados: {len(r['watched_amazon_asins'])}\n"
            f"🔥 En stock a MSRP:\n{found}")


COMMANDS = {"/status": cmd_status, "/next": cmd_next, "/news": cmd_news, "/pokemon": cmd_pokemon}


def _keep_typing(chat_id: int, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            _api("sendChatAction", chat_id=chat_id, action="typing")
        except Exception:
            pass
        stop.wait(4.5)


def handle_message(msg: dict) -> None:
    user_id = (msg.get("from") or {}).get("id")
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if user_id not in config.telegram_allowed_user_ids:
        logger.warning(f"Mensaje ignorado de usuario no autorizado {user_id}.")
        return
    if not text:
        return

    stop = threading.Event()
    threading.Thread(target=_keep_typing, args=(chat_id, stop), daemon=True).start()
    try:
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd in ("/start", "/help"):
            reply = cmd_start(arg.strip())
        elif cmd in COMMANDS:
            reply = COMMANDS[cmd]()
        else:
            reply = core.answer(user_id, text)
    except Exception as e:
        logger.exception("Fallo procesando mensaje")
        reply = f"⚠️ Error interno: {e}"
    finally:
        stop.set()
    send(chat_id, reply)


def run_polling(stop: threading.Event) -> None:
    if not config.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN vacío: el bot interactivo no arrancará.")
        return
    if not config.telegram_allowed_user_ids:
        logger.warning("TELEGRAM_ALLOWED_USER_IDS/TELEGRAM_CHAT_ID vacíos: se ignorarán todos los mensajes.")
    try:
        _api("deleteWebhook")  # long polling no funciona si hay un webhook registrado
        me = _api("getMe")
        logger.info(f"Bot de Telegram conectado como @{me.get('username')} (long polling).")
    except Exception as e:
        logger.error(f"No se pudo inicializar Telegram: {e}")

    offset = 0
    while not stop.is_set():
        try:
            updates = _api("getUpdates", http_timeout=40, offset=offset, timeout=30, allowed_updates=["message"])
        except Exception as e:
            logger.warning(f"getUpdates falló ({e}); reintento en 5s.")
            stop.wait(5)
            continue
        for upd in updates:
            offset = upd["update_id"] + 1
            if "message" in upd:
                handle_message(upd["message"])

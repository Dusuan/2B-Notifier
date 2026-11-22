import time
import signal
import random
import sys
import logging
import threading
from typing import Dict
from config import config, logger
from alerts import dispatch_alert
from agent import store, news
from bot import telegram_bot
from scrapers.amazon import scan_amazon
from scrapers.costco import scan_costco
from scrapers.models import ScrapedItem
from test_alert import send_test_notification

# Control de terminación graciosa (Graceful shutdown): se activa con SIGINT/SIGTERM
stop_event = threading.Event()

# Cooldown para evitar spam de alertas (URL -> timestamp del último envío)
# Por defecto 12 horas para productos que permanecen disponibles continuamente
ALERT_COOLDOWN_SECONDS = int(config.alert_cooldown_hours * 3600)


def handle_shutdown(signum, frame):
    logger.info("Señal de detención recibida. Finalizando 2B-Notifier limpiamente...")
    stop_event.set()


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def run_monitor_cycle(alert_history: Dict[str, float]):
    """Ejecuta una ronda de inspección completa en todas las plataformas."""
    logger.info("=== Iniciando ronda de monitoreo ===")

    found_opportunities: list[ScrapedItem] = []

    # 1. Monitoreo Costco México
    try:
        costco_items = scan_costco()
        found_opportunities.extend(costco_items)
    except Exception as e:
        logger.error(f"Error inesperado en ciclo de Costco: {e}")

    # 2. Monitoreo Amazon México
    try:
        amazon_items = scan_amazon()
        found_opportunities.extend(amazon_items)
    except Exception as e:
        logger.error(f"Error inesperado en ciclo de Amazon: {e}")

    # Estado para el agente (herramienta get_pokemon_status)
    now = time.time()
    found_titles = [f"{it.store}: {it.title[:60]} — {it.price_str}" for it in found_opportunities]

    def _record(p):
        p["last_cycle_at"] = now
        p["last_found"] = found_titles

    store.update("pokemon", _record)

    # El usuario puede silenciar estas alertas desde el chat (update_profile)
    if not store.get("profile")["notify"].get("pokemon_stock", True):
        logger.info("Notificaciones de stock Pokémon desactivadas por el usuario; no se despachan alertas.")
        return

    # 3. Procesamiento y despacho de alertas
    for item in found_opportunities:
        last_sent = alert_history.get(item.url, 0)
        time_since_last = now - last_sent

        if time_since_last < ALERT_COOLDOWN_SECONDS:
            logger.info(
                f"[Cooldown Activo] Ya se alertó '{item.title[:30]}...' hace "
                f"{int(time_since_last // 60)} min. Se omite para evitar spam."
            )
            continue

        # Enviar alerta (Telegram, Discord, CallMeBot WhatsApp o Twilio) con botones de acción directa
        msg = item.to_whatsapp_message()
        buttons = item.get_action_buttons()
        success = dispatch_alert(msg, buttons=buttons)
        if success:
            alert_history[item.url] = now
            store.update("pokemon", lambda p: p.__setitem__(
                "alerts_sent", (p.get("alerts_sent", []) + [f"{time.strftime('%Y-%m-%d %H:%M')} {item.title[:60]}"])[-20:]))
            logger.info(f"¡Alerta despachada para {item.title[:40]}...!")
        else:
            logger.error(f"Fallo al despachar alerta para {item.title[:40]}...")

    logger.info(
        f"=== Fin de ronda. Oportunidades encontradas: {len(found_opportunities)} ==="
    )


def run_pokemon_monitor():
    """Hilo: bucle de monitoreo Pokémon TCG con jitter (comportamiento original de Pokenotify)."""
    alert_history: Dict[str, float] = {}
    while not stop_event.is_set():
        run_monitor_cycle(alert_history)
        # Jitter aleatorio (+/- 10s) para mitigar huellas de tráfico automatizado
        jitter = random.uniform(-10.0, 15.0)
        sleep_duration = max(15.0, config.check_interval + jitter)
        logger.info(f"Próxima inspección en {sleep_duration:.1f} segundos...\n")
        stop_event.wait(sleep_duration)


def run_news_watcher():
    """Hilo: refresca noticias oficiales de CoC y hace push de posts nuevos (si el usuario lo quiere)."""
    while not stop_event.is_set():
        try:
            new_posts = news.refresh()
            wants = store.get("profile")["notify"].get("coc_news", True)
            if new_posts and wants and config.telegram_chat_id:
                for p in new_posts:
                    telegram_bot.send(int(config.telegram_chat_id), "🆕 Nuevo post oficial de Clash of Clans\n\n" + news.format_post(p))
        except Exception as e:
            logger.error(f"Error en vigilante de noticias: {e}")
        stop_event.wait(max(600.0, config.news_refresh_hours * 3600))


def main():
    logger.info("Iniciando 2B-Notifier — bot + agente IA de notificaciones personales")
    logger.info(
        f"Intervalo base: {config.check_interval}s | Cooldown de alertas: {config.alert_cooldown_hours:.1f}h | "
        f"Precio MSRP Máx: ${config.max_msrp_price} MXN | Modelo IA: {config.gemini_model}"
    )
    logger.info(f"ASINs de Amazon monitoreados: {', '.join(config.amazon_asins)}")

    # Modo de prueba directa si se pasa el flag --test-alert
    if "--test-alert" in sys.argv:
        logger.info("Modo de prueba manual activado (--test-alert).")
        send_test_notification()
        return

    # Envío de prueba al arrancar el contenedor si está habilitado
    if config.send_startup_test_alert:
        send_test_notification()

    workers = [threading.Thread(target=run_news_watcher, name="news", daemon=True)]
    if config.enable_pokemon_monitor:
        workers.append(threading.Thread(target=run_pokemon_monitor, name="pokemon", daemon=True))
    for w in workers:
        w.start()

    # Hilo principal: bot interactivo de Telegram (long polling)
    telegram_bot.run_polling(stop_event)
    stop_event.wait()  # si el bot no arrancó, mantener vivos los monitores hasta SIGTERM

    logger.info("2B-Notifier se ha detenido correctamente.")


if __name__ == "__main__":
    main()

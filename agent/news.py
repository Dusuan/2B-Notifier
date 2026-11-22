"""
Noticias oficiales de Clash of Clans (blog de Supercell).
No hay RSS oficial: la página es Next.js y trae los artículos como JSON en <script id="__NEXT_DATA__">.
Se cachean ~10 posts en el store y se refrescan como máximo cada NEWS_REFRESH_HOURS.
"""
import json
import logging
import re
import time
import requests
from config import config
from agent import store

logger = logging.getLogger("2B-Notifier.News")

BASE = "https://supercell.com"
BLOG_URL = f"{BASE}/en/games/clashofclans/blog/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; 2B-Notifier personal bot)"}
MAX_POSTS = 10
SUMMARY_CHARS = 600


def _get(url: str) -> requests.Response:
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.encoding = "utf-8"  # el sitio no declara charset; sin esto requests asume Latin-1
    return res


def _next_data(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("No se encontró __NEXT_DATA__ (¿cambió el sitio?)")
    return json.loads(m.group(1))["props"]["pageProps"]


def _summary(url: str) -> str:
    """Usa la descripción OpenGraph oficial del artículo (resumen escrito por Supercell)."""
    try:
        res = _get(url)
        res.raise_for_status()
        desc = (_next_data(res.text).get("openGraph") or {}).get("description") or ""
        desc = " ".join(desc.split())
        return desc[:SUMMARY_CHARS] + ("…" if len(desc) > SUMMARY_CHARS else "")
    except Exception as e:
        logger.warning(f"No se pudo leer el artículo {url}: {e}")
        return ""


def fetch_posts() -> list:
    res = _get(BLOG_URL)
    if res.status_code != 200:
        raise RuntimeError(f"Blog de Supercell respondió HTTP {res.status_code}")
    articles = _next_data(res.text).get("articles", [])[:MAX_POSTS]
    return [{
        "title": a.get("title", "").strip(),
        "date": (a.get("publishDate") or "")[:10],
        "url": BASE + a.get("linkUrl", "").rstrip("/") + "/",
    } for a in articles if a.get("linkUrl")]


def refresh(force: bool = False) -> list:
    """Refresca la caché si está vencida. Devuelve SOLO los posts nuevos (no vistos antes)."""
    cache = store.get("news")
    if not force and time.time() - cache["fetched_at"] < config.news_refresh_hours * 3600:
        return []
    try:
        posts = fetch_posts()
    except Exception as e:
        logger.error(f"Fallo al refrescar noticias: {e}")
        return []

    known = {p["url"]: p for p in cache["posts"]}
    for p in posts:  # sólo se piden resúmenes de posts que no teníamos
        p["summary"] = known[p["url"]].get("summary", "") if p["url"] in known else _summary(p["url"])

    first_run = not cache["seen_urls"]
    new_posts = [p for p in posts if p["url"] not in cache["seen_urls"]]

    def apply(n):
        n["posts"] = posts
        n["fetched_at"] = time.time()
        n["seen_urls"] = list(dict.fromkeys(n["seen_urls"] + [p["url"] for p in posts]))[-100:]

    store.update("news", apply)
    logger.info(f"Noticias refrescadas: {len(posts)} posts, {len(new_posts)} nuevos.")
    return [] if first_run else new_posts  # en el primer arranque no se notifica el histórico


def latest(n: int = 5) -> list:
    refresh()
    return store.get("news")["posts"][: max(1, min(n, MAX_POSTS))]


def format_post(p: dict) -> str:
    summary = f"\n{p['summary']}" if p.get("summary") else ""
    return f"📰 {p['title']} ({p['date']}){summary}\n{p['url']}"

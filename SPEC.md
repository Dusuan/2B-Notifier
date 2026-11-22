# Especificaciones del Proyecto (SPEC.md)

Este documento es la fuente única de verdad para los requerimientos, la arquitectura y el diseño del sistema **2B-Notifier** (antes *Pokenotify*).

---

## 1. Visión General
**2B-Notifier** es un bot personal de Telegram + agente de IA que corre 24/7 y le envía a su único usuario las notificaciones que él considera relevantes, y además conversa con él usando herramientas deterministas:

1. **Monitor Pokémon TCG** (módulo original de Pokenotify): rastrea stock y precios de productos Pokémon TCG en inglés en **Costco México** y **Amazon México** y alerta cuando hay stock a MSRP (+colchón).
2. **Agente Clash of Clans**: optimiza la cuenta del usuario (progreso de TH, orden de mejoras, héroes/tropas/equipo) con datos reales de la API oficial y cálculos en código.
3. **Noticias oficiales de Clash of Clans**: lee el blog de Supercell, responde "¿qué hay de nuevo?" y hace push de posts nuevos.

El usuario decide qué recibe: puede activar/desactivar cada tipo de push desde el chat ("deja de mandarme noticias de CoC").

Origen del diseño: `HANDOFF.md` (agente CoC con Gemini free tier). Decisiones tomadas el 2026-11-22: hosting en la VM existente (no Cloud Run), reutilizar el bot de Telegram existente, docs en español, repo renombrado a `2B-Notifier`.

---

## 2. Arquitectura del Sistema

```text
Usuario en Telegram
   │  (long polling getUpdates — la VM corre 24/7, no se necesita webhook)
   ▼
VM e2-micro GCP (Docker, contenedor "2b-notifier")
 main.py
   ├── Hilo principal: bot/telegram_bot.py
   │     ├── allowlist TELEGRAM_ALLOWED_USER_IDS (ignora a cualquier otro)
   │     ├── comandos deterministas /start /status /next /news /pokemon (0 llamadas a IA)
   │     └── texto libre → agent/core.answer(user_id, msg)
   │            └── bucle Gemini (google-genai, function calling manual, máx 5 iteraciones)
   │                  └── agent/tools.py (6 herramientas)
   │                        ├── get_player        → API oficial CoC (caché 20 min)
   │                        ├── get_upgrade_plan  → agent/upgrade_plan.py (sin LLM) + data/game_data.json
   │                        ├── get_latest_news   → agent/news.py (blog Supercell, caché 6 h)
   │                        ├── get_pokemon_status→ estado del último escaneo
   │                        ├── get_profile
   │                        └── update_profile    → tag, estilo, metas, notas, preferencias de push
   ├── Hilo "pokemon": scrapers Costco/Amazon cada ~90 s con jitter → alerts.dispatch_alert
   ├── Hilo "news": refresca noticias cada NEWS_REFRESH_HOURS → push de posts nuevos
   └── agent/store.py → state/state.json (volumen Docker)
```

### Principios de diseño (el modelo es pequeño)
1. **El código piensa, la IA habla**: topes por TH, costos, tiempos, prioridades y veredicto de "subir de TH" se calculan en Python.
2. **Pocas herramientas gruesas** (6) con descripciones cortas y salidas JSON compactas.
3. **Topes duros**: `AGENT_MAX_ITERATIONS` (5) llamadas al modelo por mensaje, `GEMINI_DAILY_LIMIT` (400/día, reinicio a medianoche del Pacífico), timeouts en todas las peticiones, 429 → mensaje amable.
4. **Caché agresiva**: jugador 20 min, noticias 6 h, datos estáticos al iniciar.
5. **Respuestas fundamentadas**: el prompt de sistema obliga a responder sólo con resultados de herramientas, decir "no lo sé" si falta el dato y citar título/fecha/enlace en noticias.

---

## 3. Componentes

### 3.1 API de Clash of Clans (`agent/coc_api.py`)
- `GET {COC_API_BASE}/players/{tag}` con `Authorization: Bearer COC_API_TOKEN`.
- Las llaves de CoC están atadas a IPs. Como corre en la VM (IP pública estable), basta crear la llave con la IP de la VM. Si la IP cambia: regenerar la llave o usar el proxy de RoyaleAPI vía `COC_API_BASE` (ver `REFERENCES.md`).
- Limitación: la API no expone niveles de edificios/defensas/muros; el plan lo indica explícitamente.

### 3.2 Calculador de mejoras (`agent/upgrade_plan.py`, `agent/priorities.json`)
- Tope por TH = mayor nivel cuyo TH requerido ≤ TH del jugador (héroes vía Hero Hall, equipo vía Blacksmith).
- Salida: % de avance por categoría, siguiente mejora por cola (Hero Hall, Laboratorio, Pet House, Blacksmith), top de prioridades con costo/tiempo restante, veredicto `ready_for_next_th` con bloqueadores.
- Reglas editables en `priorities.json`: orden de categorías por estilo (`farming`/`war`/`trophy`), `focus_units`, héroes al tope y % mínimo de ofensiva para subir de TH.

### 3.3 Datos estáticos (`data/game_data.json`)
- Generado por `tools/build_game_data.py` desde [chiefpansancolt/clash-of-clans-data](https://github.com/chiefpansancolt/clash-of-clans-data), fijado al commit `7afaa03` (2026-11-06, incluye el balance de octubre 2026).
- Formato compacto por unidad: `[nivel, th_requerido, costo, recurso, segundos]`.

### 3.4 Noticias (`agent/news.py`)
- No existe RSS oficial. La página del blog es Next.js: los artículos vienen en `<script id="__NEXT_DATA__">` (`props.pageProps.articles[]` con `title`, `linkUrl`, `publishDate`).
- Resumen = `openGraph.description` oficial de cada artículo (sin gastar cuota de IA). Se cachean ~10 posts y las URLs vistas; en el primer arranque no se notifica el histórico.

### 3.5 Monitor Pokémon TCG (`scrapers/`, `alerts/`)
- Sin cambios funcionales respecto a Pokenotify: filtro TCG en inglés, MSRP dinámico con colchón (`MSRP_CUSHION_PERCENT`), sólo vendedor Amazon México, cooldown de 12 h, botones 1-Click, manejo de 403/503/CAPTCHA.
- Nuevo: registra el último escaneo y las alertas en el store y respeta la preferencia `notify.pokemon_stock`.

### 3.6 Bot de Telegram (`bot/telegram_bot.py`)
- Bot API directa con `requests` (decisión: evita dependencias; long polling basta en una VM 24/7). Al iniciar llama `deleteWebhook`.
- Indicador "escribiendo…" mientras el agente trabaja, mensajes en texto plano partidos a ≤4000 caracteres.

---

## 4. Esquema de Variables de Entorno (.env)

| Variable | Requerido | Descripción | Default |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Sí | Token del bot (@BotFather) | — |
| `TELEGRAM_CHAT_ID` | Sí | Chat privado del usuario (destino de los push) | — |
| `TELEGRAM_ALLOWED_USER_IDS` | No | IDs de usuario permitidos (coma) | `TELEGRAM_CHAT_ID` |
| `GEMINI_API_KEY` | Para el chat IA | Llave de Google AI Studio (free tier) | — |
| `GEMINI_MODEL` | No | Modelo Gemini (verificar vigencia en la doc oficial) | `gemini-3.5-flash-lite` |
| `GEMINI_DAILY_LIMIT` | No | Tope propio de llamadas al modelo por día | `400` |
| `AGENT_MAX_ITERATIONS` | No | Máx. llamadas al modelo por mensaje | `5` |
| `COC_API_TOKEN` | Para CoC | Llave de developer.clashofclans.com (IP de la VM) | — |
| `COC_PLAYER_TAG` | No | Tag inicial (también se guarda con `/start #TAG`) | — |
| `COC_API_BASE` | No | Base de la API (o proxy RoyaleAPI) | `https://api.clashofclans.com/v1` |
| `PLAYER_CACHE_MINUTES` | No | Caché del jugador | `20` |
| `NEWS_REFRESH_HOURS` | No | Frecuencia de refresco/push de noticias | `6` |
| `ENABLE_POKEMON_MONITOR` | No | Encender/apagar el monitor Pokémon | `true` |
| `STATE_FILE` | No | Ruta del JSON persistente | `state/state.json` (Docker: `/app/state/state.json`) |
| `CHECK_INTERVAL_SECONDS`, `ALERT_COOLDOWN_HOURS`, `AMAZON_ASINS`, `MAX_MSRP_PRICE_MXN`, `MSRP_CUSHION_PERCENT`, `AMAZON_ONLY_OFFICIAL_SELLER`, `SEND_STARTUP_TEST_ALERT` | No | Parámetros del monitor Pokémon (ver `.env.example`) | — |
| `DISCORD_WEBHOOK_URL`, `CALLMEBOT_*`, `TWILIO_*` | No | Canales extra de alertas Pokémon | — |

---

## 5. Estrategia de Despliegue
- **Decisión (2026-11-22)**: reutilizar la VM **e2-micro Always Free** de GCP donde ya corría Pokenotify, con `docker compose`.
  - Resuelve el bloqueo de IP de la API de CoC (IP pública estable de la VM, sin Cloud NAT ni proxy).
  - Permite long polling y el bucle continuo del monitor Pokémon (Cloud Run escala a cero y requeriría webhook + Cloud Scheduler).
  - Costo esperado: $0/mes. Red de seguridad: alerta de presupuesto en Billing.
- Alternativa documentada pero no implementada: Cloud Run + webhook + Secret Manager + Cloud Scheduler (ver `HANDOFF.md`).
- Guía paso a paso: `README.md` → "Despliegue en la VM de Google Cloud".

---

## 6. Estado de Implementación (Hitos)

### Fases 1–4 (Pokenotify, 2026-10-19/20)
- [x] Monitor Pokémon TCG (Costco/Amazon MX), alertas Telegram/Discord/CallMeBot/Twilio, Docker, VM GCP.

### Fase 5: 2B-Notifier (2026-11-22)
- [x] Rebrand a 2B-Notifier (código, Docker, docs).
- [x] Datos estáticos CoC + generador (`tools/build_game_data.py`).
- [x] Calculador de mejoras determinista + reglas editables + tests unitarios.
- [x] Fetcher de noticias del blog de Supercell + caché + push de posts nuevos.
- [x] Store persistente (perfil, notas, preferencias de notificación, contador IA).
- [x] Agente Gemini con 6 herramientas, topes duros y CLI local (`cli.py`).
- [x] Bot interactivo de Telegram con allowlist y comandos.
- [ ] Despliegue en la VM con llaves reales (Gemini, CoC) y verificación en Telegram.
- [ ] Opcional: niveles de edificios vía exportación de aldea.

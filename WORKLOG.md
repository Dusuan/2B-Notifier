# Registro de Trabajo (WORKLOG.md)

Este documento mantiene un registro cronológico del progreso, decisiones tomadas y pendientes del proyecto **2B-Notifier** (antes Pokenotify).

> **[REGLA ESTRICTA]**: Cada sesión de trabajo debe actualizar el registro del día en curso. No agregar una nueva entrada si ya existe una para el día de hoy; editar/sobrescribir la entrada del día actual para reflejar el estado final acumulado de la sesión.

---

## Sesión: 2026-11-22 (Rebrand a 2B-Notifier + agente IA de Clash of Clans según HANDOFF.md)

**Solicitud:** Analizar el proyecto, implementar el plan de `~/Downloads/HANDOFF.md` (agente CoC con Gemini free tier), renombrar Pokenotify → 2B-Notifier (bot + agente IA de notificaciones relevantes), guía de Google Cloud y conectar el MCP de Google Cloud.

**Decisiones del usuario:** hosting en la VM e2-micro existente (no Cloud Run); reutilizar el bot de Telegram actual; renombrar también el repo de GitHub; docs en español.

**Investigación verificada (no de memoria):** modelos Gemini estables con free tier (default `gemini-3.5-flash-lite`); API de `google-genai` 3.6.1 inspeccionada localmente; blog de Supercell sin RSS pero con JSON `__NEXT_DATA__`; dataset `chiefpansancolt/clash-of-clans-data` (commit `7afaa03`) con TH requerido por nivel; `python-telegram-bot` 22.8 / `aiogram` 3.33.0 evaluadas y descartadas a favor de Bot API directa con `requests`.

**Qué implementamos:**
- `tools/build_game_data.py` + `data/game_data.json` (120 unidades: héroes, tropas, hechizos, mascotas, máquinas, equipo).
- `agent/`: `core.py` (bucle Gemini manual, máx 5 iteraciones, tope diario 400, manejo de 429), `tools.py` (6 herramientas), `upgrade_plan.py` + `priorities.json` (calculador determinista), `coc_api.py`, `news.py` (con push de posts nuevos), `store.py` (JSON en volumen `state/`).
- `bot/telegram_bot.py`: long polling, allowlist, `/start /status /next /news /pokemon`, chat libre, "escribiendo…", partición de mensajes.
- `main.py`: orquestador multi-hilo (monitor Pokémon + noticias + bot); el monitor respeta la preferencia de notificación y registra estado.
- `cli.py`, `tests/test_upgrade_plan.py`, `tests/test_agent_loop.py` (13 tests OK).
- Rebrand en loggers, `test_alert.py`, Docker (`python:3.12-slim`, servicio `notifier`, contenedor `2b-notifier`, volumen `notifier_state`), nuevo `.dockerignore` (evita copiar `.env` y `.venv` a la imagen), `.env.example`.
- Docs: `CLAUDE.md`, `SPEC.md` (reescrito), `REFERENCES.md` (sección 7), `README.md` (guía de despliegue y llaves).
- **CD pull-based** (a pedido del usuario, sin CI en GitHub Actions): `deploy/autodeploy.sh` (cron cada 5 min en la VM: fetch → ff-merge → build → tests en la imagen nueva → `up -d`; rollback + marca `.deploy_failed` + aviso Telegram si falla) y `deploy/install_autodeploy.sh`. Imagen con nombre fijo `2b-notifier:latest` en `docker-compose.yml`. Simulado localmente con remoto git y `docker` falso: éxito, sin cambios, tests fallidos (rollback sin reintento) y recuperación tras fix.

**Archivos:** creados `agent/*`, `bot/*`, `tools/build_game_data.py`, `data/game_data.json`, `cli.py`, `tests/*`, `.dockerignore`; modificados `main.py`, `config.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.gitignore`, `.env.example`, `test_alert.py`, `alerts/*.py`, `scrapers/{amazon,costco,pricing}.py`, `CLAUDE.md`, `SPEC.md`, `REFERENCES.md`, `README.md`, `WORKLOG.md`.

**Git:** commits `16466ed` (build datos), `d16ca48` (agente), `13dd62f` (bot + orquestador), `babbe0b` (rebrand), `66aa99a` (docs), `fb17402` (CD), `449a76b` (fix: `COC_PLAYER_TAG` del .env si el perfil no tiene tag) y este commit de worklog. Repo GitHub renombrado a `Dusuan/2B-Notifier`. `git push` de `8dab532..fb17402` con aprobación del usuario; `449a76b` y posteriores quedan locales hasta nueva aprobación.

**Despliegue en la VM (`pokenotify-worker`, usuario `dusuanchancloso6`, `~/Pokenotify`):** `git remote set-url` a 2B-Notifier, `git pull --ff-only` a `fb17402`, `docker compose build` (8m33s), 13 tests OK dentro de la imagen, `docker compose up -d --remove-orphans` (eliminó `pokenotify-worker`, arrancó `2b-notifier`). Logs: alerta de prueba enviada, bot conectado como `@tcgpokedus_bot`, noticias refrescadas (6). Cron de autodeploy instalado (`*/5`, log en `~/2b-notifier-deploy.log`); corrida manual sin cambios OK.

**Cambios fuera del repo:** `gcloud compute ssh` generó `~/.ssh/google_compute_engine` local y subió la llave pública a la metadata del proyecto `pokebot-512120`; la primera conexión creó por error un usuario nuevo `dusuan` en la VM (sin repo ni docker; se puede borrar con `sudo userdel -r dusuan`). `gcloud auth login` hecho por el usuario; `gcloud config set project pokebot-512120` (VM `pokenotify-worker`, us-central1-c, IP efímera 34.63.27.32). gcloud CLI 594.0.1 instalado en `~/.local/google-cloud-sdk` (sin sudo, sin tocar rc de shell); MCP `gcloud` (`@google-cloud/gcloud-mcp`) registrado con `claude mcp add gcloud -s local` (en `~/.claude.json`, sólo este proyecto); `.venv/` local (ignorado por git).

**No verificado / omitido:** build local de Docker (Docker Desktop apagado; sí se verificó en la VM); llamadas reales a Gemini y a la API de CoC (no hay llaves locales). Bug preexistente sin tocar: `alerts/twilio_client.py` llama `config.validate_twilio()`, que no existe en `Config` (Twilio nunca se inicializa).

**Próximos pasos:**
1. Usuario: cargar `GEMINI_API_KEY`, `COC_API_TOKEN`, `COC_PLAYER_TAG` con el script de prompt oculto (`set_secrets.sh`).
2. `git push` de `449a76b` → primera prueba real del CD (mensaje 🚀 en Telegram).
3. Crear alerta de presupuesto en Billing.
4. Decidir si arreglar `validate_twilio`.

---

## Sesión: 2026-10-20 (Verificación de Alertas y Test Suite)

**Qué implementamos en esta sesión:**
- Creación del script de prueba `test_alert.py` para verificar notificaciones directamente a Telegram sin esperar ciclos de stock.
- Integración de alerta de confirmación automática en `main.py` al arrancar el contenedor (`SEND_STARTUP_TEST_ALERT=true`).
- Soporte para flag manual `--test-alert` en `main.py`.
- Ejecución y verificación exitosa de prueba de notificación con entrega real a Telegram.
- Documentación del flujo de pruebas en `README.md` y actualización del template `.env.example`.
- Implementación de filtro inteligente de TCG en `config.py` y `scrapers/costco.py` con lista blanca de términos de cartas (ETB, booster, tin, colección, sobres) y lista negra de exclusión (Legos, Mega Construx, peluches, videojuegos, ropa).
- Implementación del módulo de precios dinámicos `scrapers/pricing.py` con tabla oficial de MSRPs en USD para todas las categorías (ETB, Booster Box, UPC, Blisters, Tins, etc.), consulta y caché del tipo de cambio USD/MXN en tiempo real, y cálculo automático con colchón porcentual configurable actualizado al +25% (`MSRP_CUSHION_PERCENT=25.0`), estableciendo el tope de alerta para ETBs en ~$1,153 MXN para capturar compras ventajosas en $1,100 MXN.
- Regla estricta de idioma implementada en `config.py`, `scrapers/amazon.py` y `scrapers/costco.py`: filtro que descarta automáticamente cualquier producto o carta en idioma Español (`español`, `spanish`, `castellano`, etc.), garantizando alertas exclusivas para cartas Pokémon TCG en idioma Inglés.
- Extracción precisa de vendedor/remitente en Amazon México (`extract_amazon_seller_info`) y filtro estricto `AMAZON_ONLY_OFFICIAL_SELLER=true` ajustado para garantizar alertas exclusivamente de productos vendidos/enviados específicamente por Amazon México (descartando revendedores terceros e importaciones de Amazon EE.UU.).
- Integración de botones interactivos Inline Keyboard en Telegram (`alerts/notifier.py`) con URLs Direct 1-Click (`scrapers/models.py`) que permiten añadir al carrito y abrir checkout instantáneo en la App oficial de Amazon con 1 solo toque.
- Configuración de cooldown de alertas ampliado a 12 horas (`ALERT_COOLDOWN_HOURS=12.0` en `config.py` y `main.py`) para evitar spam repetitivo en productos que permanecen en stock de forma continua.
- Implementación de `get_clean_headline` en `scrapers/models.py` para extraer de forma inteligente el nombre real de la caja o set (ej: `PITCH BLACK (ETB)`, `30TH ANNIVERSARY (ETB)`) y ubicarlo en la primerísima línea del mensaje para lectura instantánea en el banner de notificaciones del celular.
- Verificación exitosa en vivo de la nueva estructura de alerta mediante `test_alert.py`.

**Qué está en progreso:**
- Monitoreo continuo 24/7 en la VM de Google Cloud Platform (GCP).

**Bloqueos:**
- Ninguno.

**Próximos pasos en orden de prioridad:**
1. En la VM de GCP, ejecutar `git pull && docker-compose up -d --build` para actualizar el contenedor con el ping de confirmación al arranque.
2. Agregar nuevos ASINs de Pokémon TCG en `.env` conforme salgan preventas de nuevos sets.

---

## Sesión: 2026-10-19 (Fases 1, 2, 3 y 4: Implementación Completa y Despliegue)

**Qué implementamos en esta sesión:**
- **Fase 1 (Context Management & Docs)**:
  - Repositorio Git inicializado con estructura de branches y `.gitignore`.
  - Creación de los cuatro documentos de contexto: `CLAUDE.md`, `SPEC.md`, `WORKLOG.md` y `REFERENCES.md`.
  - Commit inicial realizado (`docs: inicializa estructura de contexto y especificaciones`).
- **Fase 2 (Features Implementados)**:
  - *Feature 1*: Configuración y dependencias (`requirements.txt`, `.env.example`, `config.py`) con validación y tipado de variables (`feat: setup dependencias y env`).
  - *Feature 2*: Módulo de mensajería `alerts/twilio_client.py` con lazy loading de Twilio SDK y fallback en modo log (`feat: integra cliente de twilio para alertas whatsapp`).
  - *Feature 3*: Scrapers de Amazon y Costco (`scrapers/amazon.py`, `scrapers/costco.py`, `scrapers/utils.py`, `scrapers/models.py`) con mitigación de WAF, rotación de cabeceras, detección de CAPTCHA/403/503 y filtro de precios MSRP (`feat: implementa scrapers de amazon y costco`).
  - *Feature 4*: Orquestador principal `main.py` con bucle continuo, jitter aleatorio (+/- 10s), mitigación de spam mediante cooldown de 1h y manejo de señales `SIGINT`/`SIGTERM` (`feat: orquestacion del loop principal y tiempos de espera`).
- **Fase 3 (Contenerización)**:
  - Creación de `Dockerfile` basado en `python:3.11-slim`, activando `PYTHONUNBUFFERED=1` y configurando usuario no privilegiado (`appuser`).
  - Creación de `docker-compose.yml` para levantar el worker con inyección de variables de entorno y reinicio automático (`build: dockeriza la aplicacion de monitoreo`).
- **Fase 4 (Despliegue Always Free en GCP, Telegram API & README)**:
  - Soporte integrado para **Telegram Bot API** (100% permanente y continuo gratuito para mensajes push al celular).
  - Configuración y despliegue en **Google Cloud Platform (GCP)** sobre instancia `e2-micro` (Always Free permanente en `us-central1` con disco estándar de 30 GB).
  - Creación de [README.md](file:///c:/Users/XxDus/Documents/Pokenotify/README.md) documentando la arquitectura, la guía paso a paso de actualización continua (CI/CD manual) y comandos de mantenimiento de Docker.

**Qué está en progreso:**
- Ejecución continua del bot en segundo plano dentro de la VM de GCP monitoreando Costco y Amazon México.

**Bloqueos:**
- Ninguno.

**Próximos pasos en orden de prioridad:**
1. Verificar recepción de la primera alerta de prueba en Telegram.
2. Afinar selectores o agregar nuevos ASINs de Pokémon TCG en `.env` según demanda de mercado.
3. Actualizar la lógica con `git push` local y `git pull && docker-compose up -d --build` en la VM cuando se requieran ajustes de scraping.

---
*(Las sesiones futuras se registrarán en orden cronológico inverso, sobreescribiendo la sección del día si ya existe).*

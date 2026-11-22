# Instrucciones del Proyecto (CLAUDE.md)

Este documento contiene las reglas generales, convenciones, comandos personalizados y directrices de operación para el Asistente AI (Agente de Software) en el proyecto **2B-Notifier** (antes *Pokenotify*): bot de Telegram + agente IA que envía al usuario las notificaciones que él considera relevantes.

---

## Reglas Fundamentales de Operación del Agente

1. **Lectura Previa Obligatoria**: Antes de generar o modificar código, el agente debe leer `CLAUDE.md`, `SPEC.md`, `REFERENCES.md` y `WORKLOG.md` para entender el estado actual del proyecto y no desalinearse de los objetivos.
2. **Dependencias Estrictas**: No instalar ni importar librerías externas que no estén previamente discutidas y aprobadas en `SPEC.md` / `requirements.txt`. El stack base es `requests`, `beautifulsoup4`, `twilio`, `python-dotenv` y `google-genai` (aprobado 2026-11-22 para el agente). Telegram se usa vía Bot API directa con `requests` (sin librería de bots).
3. **Regla de WORKLOG.md**: Al concluir una tarea o sesión, actualizar `WORKLOG.md`. Si ya existe una sección para el día de hoy, **editar/sobrescribir** la entrada de hoy para reflejar el estado final, nunca duplicar la fecha.
4. **Simplicidad ante Todo (KISS)**: Escribir el código mínimo necesario que resuelva el requerimiento. Evitar sobre-ingeniería o abstracciones complejas para casos hipotéticos.
5. **Cambios Quirúrgicos**: Modificar únicamente lo necesario. No tocar código adyacente ni formatear archivos no relacionados.
6. **Commits Atómicos y Semánticos**: Seguir la convención Conventional Commits (`feat:`, `fix:`, `docs:`, `build:`, `refactor:`, `chore:`).
7. **El código piensa, la IA habla**: Prioridades de mejora, topes por TH, costos y tiempos se calculan en Python (`agent/upgrade_plan.py`). El modelo sólo elige herramientas y redacta. Nunca mover lógica de negocio al prompt.
8. **Pocas herramientas, salidas compactas**: Máximo 6 tools en `agent/tools.py`, devolviendo JSON recortado. Mantener los topes duros (iteraciones, cupo diario, timeouts).
9. **Tests**: `python -m unittest discover -s tests` debe pasar antes de cada commit.

---

## Comandos Personalizados

- `/load-project`: Lee `CLAUDE.md`, `SPEC.md` y `WORKLOG.md` en orden. Responde con un resumen del estado actual, tareas en curso y el próximo paso. No escribe código hasta confirmación.
- `/review-code`: Revisa el código implementado con mentalidad de Senior Engineer evaluando: 1) Bugs / Edge cases, 2) Cumplimiento de `CLAUDE.md`, 3) Simplicidad, 4) Manejo de errores HTTP (403, 503) y WAF, 5) Riesgos en producción.
- `/new-feature [descripción]`: Planifica e implementa una nueva funcionalidad paso a paso siguiendo los patrones de `REFERENCES.md`.
- `/fix-bug [descripción]`: Diagnostica y repara un problema especificando causa, archivos afectados y diff exacto sin alterar código fuera de alcance.
- `/update-worklog`: Actualiza `WORKLOG.md` reflejando el progreso del día.
- `/add-reference [tema]`: Agrega selectores, snippets o técnicas anti-WAF a `REFERENCES.md`.
- `/update-spec [cambio]`: Actualiza requerimientos o modelos en `SPEC.md`.

---

## Stack Tecnológico (2B-Notifier)
- **Lenguaje**: Python 3.12 (imagen `python:3.12-slim`)
- **IA**: Gemini API free tier vía `google-genai` (modelo en `GEMINI_MODEL`, bucle manual de function calling)
- **Interfaz**: Telegram Bot API (long polling con `requests`; sólo usuarios en `TELEGRAM_ALLOWED_USER_IDS`)
- **Datos de juego**: API oficial de Clash of Clans + `data/game_data.json` (generado con `tools/build_game_data.py`)
- **Scraping**: `requests`, `beautifulsoup4` (Costco/Amazon México, blog de Supercell)
- **Mensajería extra**: Discord, CallMeBot, `twilio` (WhatsApp)
- **Configuración**: `python-dotenv`
- **Contenedor / Hosting**: Docker + `docker compose` en la VM e2-micro (Always Free) de GCP

## Mapa del Código
- `main.py`: orquestador (hilo monitor Pokémon, hilo noticias CoC, bot Telegram en hilo principal).
- `agent/core.py`: `answer(user_id, message) -> str` (bucle Gemini con topes). `agent/tools.py`: las 6 herramientas.
- `agent/upgrade_plan.py` + `agent/priorities.json`: calculador determinista y reglas editables.
- `agent/coc_api.py`, `agent/news.py`, `agent/store.py` (JSON persistente en `state/`).
- `bot/telegram_bot.py`: comandos `/start /status /next /news /pokemon` y chat libre.
- `scrapers/`, `alerts/`: monitor Pokémon TCG original. `cli.py`: probar el agente sin Telegram.

---

## Proceso de Trabajo del Agente
1. Verificar siempre la existencia y valores en variables de entorno antes de ejecutar llamadas de red.
2. Manejar excepciones de red y códigos de estado (403 Forbidden por WAF, 429 Too Many Requests, 503 Service Unavailable) con logging claro y reintentos o backoff.
3. Asegurar que las salidas de terminal y logs no queden atascadas en buffers (`PYTHONUNBUFFERED=1`).
4. Realizar commits claros y descriptivos por cada feature completado.
5. Tras cada actualización del juego, regenerar datos: `python tools/build_game_data.py --ref main` y revisar los tests.

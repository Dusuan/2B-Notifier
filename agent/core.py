"""
Núcleo del agente: answer(user_id, message) -> str.
Bucle manual de function calling con Gemini (google-genai), con topes duros:
- máx. AGENT_MAX_ITERATIONS llamadas al modelo por mensaje,
- contador diario (día del Pacífico, como la cuota de Gemini) con tope GEMINI_DAILY_LIMIT,
- manejo amable de 429.
El código piensa (herramientas deterministas); el modelo sólo elige herramientas y redacta.
"""
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from config import config
from agent import store, tools

logger = logging.getLogger("2B-Notifier.Agent")

SYSTEM_PROMPT = """Eres 2B, el asistente personal de tu usuario dentro de Telegram.
Ayudas con su cuenta de Clash of Clans (progreso de TH, orden de mejoras, héroes, tropas, equipo),
con las noticias oficiales del juego y con su monitor de stock de Pokémon TCG.

Reglas estrictas:
1. Para cualquier dato del juego, de su cuenta o de stock, llama a una herramienta. Responde SOLO con
   datos devueltos por herramientas. Nunca inventes niveles, costos, tiempos ni fechas.
2. Si una herramienta devuelve "error" o el dato no está, dilo claramente ("No lo sé" / el error).
3. Las prioridades de mejora vienen de get_upgrade_plan: respeta su orden, no lo reordenes.
4. Al usar noticias, cita título y fecha del post e incluye el enlace.
5. Sólo guarda datos con update_profile cuando el usuario lo pida explícitamente.
6. Respuestas cortas, en el idioma del usuario, texto plano con emojis moderados (sin tablas ni Markdown).
"""

HISTORY_TURNS = 6
_history = defaultdict(lambda: deque(maxlen=HISTORY_TURNS))
_client = None


def _pacific_today() -> str:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
    except Exception:
        tz = timezone(timedelta(hours=-8))
    return datetime.now(tz).strftime("%Y-%m-%d")


def _take_quota() -> bool:
    """Reserva 1 llamada del cupo diario. False si ya se agotó."""
    today = _pacific_today()
    ok = {"v": False}

    def apply(u):
        if u.get("date") != today:
            u["date"], u["count"] = today, 0
        if u["count"] < config.gemini_daily_limit:
            u["count"] += 1
            ok["v"] = True

    store.update("usage", apply)
    return ok["v"]


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=config.gemini_api_key)
    return _client


def answer(user_id: int, message: str) -> str:
    if not config.gemini_api_key:
        return "⚠️ GEMINI_API_KEY no está configurado; sólo funcionan los comandos /status, /next, /news y /pokemon."

    from google.genai import types, errors

    client = _get_client()
    gen_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in tools.DECLARATIONS])],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.3,
    )
    history = _history[user_id]
    contents = list(history) + [types.Content(role="user", parts=[types.Part.from_text(text=message)])]

    for i in range(config.agent_max_iterations):
        if not _take_quota():
            return "⏳ Llegué al tope diario de consultas a la IA. Se reinicia a medianoche (hora del Pacífico)."
        try:
            response = client.models.generate_content(model=config.gemini_model, contents=contents, config=gen_config)
        except errors.APIError as e:
            if e.code == 429:
                return "⏳ Cuota de Gemini alcanzada por ahora. Intenta en un rato."
            logger.error(f"Error de Gemini API ({e.code}): {e}")
            return f"⚠️ Error de la IA (HTTP {e.code}). Intenta más tarde."
        except Exception as e:
            logger.exception("Fallo llamando a Gemini")
            return f"⚠️ No pude contactar a la IA: {e}"

        calls = response.function_calls or []
        if not calls:
            text = (response.text or "").strip() or "🤔 No tengo una respuesta para eso."
            history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
            history.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))
            return text

        contents.append(response.candidates[0].content)
        parts = []
        for fc in calls:
            result = tools.call(fc.name, dict(fc.args or {}))
            logger.info(f"[Agente] iter {i + 1}: {fc.name}({json.dumps(dict(fc.args or {}), ensure_ascii=False)}) "
                        f"-> {json.dumps(result, ensure_ascii=False)[:200]}")
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
        contents.append(types.Content(role="user", parts=parts))

    return "⚠️ Alcancé el máximo de pasos para esta pregunta. Intenta preguntarlo de forma más concreta."

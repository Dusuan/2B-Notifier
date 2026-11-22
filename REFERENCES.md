# Referencias y Patrones de Arquitectura (REFERENCES.md)

Este documento centraliza configuraciones de referencia, snippets de código, selectores, ASINs de prueba, enlaces de documentación y estrategias anti-baneo / evasión de WAF para **2B-Notifier** (antes Pokenotify).

---

## 1. Documentación Oficial y Enlaces Clave
- **Twilio WhatsApp API Quickstart (Python)**: https://www.twilio.com/docs/whatsapp/quickstart/python
- **Twilio Python SDK**: https://github.com/twilio/twilio-python
- **BeautifulSoup4 Docs**: https://beautiful-soup-4.readthedocs.io/en/latest/
- **Requests Docs**: https://requests.readthedocs.io/en/latest/

---

## 2. Tiendas Monitoreadas y Parámetros

### Amazon México (amazon.com.mx)
- **URL Base de Producto**: `https://www.amazon.com.mx/dp/{ASIN}`
- **ASINs de Prueba / Monitoreo (TCG Pokémon)**:
  - `B0CQV49Z5X` (Ejemplo Pokémon TCG Box / ETB)
  - `B0DFZ2M1R6` (Pokémon TCG Booster Bundle / ETB referencia)
  - *ASINs dinámicos configurables por variable de entorno o lista*
- **Estructura típica de selectores (HTML / BS4)**:
  - Contenedor de disponibilidad: `#availability span` (ej. "Disponible.", "No disponible por el momento.")
  - Contenedor de precio: `.a-price .a-offscreen`, `#priceblock_ourprice`, `#priceblock_dealprice`
  - Vendedor / Sold by: `#merchant-info`, `#tabular-buybox .tabular-buybox-text` (para verificar que sea "Vendido y enviado por Amazon México")
  - Botón agregar al carrito: `#add-to-cart-button`

### Costco México (costco.com.mx)
- **URL Base de Búsqueda / Catálogo**: `https://www.costco.com.mx/search?text=pokemon`
- **Categoría Juguetes / Coleccionables**: `https://www.costco.com.mx/Juguetes-y-Bebes/Juguetes/c/cos_10.1`
- **Estructura típica de selectores (HTML / BS4)**:
  - Tarjetas de producto: `product-tile`, `div.product-list-item`, `div.thumbnail`
  - Título del producto: `span.description a`, `.product-name`
  - Stock / Estado: Badge "Agotado" (`span.out-of-stock`, `div.product-out-of-stock`), botón "Agregar" disponible vs deshabilitado
  - Precio: `.product-price .price`, `span.price-value`

---

## 3. Estrategias de Evasión de WAF (Cloudflare, Akamai, PerimeterX)
Amazon y Costco emplean WAFs y sistemas anti-bot que detectan requests automatizados (devolviendo HTTP 403, 503 o páginas con CAPTCHA).

### Cabeceras HTTP (Headers) Realistas
Nunca enviar peticiones con el `User-Agent` por defecto de `python-requests/2.x`.
```python
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}
```

### Rotación de User-Agents y Jitter
- Definir un pool de User-Agents recientes (Chrome, Firefox, Safari en Windows y macOS).
- **Jitter en los intervalos**: No hacer peticiones exactamente cada $N$ segundos fijos. Agregar una variación aleatoria:
  `delay = base_interval + random.uniform(-10, 15)`.

### Manejo de Sesiones
- Usar `requests.Session()` para mantener cookies de sesión entre llamadas si es necesario.
- Manejo exponencial de reintentos (`urllib3.util.retry.Retry` o backoff custom ante HTTP 429/503).

---

## 4. Snippet de Referencia: Twilio WhatsApp Client
```python
from twilio.rest import Client
import logging

def send_whatsapp_alert(account_sid: str, auth_token: str, from_number: str, to_number: str, body: str) -> bool:
    """
    Envía un mensaje de alerta a través de la API de Twilio WhatsApp.
    Requiere prefijos 'whatsapp:' en from_number y to_number.
    """
    try:
        from_formatted = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
        to_formatted = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
        
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=body,
            from_=from_formatted,
            to=to_formatted
        )
        logging.info(f"Alerta enviada exitosamente. SID: {message.sid}")
        return True
    except Exception as e:
        logging.error(f"Error al enviar alerta por Twilio WhatsApp: {e}")
        return False
```

---

## 5. Guía de Configuración: Twilio WhatsApp API

Existen dos modalidades para utilizar la API de Twilio WhatsApp:

### Opción A: Twilio WhatsApp Sandbox (Recomendada para Alertas Personales)
Ideal para uso individual o desarrollo sin tramitar aprobación de marca con Meta.
1. Crear cuenta gratuita en [twilio.com](https://www.twilio.com/).
2. Ir a **Develop > Messaging > Try it out > Send a WhatsApp message**.
3. Notarás un número asignado (ej. `+1 415 523 8886`) y un código de vinculación único (ej. `join <palabra-clave>`).
4. Desde tu teléfono personal de WhatsApp, envía el mensaje `join <palabra-clave>` al número asignado de Twilio para autorizar la recepción de alertas.
5. Obtener los valores para `.env`:
   - `TWILIO_SID`: Visible en la consola principal de Twilio (**Account SID**, empieza con `AC...`).
   - `TWILIO_AUTH`: Visible en la consola principal de Twilio (**Auth Token**).
   - `TWILIO_FROM`: `whatsapp:+14155238886` (número del sandbox).
   - `TWILIO_TO`: `whatsapp:+521XXXXXXXXXX` (tu número en formato E.164 con código de país).

### Opción B: Twilio WhatsApp Sender Propio (Producción)
Requiere cuenta empresarial de Meta (Facebook Business Manager):
1. En Twilio Console: **Messaging > Senders > WhatsApp Senders**.
2. Solicitar un "WhatsApp Business Profile".
3. Verificar tu empresa en Meta Business Manager y registrar un número de teléfono exclusivo (que no tenga WhatsApp activo en la app normal).
4. El `TWILIO_FROM` será tu número aprobado: `whatsapp:+52XXXXXXXXXX`.

---

## 6. Guía de Despliegue en AWS Cloud (EC2 Free Tier)

Para mantener el worker corriendo 24/7 en AWS de forma gratuita:

1. **Lanzar Instancia**:
   - En la consola de AWS EC2, seleccionar **Launch Instance**.
   - Nombre: `pokenotify-worker`.
   - AMI: **Amazon Linux 2023** o **Ubuntu 22.04 LTS** (Ambas aptas para Free Tier).
   - Tipo de Instancia: `t2.micro` (o `t3.micro` según región elegible).
   - Key Pair: Crear y descargar archivo `.pem` para conexión SSH.
   - Security Group: Solo puerto `22` (SSH) restringido a tu IP. No requiere puertos web abiertos.
2. **Conexión SSH**:
   ```bash
   chmod 400 mi-llave.pem
   ssh -i mi-llave.pem ec2-user@<IP_PUBLICA_EC2>   # en Amazon Linux
   # o: ssh -i mi-llave.pem ubuntu@<IP_PUBLICA_EC2>    # en Ubuntu
   ```
3. **Instalación de Docker y Docker Compose**:
   ```bash
   # Amazon Linux 2023
   sudo dnf update -y
   sudo dnf install -y docker git
   sudo systemctl enable --now docker
   sudo usermod -aG docker $USER
   # Instalar Docker Compose v2
   sudo mkdir -p /usr/local/lib/docker/cli-plugins
   sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
   sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
   newgrp docker
   ```
4. **Despliegue del Proyecto**:
   ```bash
   git clone <URL_DE_TU_REPOSITORIO> pokenotify
   cd pokenotify
   cp .env.example .env
   nano .env   # colocar credenciales de Twilio
   docker compose up -d --build
   docker compose logs -f
   ```


---

## 7. Agente IA y Clash of Clans (2B-Notifier, verificado 2026-11-22)

### Gemini API (free tier)
- Modelos y estado: https://ai.google.dev/gemini-api/docs/models (ahora redirige a `aistudio.google.com/docs/models`).
  - Estables con free tier al 2026-11-22: `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`. Default del proyecto: `gemini-3.5-flash-lite`.
  - `gemini-2.5-flash` enruta a `gemini-3.5-flash-lite` desde 2026-12-01. No hardcodear: usar `GEMINI_MODEL`.
  - Los límites RPM/RPD del free tier se ven en AI Studio → Rate limits (son por proyecto y cambian). Reportes de oct-2026: Flash-Lite ~15 RPM / 500 RPD; 3.8 Flash ~5 RPM / 20 RPD.
- SDK `google-genai` (v3.6.1). Function calling manual:
```python
from google import genai
from google.genai import types
client = genai.Client(api_key=KEY)
cfg = types.GenerateContentConfig(
    system_instruction=PROMPT,
    tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
        name="get_player", description="...", parameters_json_schema={"type": "object", "properties": {}})])],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
for fc in resp.function_calls or []:
    part = types.Part.from_function_response(name=fc.name, response={"result": run(fc.name, fc.args)})
# errores: google.genai.errors.APIError (.code == 429 → cuota)
```

### Clash of Clans API
- Portal: https://developer.clashofclans.com (crear llave con la IP pública de la VM: `curl -s ifconfig.me` en la VM).
- Endpoint: `GET https://api.clashofclans.com/v1/players/%23TAG` + `Authorization: Bearer <token>`. 403 = llave inválida o IP no permitida.
- Si la IP cambia y no se quiere regenerar la llave: proxy de RoyaleAPI para IPs dinámicas (obtener URL base e IP actuales desde https://docs.royaleapi.com y su Discord; no hardcodear de memoria) y apuntar `COC_API_BASE`.
- `coc.py` (v4.0.0) trae datos de juego de coc.guide, pero requiere login con email/contraseña; no se usa para evitar dependencias y credenciales extra.

### Datos estáticos del juego
- Dataset: https://github.com/chiefpansancolt/clash-of-clans-data (`data/home/{heroes,troops,spells,pets,siege-machines,hero-equipment}/*.json`).
  - Tropas/hechizos/máquinas/mascotas: `levels[].townHallRequired`. Héroes: `levels[].heroHallLevelRequired` → `army-buildings/hero-hall.json`. Equipo: `levels[].blacksmithLevelRequired` → `army-buildings/blacksmith.json`.
- Regenerar tras cada update del juego: `python tools/build_game_data.py --ref main` (luego fijar el nuevo SHA en `PINNED_REF`).

### Blog oficial de Supercell (sin RSS)
- Listado: `https://supercell.com/en/games/clashofclans/blog/` → JSON en `<script id="__NEXT_DATA__">` → `props.pageProps.articles[]` (`title`, `linkUrl`, `publishDate`).
- Artículo: `props.pageProps.openGraph.description` (resumen oficial) y `bodyCollection` (texto completo).
- Forzar `response.encoding = "utf-8"` (el servidor no declara charset).

### Telegram Bot API
- Docs: https://core.telegram.org/bots/api. Long polling: `getUpdates` con `offset` y `timeout=30`; requiere que no haya webhook (`deleteWebhook`).
- Límite de mensaje: 4096 caracteres. `sendChatAction(action="typing")` dura ~5 s.
- Librerías evaluadas (no usadas): `python-telegram-bot` 22.8, `aiogram` 3.33.0.

### Google Cloud desde Claude Code (MCP)
- `@google-cloud/gcloud-mcp` (preview, https://github.com/googleapis/gcloud-mcp): expone `run_gcloud_command`; requiere gcloud CLI local autenticado. Instalado en `~/.local/google-cloud-sdk` y registrado con `claude mcp add gcloud -s local`.
- Compute Engine remote MCP (`https://compute.googleapis.com/mcp`): sólo ciclo de vida/lectura de VMs (sin SSH ni metadata); requiere cliente OAuth propio.

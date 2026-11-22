# 🤖 2B-Notifier — Bot + Agente IA de Notificaciones Personales

*(antes Pokenotify)*

Bot personal de Telegram con un agente de IA (Gemini free tier) que corre 24/7 en una VM gratuita de Google Cloud y te avisa de lo que tú consideras relevante:

- 🃏 **Stock de Pokémon TCG a MSRP** en Costco México y Amazon México (monitor original de Pokenotify, con botones 1-Click).
- 🏰 **Clash of Clans**: plan de mejoras con *tus* datos reales (calculado por código, no adivinado por la IA), estado de la cuenta y si ya estás listo para subir de TH.
- 📰 **Noticias oficiales de Clash of Clans**: push automático cuando Supercell publica un post nuevo.
- 💬 **Chat libre**: "¿qué mejoro primero?", "¿qué hay de nuevo en el juego?", "deja de mandarme noticias de CoC", "guarda una nota: juego guerra los fines de semana".

---

## 🛠️ Stack
- Python 3.12 (`python:3.12-slim`), Docker Compose
- IA: Gemini API free tier (`google-genai`, modelo en `GEMINI_MODEL`, default `gemini-3.5-flash-lite`)
- Telegram Bot API (long polling con `requests`)
- API oficial de Clash of Clans + datos estáticos de [chiefpansancolt/clash-of-clans-data](https://github.com/chiefpansancolt/clash-of-clans-data) (commit `7afaa03`, 2026-11-06)
- Scraping: `requests`, `beautifulsoup4`
- Hosting: VM GCP Compute Engine `e2-micro` (Always Free)

Arquitectura y decisiones: ver [`SPEC.md`](SPEC.md). Referencias técnicas: [`REFERENCES.md`](REFERENCES.md).

---

## 💬 Uso en Telegram

| Comando | Qué hace | ¿Gasta cuota IA? |
|---|---|---|
| `/start #TUTAG` | Guarda tu player tag de Clash of Clans | No |
| `/status` | Resumen de tu cuenta (TH, héroes, trofeos, clan) | No |
| `/next` | Plan de mejoras: siguiente por cola, prioridades, ¿listo para subir de TH? | No |
| `/news` | Últimos posts oficiales con fecha y enlace | No |
| `/pokemon` | Estado del monitor de stock Pokémon | No |
| Cualquier otro texto | Va al agente (Gemini + herramientas) | Sí (1–5 llamadas) |

El bot **sólo responde a tu usuario** (`TELEGRAM_ALLOWED_USER_IDS`, por defecto tu `TELEGRAM_CHAT_ID`). Mensajes de cualquier otra persona se ignoran y quedan en el log.

---

## 🔑 Paso 0: Conseguir las llaves (una sola vez)

1. **Telegram** (reutilizas el bot de Pokenotify): en @BotFather → `/mybots` → tu bot → *Edit Bot* → *Edit Name* → `2B-Notifier`. Opcional: *Edit Commands* y pega:
   ```
   start - Guardar o ver tu player tag
   status - Resumen de tu cuenta de Clash of Clans
   next - Qué mejorar ahora
   news - Últimas noticias oficiales de Clash of Clans
   pokemon - Estado del monitor de stock Pokémon
   ```
2. **Gemini API key (gratis)**: entra a https://aistudio.google.com/apikey → *Create API key*. Usa un proyecto **sin facturación** para quedarte en el free tier. Revisa tus límites en AI Studio → *Rate limits*.
3. **IP pública de tu VM**: en la consola de GCP → Compute Engine → VM instances → columna *External IP* (o en la VM: `curl -s ifconfig.me`).
4. **Clash of Clans API key**: https://developer.clashofclans.com → *Register/Log in* → *My Account* → *Create New Key* → en *Allowed IP Addresses* pon la IP del paso 3 → copia el token.
   > Si la IP de la VM cambia (por ejemplo al recrearla), crea una llave nueva con la IP nueva. Mientras la VM sólo se reinicie, la IP efímera normalmente se mantiene; para fijarla puedes "promoverla" a estática en *VPC network → IP addresses* (revisa en Billing si te genera costo).
5. **Tu player tag**: en el juego, toca tu perfil → el tag está bajo tu nombre (ej. `#2PP0JQ`).

---

## 🚀 Despliegue en la VM de Google Cloud (paso a paso)

### 1. En tu computadora local: subir el código
```bash
git push
```

### 2. En la VM (botón **SSH** en Compute Engine → VM instances)
```bash
cd ~/Pokenotify                      # carpeta donde clonaste el repo originalmente
git remote set-url origin https://github.com/Dusuan/2B-Notifier.git
git pull
nano .env                            # agrega las variables nuevas (abajo)
```
Variables nuevas a añadir al `.env` existente (las de Telegram y Pokémon se quedan igual):
```env
GEMINI_API_KEY=tu_llave_de_ai_studio
GEMINI_MODEL=gemini-3.5-flash-lite
COC_API_TOKEN=tu_token_de_developer_clashofclans
COC_PLAYER_TAG=#TUTAG
# opcional: TELEGRAM_ALLOWED_USER_IDS=123456789
```

### 3. Reemplazar el contenedor viejo por el nuevo
```bash
docker-compose down                  # detiene "pokenotify-worker"
docker-compose up -d --build --remove-orphans
docker-compose logs -f               # salir con Ctrl + C
```
Debes ver `Bot de Telegram conectado como @tu_bot (long polling)` y `Noticias refrescadas: N posts`.

### 4. Red de seguridad de costos (recomendado)
Consola GCP → **Billing → Budgets & alerts → Create budget** → monto `$1 USD` → alertas al 50/90/100% a tu correo.

### 5. Probar desde Telegram
`/start #TUTAG` → `/status` → `/next` → `/news` → "¿qué debo mejorar primero y por qué?"

---

## 🔁 CD automático (despliegue con sólo `git push`)

La VM revisa GitHub cada 5 minutos (`cron` + `deploy/autodeploy.sh`, sin sudo y sin guardar credenciales de GCP en GitHub). Si `master` tiene commits nuevos:

1. `git pull` (sólo fast-forward) → `docker compose build`
2. **Corre los tests** dentro de la imagen nueva
3. ✅ Pasan → `up -d --remove-orphans` y te llega a Telegram `🚀 2B-Notifier desplegado: <commit>`
4. ❌ Fallan → vuelve al commit anterior, **el bot viejo sigue corriendo**, te llega `❌ ... falló` y no reintenta ese commit (sólo uno nuevo)

Instalación (una vez, en la VM, después del primer despliegue manual):
```bash
cd ~/Pokenotify && bash deploy/install_autodeploy.sh
tail -f ~/2b-notifier-deploy.log        # ver despliegues
```
Desactivar: `crontab -e` y borrar la línea de `autodeploy.sh`. Forzar un reintento de un commit fallido: `rm .deploy_failed`.

---

## 🧪 Pruebas y desarrollo local

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests        # pruebas del calculador y del bucle del agente
.venv/bin/python cli.py --tool get_latest_news        # ejecutar una herramienta sin IA
.venv/bin/python cli.py "¿qué hay de nuevo en el juego?"  # probar el agente sin Telegram (requiere GEMINI_API_KEY)
.venv/bin/python test_alert.py                        # alerta de prueba a tus canales
```
> Desde tu PC la API de CoC dará 403 salvo que la llave incluya también tu IP de casa (puedes crear una segunda llave para desarrollo).

---

## 🔄 Actualizar los datos del juego (tras cada update de Clash of Clans)
```bash
python tools/build_game_data.py --ref main   # baja la última versión del dataset
python -m unittest discover -s tests
git add data/game_data.json && git commit -m "chore: actualiza datos de juego CoC"
```
Luego fija el SHA nuevo en `PINNED_REF` de `tools/build_game_data.py`. Las reglas de prioridad se ajustan en `agent/priorities.json` (sin tocar código).

---

## 📋 Comandos de Mantenimiento (en la VM)

| Acción | Comando |
|---|---|
| Ver logs en tiempo real | `docker-compose logs -f` |
| Ver qué herramientas usó el agente | `docker-compose logs --tail=200 \| grep "\[Agente\]"` |
| Reiniciar (tras editar `.env`) | `docker-compose restart` |
| Actualizar código | `git pull && docker-compose up -d --build` |
| Alerta de prueba | `docker-compose exec notifier python test_alert.py` |
| Ver estado guardado | `docker-compose exec notifier cat /app/state/state.json` |

---

## 🛡️ Políticas
- **Pokémon**: silencio sin stock; alerta inmediata con stock a MSRP; cooldown de 12 h por producto.
- **Noticias CoC**: push sólo de posts nuevos (no del histórico al primer arranque), revisión cada 6 h.
- **IA**: máximo 5 pasos por mensaje y 400 llamadas/día (configurable); si se agota la cuota responde con un aviso, nunca se queda en bucle.
- **Sin inventos**: si falta un dato (p. ej. niveles de muros, que la API no expone) el bot lo dice.
- Cada tipo de push se puede apagar desde el chat ("ya no me mandes alertas de Pokémon").

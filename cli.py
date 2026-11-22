#!/usr/bin/env python3
"""
CLI local para probar el agente sin Telegram.
Uso:
    python cli.py "¿qué debo mejorar ahora?"
    python cli.py            # modo interactivo
    python cli.py --tool get_upgrade_plan   # ejecuta una herramienta directo (sin IA)
"""
import json
import sys
from agent import core, tools


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--tool":
        print(json.dumps(tools.call(sys.argv[2], {}), ensure_ascii=False, indent=2))
        return
    if len(sys.argv) > 1:
        print(core.answer(0, " ".join(sys.argv[1:])))
        return
    print("2B-Notifier CLI — escribe 'salir' para terminar.")
    while True:
        try:
            msg = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in ("salir", "exit", "quit"):
            break
        if msg:
            print(core.answer(0, msg))


if __name__ == "__main__":
    main()

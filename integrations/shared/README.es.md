[English](README.md) · **Español**

# Biblioteca cliente compartida de las integraciones de agentes

Sobre lo que se construye cada plugin de agentes de MimirSynth (`integrations/<agente>/`): la configuración compartida (`~/.config/mimirsynth/config.json`), las llamadas a un brain (recall, novedades, whoami, propuestas), la redacción de secretos con el propio detector del servidor, los tiempos máximos con fallo en abierto y la captura opcional de sesiones. El contrato y la API están documentados en [`docs/es/AGENT_CLIENT.md`](../../docs/es/AGENT_CLIENT.md).

| Carpeta | Qué |
|---|---|
| `python/mimirsynth_agent/` | La biblioteca en Python, solo con la biblioteca estándar. La fuente de verdad |
| `typescript/` | Su port a TypeScript para agentes de JavaScript (`npm test` pasa los casos del contrato, `npm run check` los tipos) |
| `contract/cases.json` | Los casos que toda implementación tiene que pasar |
| `vendor.py` | Copia la biblioteca de Python en cada plugin (`--check` lista las copias desfasadas) |

Un plugin de Python lleva una copia exacta de `python/mimirsynth_agent/`, porque un agente solo instala la carpeta del plugin. Después de cambiar la biblioteca, o `api/mimirsynth/secretscan.py`, ejecuta:

```bash
python integrations/shared/vendor.py
```

y sube la versión de cada plugin que haya cambiado (en Claude Code, `plugin/.claude-plugin/plugin.json`): un agente solo actualiza un plugin instalado cuando cambia su versión.

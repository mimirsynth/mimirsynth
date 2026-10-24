# Contribuir a MimirSynth

¡Gracias por querer ayudar! MimirSynth está en desarrollo activo: antes de empezar con un cambio grande, abre un *issue* o una *discussion* para comentarlo.

## Preparar el entorno
```bash
git clone https://github.com/MimirSynth/mimirsynth.git && cd mimirsynth
cd api && uv venv && uv pip install -e . pytest && .venv/bin/pytest -q     # API: los tests usan SQLite; los que necesitan PostgreSQL o FalkorDB se omiten solos
cd ../web && npm install && npm run build                                   # web: incluye el guardián de interfaz (check:ui)
```
Para desarrollar con recarga: `uvicorn mimirsynth.main:app --port 8010` (con `MIMIRSYNTH_AUTH_MODE=off`, solo en desarrollo) y `npm run dev` en `web/`.

## Reglas
- **Tests:** todo cambio de comportamiento lleva su test. Un cambio en el esquema lleva su migración de Alembic.
- **Interfaz:** las pantallas se construyen solo con los componentes de `web/src/ui/` (lee su `README.md`). `npm run check:ui` falla si usas estilos en línea, elementos HTML nativos o colores literales.
- **Textos:** la interfaz está en español. No introduzcas nombres, direcciones ni datos de tu infraestructura en el código, los tests ni la documentación: usa ejemplos genéricos.
- **Secretos:** nunca los subas. Los valores sensibles viven en la base de datos cifrados, no en el repositorio.
- **Commits:** mensajes en inglés con el estilo `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.

## Pull requests
Una PR, un propósito. Describe el porqué, enlaza el *issue* y marca la lista de la plantilla. La integración continua debe pasar.

## Licencia
Al contribuir aceptas que tu aportación se publique bajo [Apache-2.0](LICENSE).

[English](../../CONTRIBUTING.md) · **Español**

# Contribuir a MimirSynth

¡Gracias por querer ayudar! MimirSynth está en desarrollo activo: antes de empezar con un cambio grande, abre un *issue* o una *discussion* para comentarlo.

## Idioma
MimirSynth trabaja **primero en inglés** y **cuida el castellano**: el inglés es el idioma de trabajo para que cualquiera pueda participar, y como la mayoría de quienes rodean el proyecto hablan español, el castellano sigue siendo un idioma de primera para los usuarios.

- **En inglés:** los mensajes de commit, el título y la descripción de las *pull requests*, el título de los *issues*, las etiquetas, el código (identificadores, comentarios, docstrings, mensajes de log) y la versión original de cada documento.
- **El castellano es bienvenido** en *issues*, *discussions* y comentarios. Si no te sientes cómodo escribiendo en inglés, escribe en castellano: alguien del equipo añadirá un título o un resumen en inglés y el original se queda como está. La conversación puede seguir en cualquiera de los dos idiomas.
- **Los comentarios en castellano que ya hay** en el código se traducen cuando tocas ese código, no en PR que solo traducen y chocan con el trabajo de los demás.
- **La documentación** se escribe primero en inglés y se mantiene traducida al castellano (ver [Documentación](#documentación)).
- **La interfaz** está completa en inglés y en castellano. De momento sus catálogos de traducción todavía usan el texto en español como clave (ver *Traducciones* más abajo); está previsto pasar el original al inglés.

## Preparar el entorno
```bash
git clone https://github.com/MimirSynth/mimirsynth.git && cd mimirsynth
cd api && uv venv && uv pip install -e . pytest && .venv/bin/pytest -q     # API: los tests usan SQLite; los que necesitan PostgreSQL o FalkorDB se omiten solos
cd ../web && npm install && npm run build                                   # web: incluye los guardianes de interfaz (check:ui e i18n)
```
Para pasar los tests de la API como el CI, arranca FalkorDB (`docker run -d -p 6379:6379 falkordb/falkordb:v4.22.0`) y define `MIMIRSYNTH_TEST_FALKOR=localhost`. En Windows el intérprete es `.venv\Scripts\python` (`.venv/Scripts/python -m pytest -q`), y la suite también pasa allí. Si un test escribe un fichero de texto, pásale `encoding="utf-8"` (y `newline=""` si importan los bytes exactos): si no, Windows lo escribe con su propia página de códigos y con CRLF.

Para levantar el stack completo desde tu copia (construye la imagen en local en vez de descargar la oficial):
```bash
cp .env.example .env     # define POSTGRES_PASSWORD y MIMIRSYNTH_SESSION_SECRET
docker compose -f docker-compose.yml -f docker-compose.build.yml --profile bundled up -d --build
```
Para desarrollar con recarga: `uvicorn mimirsynth.main:app --port 8010` (con `MIMIRSYNTH_AUTH_MODE=off`, solo en desarrollo) y `npm run dev` en `web/`.

## Reglas
- **Tests:** todo cambio de comportamiento lleva su test. Un cambio en el esquema lleva su migración de Alembic, que parte de la última: un test falla si hay dos cabezas, así que la segunda de dos PR con migración renumera la suya.
- **Interfaz:** las pantallas se construyen solo con los componentes de `web/src/ui/` (lee su `README.md`). `npm run check:ui` falla si usas estilos en línea, elementos HTML nativos o colores literales.
- **Traducciones:** todo texto visible pasa por `t("…")`. El idioma original es el español (el propio texto es la clave) y el catálogo inglés es `web/src/i18n/en.json`; los mensajes que muestra el servidor van en `web/src/i18n/en.server.json`, que la API usa también para responder en el idioma de quien llama (los textos para agentes que no son una `HTTPException` se marcan con `i18n.tr("…", lang)`). `npm run i18n` comprueba que no quede nada sin traducir y que `en.json` esté en orden alfabético (`node scripts/i18n.mjs --sort` lo ordena, para que las claves que añaden dos PR no choquen al final del fichero), y `python -m mimirsynth.i18n_extract --missing` lista los textos del servidor que faltan. Para añadir un idioma, añade su catálogo y una entrada en `LANGUAGES` (`web/src/i18n/index.ts`).
- **Textos y datos:** no introduzcas nombres, direcciones ni datos de tu infraestructura en el código, los tests ni la documentación: usa ejemplos genéricos.
- **Secretos:** nunca los subas. Los valores sensibles viven en la base de datos cifrados, no en el repositorio.
- **Commits:** mensajes en inglés con el estilo `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`. El título de la PR sigue el mismo estilo, porque las PR se fusionan con *squash* y su título acaba siendo el commit de `main`.

## Documentación
| Dónde | Qué | Idiomas |
|---|---|---|
| `README.md` / `README.es.md` | Qué es MimirSynth y el arranque rápido | Inglés y castellano |
| `docs/` / `docs/es/` | Documentación técnica que acompaña al código | Inglés y castellano |
| `docs/wiki/` | La guía de usuario, que se publica en la [wiki](https://github.com/MimirSynth/mimirsynth/wiki) | Páginas en inglés y en castellano, por parejas |
| `CHANGELOG.md` | Notas de cada versión, que se escriben al publicarla (ver más abajo) | Inglés |

- Un cambio de comportamiento actualiza la documentación a la que afecta **en la misma PR**, en los dos idiomas. Si no puedes escribir una de las dos versiones, dilo en la PR y alguien del equipo la añadirá antes de fusionarla.
- **La wiki se edita aquí, no en GitHub.** Cada página de `docs/wiki/` se publica en la wiki cuando llega a `main`, y la publicación sobrescribe lo que se haya editado directamente en la wiki. Las páginas en inglés tienen nombre en inglés (`Quick-start.md`) y las páginas en castellano nombre en castellano (`Guía-rápida.md`); cada una empieza con un enlace a su pareja, y los enlaces entre páginas usan `[[Nombre de página]]`. Una página nueva se añade a `docs/wiki/_index.yml`: en una sección de la barra lateral (y en las listas de la portada si es una entrada principal), o en `unlisted`. `_Sidebar.md` y las listas de páginas de `Home.md` e `Inicio.md` se generan desde ese fichero con `python scripts/wiki_index.py` y nunca se editan a mano; un test falla si no están al día o si falta alguna página en el índice.

## Pull requests
Una PR, un propósito. Explica el porqué, enlaza el *issue* y marca la lista de la plantilla. La integración continua debe pasar.

**Changelog.** Una PR no edita `CHANGELOG.md`. Su entrada va en la sección `## Changelog` de su descripción, una línea por entrada: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` o `Security`, dos puntos y el texto en inglés, tal como debe quedar en el changelog (una línea que no empieza por un tipo continúa la entrada anterior). La comprobación *PR* falla si no la hay; un cambio que no necesita entrada (CI, solo documentación, una actualización de dependencias) lleva en su lugar la etiqueta `no-changelog`, y las PR de Dependabot quedan exentas. Las entradas se escriben en `CHANGELOG.md` al publicar una versión, así que `[Unreleased]` en el fichero no está al día entre versiones: la fuente son las PR fusionadas, y `python scripts/changelog.py --preview` enseña lo que diría la próxima versión.

## Licencia
Al contribuir aceptas que tu aportación se publique bajo [Apache-2.0](../../LICENSE).

## Publicar una versión (mantenedores)
1. Pon la nueva versión en `api/pyproject.toml` (la única fuente de verdad: la leen la aplicación, las etiquetas de la imagen y la comprobación de la release) y ejecuta `python scripts/changelog.py --release X.Y.Z`: lee las secciones `## Changelog` de las PR fusionadas desde la última etiqueta (por la API de GitHub, con `GITHUB_TOKEN`, `GH_TOKEN` o `gh auth token`) y las escribe bajo un nuevo encabezado `## [X.Y.Z] - fecha`, en sus subsecciones y con el número de cada PR. Avisa de las PR fusionadas que debían tener entrada y no la tienen. Revisa el resultado; todo esto va en la PR de la versión.
2. Haz commit, crea la etiqueta y súbela: `git tag vX.Y.Z && git push origin vX.Y.Z`. Una versión previa usa `vX.Y.Z-rc.N` (no mueve `latest`).
3. El workflow *Release* comprueba que la etiqueta coincide con la versión, construye la imagen para `linux/amd64` y `linux/arm64`, la sube a `ghcr.io/mimirsynth/mimirsynth` y crea la release de GitHub a partir del changelog.

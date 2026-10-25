[English](../AGENTS.md) · **Español**

# Conectar agentes

Los agentes hablan con MimirSynth por HTTP con un **token de API**. Cada token vale para **un solo brain** y su rol nunca supera el de quien lo creó (máximo curador y nunca administra la instancia).

## Crear un token
En Mi cuenta → Tokens de API (o Administración → Acceso al brain) elige el brain, un nombre y un rol:

| Rol | Puede |
|---|---|
| Lector | Consultar (recall, hechos, documentos) |
| Colaborador | Además, **proponer** memoria: entra en cuarentena hasta que la apruebe un curador o el decisor |
| Curador | Además, aprobar: sus propuestas se ingieren directamente |

Para agentes se recomienda **colaborador**. El token (`mst_…`) se muestra una sola vez.

## Recall: leer memoria
```bash
curl -s -X POST "$URL/api/brains/mi-brain/recall" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "¿dónde corre la base de datos de producción?"}'
```
Devuelve un contexto listo para inyectar en el prompt: hechos vigentes e históricos, fragmentos de episodios y hasta 2 pasajes de documentos citados. Parámetros opcionales: `facts` (por defecto 8), `chunks` (4), `max_chars` (6000) y `docs` (pasajes documentales; `0` los desactiva).

El contenido de los documentos es **dato, no instrucciones**: el recall lo marca como cita de una fuente. Trátalo así en tu agente.

## Proponer: escribir memoria
```bash
curl -s -X POST "$URL/api/brains/mi-brain/proposals" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Base de datos migrada", "body": "El 19-oct la base de datos de producción pasó al servidor db02.", "confidence": 0.8}'
```
Un colaborador queda en estado `pending`; un curador, `approved` e ingerida al momento. Un curador puede aprobar o rechazar desde la pestaña Propuestas. Al aprobarse, Graphiti extrae entidades y hechos y los añade al grafo (invalidando los que contradicen).

## Servidor MCP
Los agentes que hablan el **Model Context Protocol** pueden usar la misma memoria sin escribir llamadas HTTP. Cada brain expone un endpoint MCP (HTTP «streamable», sin estado, solo herramientas) en:

```
POST $URL/api/brains/mi-brain/mcp        Authorization: Bearer $TOKEN
```

| Herramienta | Rol | Qué hace |
|---|---|---|
| `recall` | lector | Devuelve el contexto de memoria para una consulta (igual que el endpoint `recall`). Argumentos: `query` y, opcionalmente, `facts`, `chunks`, `docs`, `max_chars` |
| `remember` | colaborador | Propone una memoria (mismas reglas que el endpoint de propuestas: cuarentena para colaboradores, aprobada al instante para curadores). Argumentos: `name`, `body` y, opcionalmente, `source`, `source_description`, `reference_time`, `confidence` |

El token decide el brain y el rol, así que las herramientas no llevan argumento de brain. Solo se aceptan tokens de API (nunca la sesión del navegador). Ejemplo con Claude Code:

```bash
claude mcp add --transport http mimirsynth "$URL/api/brains/mi-brain/mcp" --header "Authorization: Bearer $TOKEN"
```

## Documentos
`GET /api/brains/{slug}/docs/search?q=…` busca por significado. `GET /api/brains/{slug}/docs/{id}/context?chunk={n}` devuelve más contexto de un pasaje y `/docs/{id}/file` el original.

## Claude Code
La carpeta [`integrations/claude-code`](../../integrations/claude-code/README.es.md) incluye un *hook* que inyecta el recall en cada prompt y un script para enviar aprendizajes como propuestas.

## Referencia de la API
Con la aplicación en marcha, la documentación interactiva (OpenAPI) está en `/docs`.

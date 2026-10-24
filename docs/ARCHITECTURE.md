# Arquitectura

MimirSynth es una capa de memoria para agentes de IA. Se apoya en [Graphiti](https://github.com/getzep/graphiti) (grafo de conocimiento temporal) sobre FalkorDB y añade lo que un grafo solo no da: usuarios y permisos, cuarentena de lo que escriben los agentes, recall híbrido, memoria documental y una interfaz web.

## Idea central

Los hechos no se sobrescriben: se **invalidan** y se conserva su historial (modelo bi-temporal: cuándo ocurrió y cuándo se supo). Cada tipo de memoria del marco cognitivo [CoALA](https://arxiv.org/abs/2309.02427) tiene su sitio:

| Memoria | Qué guarda | Dónde |
|---|---|---|
| Episódica | Qué pasó, inmutable | Episodios de Graphiti, más un índice de su texto en PostgreSQL (pgvector + búsqueda de texto completo) |
| Semántica | Entidades y hechos con fechas de validez | Graphiti sobre FalkorDB |
| Documental | Qué dicen los documentos | Trozos con vectores y texto completo en PostgreSQL; originales en un volumen. Ver [DOCUMENTS.md](DOCUMENTS.md) |

## Componentes

```
agentes / plugins ──token de API──┐
navegador ────────cuenta u OIDC───┤
                                  ▼
                        ┌──────────────────┐        ┌────────────────┐
                        │ MimirSynth       │───────▶│ FalkorDB       │ un grafo por brain
                        │ API (FastAPI)    │        └────────────────┘
                        │ + UI (React)     │        ┌────────────────┐
                        │                  │───────▶│ PostgreSQL     │ plano de control,
                        └──────────────────┘        │ + pgvector     │ índices de texto
                           │        │               └────────────────┘
                           ▼        ▼
                  LLM (extracción)  Embeddings   (cualquier endpoint compatible con OpenAI)
```

- **Un solo contenedor** sirve la API y la interfaz; PostgreSQL y FalkorDB son servicios aparte (el `docker-compose.yml` incluye ambos).
- **Ingesta:** `graphiti-core` se usa como librería dentro de la aplicación, sobre el mismo FalkorDB.
- **Proveedores de IA** (LLM, embeddings y decisores) se configuran en la interfaz, con las claves cifradas en la base de datos. Cualquier endpoint compatible con OpenAI sirve (nube, Ollama, un proxy…).

## Brains

Un **brain** es un dominio de conocimiento aislado: su grafo, su ontología (tipos de entidad y relación), su índice de texto, sus miembros y sus tokens. Todo lo que hace la API está acotado a un brain y al usuario autenticado.

## Usuarios y roles

- **Cuentas propias** (email y contraseña con argon2id, bloqueo tras intentos fallidos, invitaciones y recuperación por enlace de un solo uso, correo por SMTP opcional) y **doble factor TOTP** con códigos de recuperación, que el administrador puede exigir.
- **OIDC opcional** (Keycloak, Authentik, Entra ID, PocketID…): solo entra quien ya tiene cuenta o invitación.
- **Rol por brain:** lector < colaborador < curador < administrador < propietario. El administrador de la instancia ve todo.
- **Tokens de API** acotados a un brain, para agentes y plugins; nunca superan el rol de quien los crea y no administran la instancia.
- Las acciones de administración y de acceso quedan en un **registro de auditoría**.

## Escritura: cuarentena de propuestas

Lo que aporta un colaborador o un agente no entra directo al grafo. Crea una **propuesta** con su autor y su confianza:

1. Un **decisor** (modelo de decisión cerrada, con umbral) puede aprobar automáticamente lo claramente factual. Nunca rechaza por su cuenta.
2. Lo dudoso espera a un **curador**, que aprueba o rechaza. Si propone un curador, queda aprobada.
3. Al aprobarse, se **ingiere** con Graphiti (extracción de entidades y hechos con el LLM del brain) mediante un trabajo en cola, con reintentos y progreso.

## Lectura: recall híbrido

Una consulta combina, sin llamar a un LLM:

1. **Hechos** vigentes e históricos del grafo, por similitud de embedding.
2. **Fragmentos del texto original** de los episodios, por vectores y texto completo.
3. **Pasajes de documentos**, con presupuesto y tiempo máximo.
4. Fusión por rango recíproco (RRF) con peso por recencia, y un bloque con la evolución de los hechos de las entidades consultadas.

## Vocabulario

La ontología se define por brain (paquetes de partida en `api/mimirsynth/presets/`). La interfaz permite normalizar alias, fusionar duplicados, retipar entidades y editar los tipos de relación; cada cambio es reversible y queda auditado.

## Trabajos

Ingesta, escaneo de carpetas y reindexado pasan por una cola general con progreso, cancelación y reintento. Los reescaneos programados sin incidencias se purgan solos; los plazos se cambian en Administración → Ajustes.

## Configuración

El entorno solo lleva lo necesario para arrancar y conectar (ver `.env.example`). Todo lo demás se cambia en la interfaz (Administración → Ajustes) y se aplica sin reiniciar; las variables de entorno equivalentes funcionan como valor por defecto. Los secretos guardados en la base de datos se cifran con una clave derivada de `MIMIRSYNTH_SESSION_SECRET`: si cambia, hay que volver a introducirlos.

## Dependencias y licencias

MimirSynth se publica bajo Apache-2.0. Graphiti es Apache-2.0. **FalkorDB es *source-available* (SSPL)**, no una licencia open source permisiva: revisa sus condiciones antes de ofrecer MimirSynth como servicio. El acceso al grafo pasa por una capa propia para poder sustituir el motor en el futuro.

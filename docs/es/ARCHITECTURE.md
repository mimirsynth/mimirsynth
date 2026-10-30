[English](../ARCHITECTURE.md) · **Español**

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

- **Cuentas propias** (email y contraseña con argon2id, bloqueo tras intentos fallidos, invitaciones y recuperación por enlace de un solo uso, correo por SMTP opcional), **doble factor TOTP** con códigos de recuperación, que el administrador puede exigir, y **llaves de acceso** (WebAuthn) para entrar sin contraseña o como segundo paso.
- **OIDC opcional, con uno o varios proveedores** (Keycloak, Authentik, Entra ID, PocketID…): por defecto solo entra quien ya tiene cuenta o invitación; cada proveedor puede permitir, opcionalmente, el alta automática por dominios y conceder roles según sus grupos.
- **Rol por brain:** lector < colaborador < curador < administrador < propietario. El administrador de la instancia ve todo.
- **Tokens de API** acotados a un brain, para agentes y plugins; nunca superan el rol de quien los crea y no administran la instancia.
- Las acciones de administración y de acceso quedan en un **registro de auditoría**.
- **Idioma:** la interfaz y los correos están en inglés y en español, a elección de cada persona.

## Escritura: cuarentena de propuestas

Lo que aporta un colaborador o un agente no entra directo al grafo. Crea una **propuesta** con su autor y su confianza:

1. Un **decisor** (modelo de decisión cerrada, con umbral) puede aprobar automáticamente lo claramente factual. Nunca rechaza por su cuenta.
2. Lo dudoso espera a un **curador**, que aprueba o rechaza. Si propone un curador, queda aprobada.
3. Al aprobarse, se **ingiere** con Graphiti (extracción de entidades y hechos con el LLM del brain) mediante un trabajo en cola, con reintentos y progreso.

### Secretos

Antes de guardar una propuesta (de la interfaz, de la API o de `remember` por MCP) o de indexar un documento, un **detector de secretos** busca credenciales en el texto:

- **Seguros:** formatos inconfundibles (claves de acceso de AWS, tokens de GitHub, GitLab, Slack, npm o Hugging Face, claves de API de Google, Stripe, SendGrid o de proveedores de IA, tokens de bots de Telegram, claves privadas PEM, JWT, cabeceras `Authorization` y contraseñas dentro de una URL).
- **Posibles:** un valor de aspecto aleatorio asignado a una palabra como `password`, `secret` o `token`. Solo se marcan: la entropía por sí sola confundiría sumas, UUID e identificadores de contenedor, que son contenido normal en documentación técnica.

Cada brain elige qué hacer en Administración → Acceso al brain → Secretos:

| Modo | Secretos seguros | Secretos posibles |
|---|---|---|
| **Enmascarar** (por defecto) | Se sustituyen por `[secreto eliminado: tipo]` antes de guardar | Se marcan |
| **Bloquear** | La propuesta se rechaza (422) diciendo qué tipo es; el documento no se indexa y sale del índice | Se marcan |
| **Solo avisar** | Se marcan, sin tocarlos | Se marcan |

Una propuesta con algo marcado no la aprueba el decisor, ni se aprueba al enviarla aunque la mande un curador: espera a que un curador la revise, y ve el aviso en su detalle. En la auditoría y en los trabajos, lo marcado en su título se tapa. El marcador se escribe en el idioma de la instancia, porque queda en la memoria. Las **excepciones** del brain (una por línea) desactivan una regla (`rule:jwt`) o aceptan los valores que encajan con una expresión regular; una expresión que lo aceptaría todo (`.*`) se rechaza al guardarla. **Analizar lo ya guardado** pasa el detector en solo lectura por las propuestas y los documentos indexados del brain y enseña, de cada hallazgo, la regla y el texto que lo precede, nunca el valor: sirve para medir aciertos y falsos positivos antes de cambiar la política. Lo que ya está en el grafo no se analiza, y cambiar la política no reprocesa lo ya guardado: para aplicarla a un documento, reindéxalo.

Ni la auditoría, ni los logs, ni la API guardan o devuelven el valor detectado: solo la regla y su posición. En los documentos se enmascara el texto que se indexa (trozos, vectores y texto normalizado); **el original descargable no se modifica**. El detector (`api/mimirsynth/secretscan.py`) no depende del resto del paquete, para que un cliente pueda llevárselo y redactar antes de enviar.

## Lectura: recall híbrido

Una consulta combina, sin llamar a un LLM:

1. **Hechos** vigentes e históricos del grafo, por similitud de embedding.
2. **Fragmentos del texto original** de los episodios, por vectores y texto completo.
3. **Pasajes de documentos**, con presupuesto y tiempo máximo.
4. Fusión por rango recíproco (RRF) con peso por recencia, y un bloque con la evolución de los hechos de las entidades consultadas.

### Consultas de referencia

Cada brain puede guardar **consultas de referencia** (Preguntar → Consultas de referencia; curadores o superior): una pregunta con los textos que su recall **debe** traer y los que **no** (falsos positivos conocidos), y si la sección de documentos debe salir o no. Un texto cuenta como encontrado si aparece, sin contar mayúsculas ni espacios, en algún resultado; con `fact:`, `chunk:` o `doc:` delante se exige ese tipo.

- **Ejecutar** las mide con los ajustes en vigor: esperados encontrados, falsos positivos y consultas con la sección de documentos al revés (también por tipo), mediana de latencia y diferencia con la ejecución anterior con los ajustes en vigor. La diferencia solo cuenta lo que está en las dos ejecuciones (las mismas consultas y los mismos textos), así que añadir, borrar o editar una consulta no la empeora; empeora si deja de salir un esperado que salía, aparece un falso positivo nuevo o la sección de documentos pasa a salir al revés. Corre como trabajo, con progreso, y se conservan las últimas 20 ejecuciones de cada brain.
- **Simular** repite la medida con otros umbrales de similitud de los pasajes (por ejemplo `0,68 0,70 0,72`) **sin cambiar el ajuste**.
- Se crean a mano, se **importan y exportan** en JSON, o se guardan desde Preguntar marcando cada resultado como «Debe salir» o «Sobra».
- **En un cambio de modelo de embeddings** se ejecutan solas dos veces en cada brain que tenga consultas: al empezar el relleno, con el modelo anterior, como base, y al terminar el cambio. Si empeoran, se avisa con el evento `refquery.regressed`; si no hay base con la que comparar, el mismo evento lo dice (como información) en vez de callar.
- Los textos de una consulta pasan por el detector de secretos del brain: guardar como esperado un hecho del grafo (que no pasó por él al ingerirse) no copia una credencial.

## Vocabulario

La ontología se define por brain (paquetes estándar en `api/mimirsynth/presets/`, ver [ONTOLOGY.md](ONTOLOGY.md)). La interfaz permite normalizar alias, fusionar duplicados, retipar entidades y editar los tipos de relación; cada cambio es reversible y queda auditado.

## Trabajos

Ingesta, escaneo de carpetas y reindexado pasan por una cola general con progreso, cancelación y reintento. Los reescaneos programados sin incidencias se purgan solos; los plazos se cambian en Administración → Ingesta y trabajos.

## Configuración

El entorno solo lleva lo necesario para arrancar y conectar (ver `.env.example`). Todo lo demás se cambia en la interfaz (Administración) y se aplica sin reiniciar; las variables de entorno equivalentes funcionan como valor por defecto. Los secretos guardados en la base de datos se cifran con una clave derivada de `MIMIRSYNTH_SESSION_SECRET`: si cambia, hay que volver a introducirlos.

## Dependencias y licencias

MimirSynth se publica bajo Apache-2.0. Graphiti es Apache-2.0. **FalkorDB es *source-available* (SSPL)**, no una licencia open source permisiva: revisa sus condiciones antes de ofrecer MimirSynth como servicio. El acceso al grafo pasa por una capa propia para poder sustituir el motor en el futuro.

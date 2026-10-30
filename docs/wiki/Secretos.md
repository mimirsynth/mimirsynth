[English](Secrets) · **Español**

# Secretos

Es fácil llenar una memoria de credenciales sin querer: una nota que pega una cadena de conexión, un agente que recuerda un comando con su token, un documento con una clave privada. Antes de guardar nada, MimirSynth le pasa un **detector de secretos**, y cada brain decide qué hacer con lo que encuentre.

## Cuándo actúa
- Antes de guardar una **propuesta**, venga de donde venga: la pantalla de [[Propuestas]], la API REST o `remember` por MCP.
- Antes de indexar un **documento** (subidas, carpetas y wikis; ver [[Conocimiento]]).
- Sobre los textos de una **consulta de referencia** (Preguntar → Consultas de referencia), para que guardar un hecho del grafo como texto esperado no copie una credencial.

No usa ningún modelo de IA: es un conjunto de reglas, rápido y local.

## Qué busca
Los hallazgos son de dos clases:
- **Seguros:** formatos inconfundibles. Claves privadas (PEM), claves de acceso de AWS, tokens de GitHub, GitLab, Slack, npm, Hugging Face y de bots de Telegram, webhooks de Slack, claves de API de Google, Stripe, SendGrid y de proveedores de IA, JWT, cabeceras `Authorization` y contraseñas dentro de una URL (`https://usuario:contraseña@…`).
- **Posibles:** un valor de aspecto aleatorio asignado a una palabra como `password`, `secret`, `token` o `api_key`. Estos **solo se marcan**, nunca se cambian: la aleatoriedad sola atraparía también sumas de comprobación, UUID e identificadores de contenedores, que son normales en notas técnicas.

## Qué hacer con un secreto
Cada brain lo elige en **Administración → Acceso al brain → Secretos** (administradores del brain):

| Modo | Secretos seguros | Secretos posibles |
|---|---|---|
| **Enmascarar (recomendado)**, el predeterminado | Se sustituyen por `[secreto eliminado: tipo]` antes de guardar | Se marcan |
| **Bloquear** | La propuesta se rechaza con un mensaje que dice qué tipo es; el documento no se indexa (y sale del índice si ya estaba) | Se marcan |
| **Solo avisar** | Se marcan y no se tocan | Se marcan |

En la práctica:
- Una propuesta con algo **marcado** siempre **espera a un curador**: el decisor no la aprueba y no se aprueba al enviarla, aunque la envíe un curador. Su detalle muestra un aviso de **Secretos detectados** con lo que se enmascaró o se marcó.
- En un documento se enmascara el **texto indexado** (pasajes, vectores y texto de búsqueda). **El original que se descarga no se modifica**: conserva el valor tal cual, y el visor del documento lo indica.
- La marca se escribe en el idioma de la instancia, porque se queda en la memoria.
- Cambiar el modo no vuelve a procesar lo ya guardado. Para aplicarlo a un documento, **reindéxalo**.

## Excepciones
El cuadro **Excepciones** admite una entrada por línea:
- `rule:jwt` desactiva una regla en este brain. Los nombres de las reglas son `private_key`, `aws_access_key`, `github_token`, `gitlab_token`, `slack_token`, `slack_webhook`, `google_api_key`, `ai_api_key`, `stripe_key`, `npm_token`, `huggingface_token`, `telegram_bot_token`, `sendgrid_key`, `jwt`, `authorization`, `url_credentials` y `assigned_secret` (la de los posibles).
- Cualquier otra línea es una **expresión regular**: un valor detectado que encaje con ella no se trata como secreto (por ejemplo, las claves de mentira de tus ejemplos).
- Las líneas que empiezan por `#` son comentarios.

Una expresión que lo aceptaría todo (como `.*`) se rechaza al guardar, porque apagaría el detector; usa `rule:` para desactivar una sola regla.

## Analizar lo ya guardado
**Analizar lo ya guardado** pasa el detector, con las excepciones guardadas, por las propuestas y los documentos indexados del brain **sin cambiar nada**. Sirve para medir aciertos y falsos positivos antes de cambiar el modo o añadir excepciones.
- Muestra cuántas propuestas y documentos se han analizado, un resumen por **Tipo** (con su **Clase**, **seguro** o **posible**, las **Apariciones** y en cuántos elementos están, **En**) y la lista de hallazgos con **Dónde** están y el **Texto anterior**. El valor nunca se muestra.
- Solo se listan los primeros 500 elementos; los recuentos sí son completos. En un brain muy grande puede pararse al llegar al máximo de texto y avisar de que faltan documentos.
- Lo que ya está en el **grafo** no se analiza.
- Cada análisis queda en la [[Auditoría]] (`secrets.scan`, con los recuentos por regla).

## Lo que nunca se guarda
El valor detectado nunca llega a la [[Auditoría]], a los registros, a las respuestas de la API ni a las [[Notificaciones]]: solo la regla y su posición. En la auditoría y en [[Trabajos]] también se oculta lo que esté marcado en el título de una propuesta. Una propuesta bloqueada queda como `proposal.blocked` con las reglas, no con el valor.

Detalles técnicos: «Secretos» en [docs/es/ARCHITECTURE.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/ARCHITECTURE.md).

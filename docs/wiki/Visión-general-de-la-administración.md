[English](Administration-overview) · **Español**

# Visión general de la administración

El icono del engranaje de la barra lateral abre **Administración**. Las secciones están en una lista a la izquierda, agrupadas (en móvil, arriba), y cada una es una tarjeta con su título y su descripción. La sección activa va en la dirección (`?seccion=…`), así que puedes enlazarla.

## Qué ve cada persona
- **Cualquiera** ve **Acceso al brain** del brain activo: su nombre y su rol, qué le prestan otros brains ([[Federación]]) y sus tokens de API.
- **Los administradores de un brain** gestionan además sus miembros, lo que presta a otros brains y su política de [[Secretos]], y pueden editarlo.
- **El administrador de la instancia** ve todas las secciones.

## Mapa de secciones
| Grupo | Sección | Para qué | Página |
|---|---|---|---|
| **Brain** | Acceso al brain | Crear/editar/borrar brains, miembros, federación, secretos y tokens | [[Administrar brains y miembros]], [[Federación]], [[Secretos]] |
| **Cuentas** | Usuarios | Altas, invitaciones, roles, bloqueos | [[Administrar usuarios]] |
| | Seguridad | Contraseñas, bloqueo, doble factor obligatorio | [[Seguridad y doble factor]] |
| | Identidad | Inicio de sesión con uno o varios proveedores externos | [[Identidad OIDC]] |
| | Correo (SMTP) | Envío de invitaciones y recuperaciones | [[Correo SMTP]] |
| **Modelos de IA** | Modelo LLM, Embeddings, Decisor | Los tres motores, y el cambio de modelo de embeddings | [[Proveedores de IA]] |
| **Documentos** | Carpetas | Raíces de las fuentes de carpetas | [[Carpetas y límites]] |
| | Límites | Tamaños máximos de ficheros | [[Carpetas y límites]] |
| **Sistema** | General | Idioma por defecto | [[Referencia de ajustes]] |
| | Recuerdo | Parámetros del recall documental e índice | [[Recuerdo e ingesta]] |
| | Ingesta y trabajos | Reintentos, retención y el ritmo de un cambio de modelo de embeddings | [[Recuerdo e ingesta]] |
| | Notificaciones | Canales de avisos, historial de envíos y comprobaciones propias de la instancia | [[Notificaciones]] |
| | Auditoría | Registro de acciones | [[Auditoría]] |

Todos los parámetros numéricos y de texto, con sus valores por defecto y rangos, están en [[Referencia de ajustes]].

## Cómo funcionan los ajustes
- Cada ajuste es una **fila** con su nombre, su ayuda y el control a la derecha.
- Los botones **Guardar** y **Cancelar** solo aparecen si cambias algo; **Restaurar** solo si el valor difiere del por defecto.
- Se aplican **sin reiniciar** (hay una caché de unos 5 segundos, así que puede tardar un momento en notarse).
- Cada campo valida su formato y su rango.
- Los **secretos** (contraseña SMTP, secretos de los clientes OIDC, claves de los modelos, tokens de los canales de notificación) se guardan **cifrados** y **no se vuelven a mostrar**: para cambiarlos hay que escribir uno nuevo.
- Cada cambio queda en la [[Auditoría]] (los secretos, sin su valor).
- El **valor por defecto** de un ajuste es su variable de entorno equivalente, si existe, o el valor de fábrica. Ver [[Variables de entorno]].

## En una instancia nueva
Mientras no exista ningún brain, la página de inicio del administrador de la instancia muestra **Primeros pasos**: un botón **Crea tu primer brain** y una lista breve (modelos de IA, un token de API, conectar un agente) con enlaces a cada pantalla.

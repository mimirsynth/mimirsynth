[English](SMTP-email) · **Español**

# Correo SMTP

Sección **Correo (SMTP)** de la administración. Configura el servidor de correo con el que MimirSynth envía **invitaciones**, **enlaces de recuperación de contraseña** y, si defines un canal de correo, **avisos**. Es opcional: sin él, el administrador copia los enlaces a mano desde la ficha del usuario, y los avisos pueden ir por los demás canales (o quedarse en la campana).

## Ajustes
| Ajuste | Por defecto | Notas |
|---|---|---|
| **Servidor SMTP** | vacío | Dirección del servidor (`smtp.ejemplo.com`) |
| **Puerto** | 587 | Habitual: 587 (STARTTLS), 465 (SSL/TLS) o 25 |
| **Cifrado** | STARTTLS | STARTTLS (587), SSL/TLS (465) o ninguno (solo redes de confianza) |
| **Usuario** | vacío | Vacío si el servidor no pide autenticación |
| **Contraseña** | — | Se guarda **cifrada** y no se vuelve a mostrar |
| **Remitente** | vacío | La dirección que aparece como remitente (`mimirsynth@ejemplo.com`) |

## Probar
Debajo de los ajustes hay un campo para escribir un **correo de destino** y el botón **Enviar prueba**. Si algo falla, el mensaje indica el motivo (autenticación, cifrado, conexión…). La prueba usa la configuración **ya guardada**: guarda los cambios antes de probar. Comprueba que llega **antes** de depender de él.

## Qué se envía
- **Invitación**: «Te han invitado a MimirSynth», con un enlace de un solo uso para elegir la contraseña.
- **Restablecimiento**: «Restablece tu contraseña de MimirSynth», con otro enlace. Si no lo pediste, se puede ignorar.
- **Avisos**: un canal **Email** en *Administración → Notificaciones* envía los avisos a los que esté suscrito (modelo de IA o grafo que no responde, ingesta o trabajo fallido, error de una fuente de documentos, bloqueo de una cuenta…) a los destinatarios que indiques, por este mismo servidor. Los avisos nunca incluyen contenido de la memoria.

Las invitaciones y los restablecimientos salen en el idioma del destinatario (o en el de la instancia; ver [[Referencia de ajustes]]). Los enlaces caducan a los 7 días por defecto ([[Seguridad y doble factor]]).

## Proveedores habituales
| Proveedor | Servidor | Puerto / cifrado |
|---|---|---|
| Servidor propio (Postfix…) | el tuyo | 587 STARTTLS, o 25 sin cifrar en red de confianza |
| Gmail / Google Workspace | `smtp.gmail.com` | 587 STARTTLS, con una **contraseña de aplicación** |
| Microsoft 365 | `smtp.office365.com` | 587 STARTTLS |
| Servicios transaccionales | el que indique el servicio | normalmente 587 o 465 |

## Si no llegan los correos
- Revisa la carpeta de spam y que el **remitente** sea una dirección que tu servidor permite usar.
- Con proveedores que exigen **autenticación fuerte** (Gmail, Microsoft), usa una contraseña de aplicación o un usuario de envío dedicado.
- Si el servidor se anuncia con un certificado no válido, el cifrado fallará: usa un certificado correcto.
- «¿Has olvidado la contraseña?» responde **siempre lo mismo** (para no revelar qué cuentas existen): si no llega nada, el correo no está configurado, la cuenta no existe o se superó el límite de 3 peticiones por hora.
- Un correo de aviso que no llega aparece como envío fallido en *Administración → Notificaciones*, donde se puede reintentar a mano.

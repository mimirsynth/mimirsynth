[English](Audit-log) · **Español**

# Auditoría

Sección **Auditoría** de la administración (solo el administrador de la instancia): el **registro de acciones** de administración y de acceso. Sirve para saber **quién hizo qué y cuándo**.

## La tabla
Muestra las **200 acciones más recientes**, con tres columnas:
- **Fecha.**
- **Acción** (filtrable): el tipo de evento.
- **Detalle**: los datos de la acción (usuario afectado, brain, rol, etc.). Con búsqueda de texto.
Cada columna se puede ordenar y filtrar.

## Qué se registra
| Familia | Acciones |
|---|---|
| **Acceso** | `login` (el detalle dice cómo: contraseña, contraseña y doble factor, llave de acceso o un proveedor), `login.locked`, `setup` (primer arranque), `password.set`, `password.change`, `password.forgot` |
| **Doble factor y llaves de acceso** | `2fa.enable`, `2fa.disable`, `2fa.recovery`, `passkey.add`, `passkey.remove`, `user.mfa_reset` (quita también las llaves de acceso de la persona) |
| **Usuarios** | `user.create`, `user.status`, `user.role`, `user.link` (se generó un enlace de invitación o de restablecimiento), `user.logout`, `user.unlock`, `user.delete`, `user.autoprovision` |
| **Proveedores de identidad** | `oidc.create`, `oidc.update`, `oidc.delete`; `identity.link`, `identity.unlink` (una persona vincula o desvincula un proveedor); `oidc.revoke.skipped` (no se retiró el rol de administrador al salir del grupo porque era el último administrador) |
| **Brains y miembros** | `brain.create`, `brain.update` (incluidas la descripción y la política de secretos), `brain.delete`, `brain.retention` (cada plazo que cambió, de cuánto a cuánto), `member.set` (`via=oidc-default:<proveedor>` cuando viene del acceso inicial de un proveedor), `member.remove` |
| **Federación** | `grant.create`, `grant.update`, `grant.revoke` |
| **Tokens** | `token.create` (con el alcance y los días hasta que caduca), `token.rotate` (con el periodo de gracia), `token.revoke` |
| **Propuestas** | `proposal.submit`, `proposal.approved`, `proposal.rejected`, `proposal.triage.*` (el veredicto del decisor), `proposal.ingested`, `proposal.failed`, `proposal.blocked` (rechazada por la política de [[Secretos]], con las reglas, nunca el valor) |
| **Secretos** | `secrets.scan` (recuentos por regla) |
| **Exportar** | `brain.export` (las opciones, nunca la contraseña), `brain.export.download` |
| **Importar** | `brain.import` (slug, modo y nombre del fichero, nunca la contraseña), `brain.import.done` (cómo entró el grafo y los recuentos) |
| **Vocabulario** | `fact.confirm` (un hecho a revisar confirmado como todavía cierto), `vocab.alias.add`, `vocab.alias.delete`, `vocab.revert`, `vocab.duplicates.ignore`, `vocab.*` (fusiones y cambios de tipos de entidad y de relación), `ontology.update`, `retype.scan`, `retype.apply`, `retype.revert`, `conflict.resolve` (una contradicción resuelta), `conflict.dismiss` y `conflict.undismiss` (marcada como no contradicción, y vuelta a mostrar) |
| **Consultas de referencia** | `refquery.create`, `refquery.update`, `refquery.delete`, `refquery.import`, `refquery.run` |
| **Documentos** | `document.upload`, `document.delete`, `document.reindex`, `document.duplicates` (Buscar duplicados), `docsource.create/update/delete/scan`, `docroot.create/delete` |
| **Proveedores de IA** | `ai.price` (el precio por millón de tokens de un modelo), `brain.ai_budget` (el presupuesto mensual de un brain, de cuánto a cuánto), `llm.*`, `embedding.*`, `decider.*` (crear, actualizar, borrar, por defecto); en un cambio de modelo de embeddings, además `embedding.reindex`, `embedding.reindex.filled`, `embedding.reindex.discard`, `embedding.switch` (con la confirmación de la copia de seguridad) y `embedding.switched` |
| **Notificaciones** | `notify.channel.create`, `notify.channel.update`, `notify.channel.delete`, `notify.channel.test` |
| **Ajustes** | `settings.set`, `settings.reset`, `settings.secret` (sin el valor del secreto) |
| **Sistema** | `index.sync`, `job.cancel`, `job.retry` |
| **Cuenta** | `account.profile`, `account.avatar`, `account.sessions.revoke` |

## Qué **no** se registra
- Los **valores de los secretos** (contraseñas, claves de API, secretos OIDC, tokens de los canales): solo que se cambiaron.
- Las **credenciales encontradas en propuestas y documentos**: solo la regla que encajó. Lo que el detector marque en el título de una propuesta también se oculta ([[Secretos]]).
- La lectura de datos (consultas, recall).

## Tu propia actividad
Cada persona ve su actividad reciente en [[Mi cuenta]].

## Retención
El registro se conserva en la base de datos sin purga automática. Entra en las copias de seguridad de PostgreSQL ([[Actualización y copias de seguridad]]).

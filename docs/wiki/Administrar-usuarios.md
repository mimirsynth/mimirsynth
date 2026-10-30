[English](Administer-users) · **Español**

# Administrar usuarios

Sección **Usuarios** de la administración (solo el administrador de la instancia). Gestiona las **cuentas propias** de MimirSynth: altas, invitaciones, roles, bloqueos y bajas.

## La tabla
Una fila por persona: **usuario** (nombre y email), **rol** (administrador o usuario), métodos de **acceso** (contraseña y proveedores OIDC vinculados), **estado**, número de **brains** y **último acceso**. Con orden y filtros por columna (búsqueda por nombre o email, filtro por rol y por estado).

| Estado | Significado |
|---|---|
| **Invitado** | Creado pero aún no ha aceptado la invitación ni ha entrado |
| **Activo** | Puede entrar |
| **Deshabilitado** | No puede entrar (sus tokens de API tampoco valen) |
Una cuenta puede aparecer además como **bloqueada** temporalmente por demasiados intentos fallidos.

Si no hay servidor de correo configurado, arriba verás un aviso de atención **«Sin servidor de correo»** con un enlace a [[Correo SMTP]]: sin él, los enlaces de invitación y recuperación se copian a mano.

## Crear un usuario
Botón **Crear usuario**:
- **Email** y **Nombre**.
- **Administrador de la instancia** (casilla): gestiona usuarios, ajustes y todos los brains.
- **Acceso**, dos modos:
  - **Invitación:** se genera un **enlace de un solo uso** para que la persona elija su contraseña. Si hay correo configurado, también se le envía por email. **Cópialo en ese momento**: solo se muestra al crearlo (puedes generar otro después).
  - **Contraseña temporal:** pones tú una contraseña y la persona **tendrá que cambiarla al entrar**.
Los enlaces caducan a los **7 días** (ajustable en [[Seguridad y doble factor]]).

## La ficha de un usuario
Al pulsar una fila se abre su panel lateral:
- **Datos:** estado, etiquetas (administrador, bloqueado, contraseña, 2FA, proveedores), email y fechas.
- **Administrador de la instancia** (interruptor). No puedes cambiar tu propio rol.
- **Deshabilitar / Habilitar.**
- **Nuevo enlace de invitación** (si aún no aceptó) o **Restablecer contraseña** (genera un enlace para que elija una nueva; si hay correo, se envía).
- **Desbloquear** (si está bloqueada).
- **Quitar doble factor**: para quien perdió el móvil y los códigos de recuperación. Quita su app de autenticación **y sus llaves de acceso**, y cierra sus sesiones.
- **Cerrar sus sesiones.**
- **Eliminar.**
- **Brains:** todas sus pertenencias con su rol (cámbialo con el selector), **Quitar** de un brain y **Añadir a un brain** nuevo. Quien se da de alta solo a través de un proveedor OIDC llega con el **acceso inicial** de ese proveedor ([[Identidad OIDC]]): es una pertenencia normal, así que puedes cambiarla o quitarla aquí y ningún inicio de sesión posterior la repone.

## Eliminar un usuario
**Anonimiza** la cuenta: se borran su email y su nombre, se le quitan accesos, sesiones y tokens, y el email queda **libre** para volver a invitarlo. Sus **propuestas y la auditoría se conservan** como «Usuario eliminado».

## Protecciones
- No puedes deshabilitarte, eliminarte ni quitarte el rol de administrador a ti mismo.
- No se puede deshabilitar, eliminar ni degradar al **último administrador activo**.
- Cada acción de esta pantalla queda en la [[Auditoría]].

## El camino de la invitación
1. El administrador crea el usuario (modo invitación) y entrega el enlace.
2. La persona lo abre (`/acceso/<código>`), ve su email, elige nombre y contraseña, y **entra directamente**.
3. El enlace se invalida (un solo uso) y cierra sesiones anteriores de esa cuenta.
Un enlace caducado o usado se sustituye generando otro desde la ficha.

## Recuperar la contraseña
En la pantalla de entrada, **«¿Has olvidado la contraseña?»** envía un enlace por correo (solo si el SMTP está configurado; la respuesta es siempre la misma para no revelar qué cuentas existen). Sin correo, el administrador genera el enlace desde la ficha («Restablecer contraseña»).

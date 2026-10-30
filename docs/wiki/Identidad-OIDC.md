[English](OIDC-identity) · **Español**

# Identidad OIDC

Sección **Identidad** de la administración. Permite que las personas inicien sesión con uno o varios **proveedores de identidad externos** (PocketID, Keycloak, Authentik, Entra ID, Google…) además de con su cuenta propia. Es **opcional**: MimirSynth funciona sin ellos.

> El inicio de sesión por OIDC **no sustituye** al sistema de cuentas: cada persona sigue teniendo su cuenta, y cada proveedor se **vincula** a ella. Por defecto solo entra quien ya tiene cuenta o invitación.

## Proveedores
La sección lista los **proveedores de inicio de sesión**. Cada uno tiene su **propia** conexión, política de alta automática y roles por grupo, y muestra **su propio botón** («Entrar con …») en la pantalla de acceso. Puedes **añadir**, **editar**, **probar la conexión** y **borrar**.

1. En tu proveedor, registra una **aplicación (cliente OIDC)**. La tarjeta de cada proveedor muestra su **URL de retorno** (`…/api/auth/callback/<identificador>`; la del proveedor importado de una versión anterior sigue siendo `…/api/auth/callback`), con un botón de copiar.
2. Pulsa **Añadir proveedor** y rellena:
   | Campo | Qué poner |
   |---|---|
   | **Identificador** | Nombre corto que va en las URLs (minúsculas, números y guiones). **No se puede cambiar** después |
   | **Nombre del botón** | Texto del botón de inicio de sesión («Entrar con *nombre*») |
   | **Emisor OIDC** | URL base del proveedor; debe publicar `/.well-known/openid-configuration` |
   | **Client ID** | El identificador de la aplicación registrada |
   | **Client secret** | Se guarda **cifrado** y no se vuelve a mostrar. Al editar, déjalo vacío para conservar el guardado |
   | **Scopes** | Permisos que se piden (por defecto `openid profile email`) |
   | **Activo** | Un proveedor desactivado no se ofrece en la pantalla de acceso |
3. **Un emisor que no responde no se puede guardar**, para que un error no deje a nadie fuera. **Probar conexión** lee el documento de descubrimiento del proveedor.
4. La **URL pública** (ajuste común, debajo de la lista) se usa para construir las URLs de retorno.

**Borrar** un proveedor desvincula las identidades de quienes entraban por él. Se **rechaza** si alguien se quedaría sin ninguna forma de entrar (sin contraseña y sin otro proveedor): dale una contraseña o vincula otro antes.

> **Al actualizar desde la 0.4 o anterior:** el único proveedor que tuvieras configurado (desde la interfaz o con las variables `MIMIRSYNTH_OIDC_*`) se importa **una sola vez**, en el primer arranque, como el proveedor `oidc`, con la **misma URL de retorno**: no hace falta cambiar nada en tu proveedor. A partir de ahí se gestiona solo aquí; las variables ya no se leen y puedes quitarlas del `.env`.

## Quién puede entrar
Entra por un proveedor quien cumpla **una** de estas condiciones:
1. Su identidad ya está **vinculada** a una cuenta.
2. Tiene una cuenta **activa o invitada** con **el mismo email**, **verificado** por el proveedor: entonces se vincula sola. Una cuenta invitada pasa a activa.
3. Su email está en **Administradores de la instancia** y el proveedor lo marca como **verificado**: se crea una cuenta de administrador.
4. El proveedor tiene **alta automática** y su email **verificado** es de uno de sus **dominios permitidos**.

En cualquier otro caso verá «Tu cuenta no está dada de alta en esta instancia». Una cuenta **deshabilitada** no entra.

### Emails sin verificar
Algunos proveedores no marcan el email como verificado (Entra ID, por ejemplo). Para ellos existe **Aceptar emails sin verificar**, para que las invitaciones se puedan aceptar a través de ese proveedor. Con él activado:
- Un email sin verificar **solo se vincula a una invitación** (una cuenta que aún no tiene contraseña ni proveedor).
- **Nunca** se vincula a una cuenta que ya está **activa**. Esa persona ve «Ya tienes una cuenta con ese email. Entra como siempre y vincula este proveedor desde Mi cuenta → Seguridad», y lo vincula desde [[Mi cuenta]] después de entrar.
- Nunca crea una cuenta: ni **Administradores de la instancia** ni el **alta automática** aceptan un email sin verificar.

### Ajustes de cada proveedor
| Ajuste | Por defecto | Notas |
|---|---|---|
| **Aceptar emails sin verificar** | No | Solo para proveedores que no marcan el email como verificado. Quien pueda registrar un email ajeno en el proveedor podría aceptar la invitación de esa persona. **No lo actives salvo que confíes en el proveedor** |
| **Alta automática** | No (solo invitados) | La cuenta se crea sin invitación, solo para los dominios permitidos |
| **Dominios permitidos** | vacío | Dominios (separados por comas, p. ej. `example.com`) a los que se aplica el alta automática. Vacío = ninguno |
| **Acceso inicial** | vacío | Brains a los que entra quien se da de alta solo, como `brain:rol` (ver abajo) |

### Ajustes comunes
| Ajuste | Por defecto | Notas |
|---|---|---|
| **Administradores de la instancia** | vacío | Emails (separados por comas) que reciben una cuenta de administrador la primera vez que entran por un proveedor, solo con un email que el proveedor marque como verificado |
| **Gestión de la cuenta** | vacío | URL de la página de tu proveedor donde se gestionan contraseña, llaves de acceso y doble factor; se enlaza desde [[Mi cuenta]] |

**Alta automática:** la cuenta nueva es **usuario** (no administrador), con el **acceso inicial** del proveedor y lo que le den sus grupos, y nada más. **Nunca** se aplica a emails sin verificar, aunque actives «Aceptar emails sin verificar».

### Acceso inicial
Una lista de `brain:rol` separados por comas, por ejemplo `docs:reader, wiki:contributor`, que recibe quien se da de alta por **alta automática**:
- Solo se admiten los roles `reader` y `contributor`: cualquiera de esos dominios los obtiene sin que nadie lo revise, y lo que proponga sigue el camino habitual del brain (un curador o el decisor).
- Se aplica **una sola vez**, al crear la cuenta, como una pertenencia normal que queda en la [[Auditoría]] (`member.set`, `via=oidc-default:<proveedor>`). Un administrador puede cambiarla o quitarla en [[Administrar usuarios]], y ningún inicio de sesión posterior la repone.
- Si un grupo da un **rol mayor** en el mismo brain, gana el mayor.
- Al guardar el proveedor se rechazan otros roles, brains repetidos y brains que no existen; un brain borrado después se ignora.
- No se aplica a las invitaciones, que traen sus propios roles.

## Grupos y roles
Si un proveedor envía los **grupos** de cada persona en un campo de su identidad, puedes dar roles automáticamente (cada proveedor tiene sus propias reglas).

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| **Claim de grupos** | `groups` | Nombre del campo con los grupos (el proveedor debe incluirlo, con el scope adecuado) |
| **Grupo de administradores** | vacío | Los miembros de este grupo son **administradores de la instancia**. Quien sale del grupo pierde el rol en su siguiente inicio de sesión, salvo que sea el último administrador |
| **Roles por grupo** | vacío | Reglas `grupo=brain:rol` separadas por comas. Roles: `reader`, `contributor`, `curator`, `admin` |

Ejemplo de **Roles por grupo**: `curadores=docs:curator, lectores=docs:reader`.

Cómo funciona:
- Se aplica **en cada inicio de sesión**.
- **Conceden** el rol si la persona no tiene ya uno **igual o mayor**, y **nunca rebajan** uno existente. Por grupo, **«owner» no se concede nunca**.
- También **retiran**: cuando alguien **sale de un grupo**, la siguiente vez que entra pierde lo que ese grupo le dio (el rol de administrador o el rol en el brain). Si el grupo le había **subido** un rol (por ejemplo de lector a curador), vuelve al anterior.
- Lo puesto **a mano no se toca nunca**: los roles que ya existían antes de la 0.5, los que un administrador asigna o cambia después en [[Administrar usuarios]] y los que la persona ya tenía con igual o mayor nivel.
- Salvaguardas: **nunca se retira al último administrador activo**; y **si el proveedor no envía el campo de grupos** no se retira nada (un fallo de configuración no debe dejar a todo el mundo sin acceso). Al retirar el rol de administrador se cierran las sesiones abiertas de esa persona.
- Las reglas con un brain que no existe o un rol inválido se ignoran.

## Vincular varios proveedores a una cuenta
Cada persona puede vincular y desvincular proveedores en [[Mi cuenta]] → Seguridad → **Identidades vinculadas**. Vincular pasa por el proveedor y lo añade a la cuenta actual; una identidad que ya es de otra cuenta se rechaza. La última forma de entrar no se puede desvincular.

## El administrador local y el modo mixto
Con un proveedor activo, las **cuentas con contraseña siguen funcionando**: sirven de acceso de emergencia si el proveedor cae. Mantén al menos una cuenta de administrador con contraseña (y doble factor).

## Solución de problemas
| Síntoma | Causa probable |
|---|---|
| No guarda el proveedor | El emisor no responde o no publica el documento de descubrimiento (usa «Probar conexión») |
| «redirect_uri no válida» en el proveedor | La URL de retorno registrada no coincide con la de la tarjeta del proveedor (esquema, dominio, ruta) |
| «Tu cuenta no está dada de alta» | No hay cuenta/invitación con ese email, el email no está verificado, o el dominio no está permitido |
| «Ya tienes una cuenta con ese email…» | El proveedor envió un email sin verificar que coincide con una cuenta activa: entra como siempre y vincula el proveedor desde [[Mi cuenta]] → Seguridad |
| Entra sin los roles esperados | El proveedor no envía el campo de grupos, o el nombre del *claim* no coincide |
| Perdió un rol al salir de un grupo | Es lo esperado: los roles concedidos por un grupo se retiran al salir de él |
| El primer inicio falla y el siguiente funciona | El proveedor tardó en responder al descubrimiento; reinténtalo |

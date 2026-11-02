[English](My-account) · **Español**

# Mi cuenta

Tu perfil, tu seguridad, tus tokens de API y tu actividad. Se abre desde tu **avatar y tu nombre**, abajo en la barra lateral; el botón de al lado **cierra la sesión** con un solo clic. Las secciones están en la lista de la izquierda (en móvil, arriba), agrupadas en **Cuenta** (Perfil, Seguridad, Resumen por correo), **Acceso** (Tokens de API) e **Historial** (Actividad). Debajo de esa lista hay también un botón destacado de **Cerrar sesión**.

## Perfil
- **Avatar:** sube una imagen (PNG, JPEG o WebP, hasta **1 MB**) o **Quítala** para volver a la del proveedor de identidad o a tus iniciales.
- **Nombre visible:** cómo apareces en la aplicación. Si lo dejas vacío se usa el del proveedor de identidad.
- **Idioma:** español o inglés. Se guarda en tu cuenta y vale en cualquier dispositivo. Fija el idioma de la interfaz y de tus correos, y también el de lo que **la API y el servidor MCP** responden a tus tokens de API: mensajes de error, descripciones de las herramientas MCP y encabezados del contexto del recall. Un cliente que envíe la cabecera `Accept-Language` recibe ese idioma en su lugar. La memoria guardada nunca se traduce: hechos, episodios y documentos vuelven tal como se escribieron. Ver [[Conectar agentes]].
- **Cuenta:** tu correo, tu rol en la instancia (administrador o usuario), cuándo se creó la cuenta, tu último acceso y los **brains** a los que tienes acceso con tu rol en cada uno.

## Seguridad
### Contraseña
- Si ya tienes una, **cámbiala** (te pide la actual). El formulario muestra las reglas (longitud mínima, 12 por defecto; sin tu email ni tu nombre; ni común ni una secuencia; al menos 5 caracteres distintos) y las va marcando mientras escribes. Ver [[Seguridad y doble factor]].
- Si hasta ahora solo entrabas por tu proveedor de identidad (OIDC), puedes **definir una contraseña** para entrar también directamente, por si el proveedor no está disponible.
- Al cambiarla se **cierra la sesión en el resto de dispositivos**.

### Identidades vinculadas
Los proveedores externos (OIDC) con los que puedes entrar. **Vincula** otro para tener más de una forma de acceso, o **desvincula** uno que ya no uses. Vincular pasa por el proveedor y se añade a esta cuenta; una identidad que ya es de otra cuenta se rechaza, y no puedes desvincular tu única forma de entrar (pon antes una contraseña). Ver [[Identidad OIDC]].

### Llaves de acceso
Entra con la **huella, el rostro o el PIN** de tu dispositivo en lugar de escribir la contraseña. Una llave de acceso ya **cuenta como doble factor**.
1. Pulsa **Añadir llave de acceso**.
2. Ponle un **Nombre de la llave** (portátil, móvil, llave USB…) y, si tienes contraseña, **Confirma tu contraseña**.
3. Pulsa **Crear llave de acceso** y completa el gesto en tu dispositivo.

La lista muestra cada llave con su fecha de creación y su último uso, marcada como **sincronizada** cuando tu plataforma o tu gestor de contraseñas guarda una copia (así también sirve en tus otros dispositivos). **Quitar** pide tu contraseña y se rechaza si esa llave es tu única forma de entrar. En la pantalla de entrada, usa **Entrar con llave de acceso**. Si el navegador dice que no admite llaves de acceso, usa otro navegador u otro dispositivo. Las llaves solo funcionan en la dirección pública de la instancia; si el administrador la cambia, vuelve a añadirlas.

### Verificación en dos pasos (doble factor)
Añade a la contraseña un código de 6 dígitos de una **app de autenticación** (Aegis, 2FAS, Google Authenticator, Bitwarden…). Solo está disponible si tienes contraseña propia.

**Activar:**
1. Pulsa **Activar doble factor** y confirma tu contraseña.
2. **Escanea el código QR** con la app (o escribe la clave a mano si no puedes escanear).
3. Escribe el código de 6 dígitos que muestra la app y pulsa **Activar**.
4. Se muestran **10 códigos de recuperación**. **Guárdalos** (gestor de contraseñas o papel): cada uno sirve una sola vez si pierdes el móvil y **no se vuelven a mostrar**.

**Después:** al iniciar sesión con contraseña se pide además el código de la app (o uno de recuperación); si tienes también una llave de acceso, puedes usarla en ese paso. Los códigos de la app no se pueden reutilizar.

**Gestionar:** *Generar códigos nuevos* (los anteriores dejan de valer) o *Desactivar* (piden contraseña y un código). Si el administrador **exige** el doble factor, no se puede desactivar. Si pierdes el móvil **y** los códigos, un administrador puede quitártelo ([[Administrar usuarios]]); eso quita también tus llaves de acceso.

> El doble factor protege el acceso **con contraseña**. Si entras por tu proveedor de identidad (OIDC), las reglas de verificación las aplica ese proveedor.

### Sesiones
**Cerrar sesión en otros dispositivos** (esta sesión sigue abierta) si crees que alguien más la tiene abierta, y **Salir**. También hay un enlace a tu cuenta en el proveedor de identidad, si el administrador lo configuró.

## Resumen por correo
Un correo periódico con lo que ha cambiado en tus brains, para cuando no abres la aplicación a diario. En **Resumen por correo**, elige para cada brain **Nunca**, **Cada día** o **Cada semana**, y en **Cuándo** la hora, el día de la semana (para los semanales) y tu **zona horaria** (la del navegador, la primera vez). **Ver un ejemplo** enseña lo que diría ahora un resumen de tus brains.

- **Qué dice:** de cada brain, cuántos hechos son nuevos y cuántos se han invalidado, y cuántos documentos se han añadido. Si eres **curador o más**, también lo que espera por ti: propuestas y correcciones por revisar (y la antigüedad de la más antigua), documentos con errores, posibles contradicciones y hechos a revisar. Cada línea enlaza con su página, ya en ese brain.
- **Solo recuentos y enlaces, nunca el contenido de las memorias.** Para leerlo, sigue el enlace.
- **Si no hay nada que contar, no se envía:** un brain sin novedades y con los mismos pendientes que en su último resumen se omite, y si no queda ningún brain, no llega ningún correo.
- **Un solo correo** reúne todos los brains que tocan en ese momento. El primero cuenta desde que te suscribiste. Si la instancia estuvo parada, al volver envía un resumen, no uno por cada día perdido.
- Va al correo de tu cuenta, en tu idioma, y necesita el correo de la instancia ([[Correo SMTP]]). Si pierdes el acceso a un brain, su resumen desaparece.

## Tokens de API
Los tokens permiten a **plugins y agentes** acceder a un brain sin usar tu contraseña.
- Elige el **brain**, un **nombre** (por ejemplo «Claude Code portátil») y un **rol**.
- Cada token vale para **un solo brain** y **nunca tiene más rol que el tuyo** (máximo *curador*; ninguno administra la instancia).
- El token (`mst_…`) **se muestra una única vez** al crearlo. Cópialo en ese momento.
- Elige cuándo **caduca** (a los 30, 90 o 365 días, o nunca, salvo que la instancia fije un máximo) y su **alcance**: consultar, documentos y proponer.
- Verás tus tokens con su prefijo, su alcance, su caducidad y su último uso; **Rotar** da uno nuevo y mantiene el anterior durante un periodo de gracia, y **Revocar** quita los que ya no uses. Ver «Caducidad y rotación» en [[Conectar agentes]].
Uso en [[Conectar agentes]].

## Actividad reciente
Tu historial de acciones (inicios de sesión, propuestas, cambios de hechos y de vocabulario, tokens…) con la fecha y un resumen legible. Se puede ordenar y buscar.

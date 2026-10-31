[English](Security-and-two-factor) · **Español**

# Seguridad y doble factor

Sección **Seguridad** de la administración: la política de las cuentas propias. Todos los valores se aplican sin reiniciar.

## Ajustes
| Ajuste | Por defecto | Qué hace |
|---|---|---|
| **Longitud mínima de contraseña** | 12 (8–64) | Se aplica al crear o cambiar contraseñas |
| **Intentos fallidos antes de bloquear** | 5 (3–20) | Tras ese número de errores seguidos, la cuenta se bloquea temporalmente |
| **Duración del bloqueo** | 15 min (1–1440) | Cuánto dura el bloqueo |
| **Exigir doble factor** | No | «Sí, a todos» obliga a configurar un segundo factor a quien entre con contraseña |
| **Caducidad máxima de los tokens de API** | 0, sin límite (0–3650 días) | Los tokens nuevos, también los rotados, tienen que caducar en este plazo; los que ya existen no cambian |
| **Validez de invitaciones y enlaces de recuperación** | 7 días (1–30) | Pasado el plazo el enlace deja de funcionar |

## Política de contraseñas
Además de la longitud, una contraseña se rechaza si:
- es una **contraseña común** (`password`, `contraseña`, `qwerty…`, el nombre de la aplicación…);
- está formada por **un solo carácter repetido** o es una **secuencia**, también si da la vuelta (`abcdefghijkl`, `987654321098`, `…yzab…`);
- usa **menos de 5 caracteres distintos**;
- **contiene tu email o tu nombre**.

Cada campo de contraseña muestra estas reglas y las va marcando mientras escribes; mientras falte alguna, el botón dice cuál. Vale para el asistente del primer arranque, las invitaciones y los restablecimientos, la pantalla de contraseña temporal y [[Mi cuenta]]. Las contraseñas se guardan con **argon2id**.

## Bloqueo e intentos
- Los intentos fallidos de contraseña **y** de segundo factor cuentan para el mismo bloqueo. Una cuenta bloqueada tampoco entra con una llave de acceso.
- Además hay un **límite de peticiones** por dirección IP y por cuenta en el inicio de sesión, el doble factor, las llaves de acceso, la recuperación de contraseña y el primer arranque (respuestas «demasiados intentos»). Sus contadores se guardan **en la base de datos**: se comparten entre procesos y un reinicio no los pone a cero. Si la base de datos falla, pasa a un contador en memoria: el acceso nunca queda sin protección.
- La pantalla de entrada **no revela qué cuentas existen**: el mensaje de error es siempre el mismo y el tiempo de respuesta también.
- Un administrador puede **desbloquear** una cuenta antes de tiempo desde su ficha ([[Administrar usuarios]]).

## Doble factor (TOTP)
Cada persona puede activarlo en [[Mi cuenta]] con una app de autenticación; se le dan **10 códigos de recuperación** de un solo uso.

**Cómo es el inicio de sesión con doble factor:** contraseña → pantalla de «Verificación en dos pasos» (código de 6 dígitos de la app, un código de recuperación o, si la cuenta tiene, **Usar llave de acceso**) → dentro. El permiso para enviar el código dura 5 minutos. Un código de la app **no se puede reutilizar**.

## Llaves de acceso
Una llave de acceso (passkey, WebAuthn) permite entrar con la **huella, el rostro o el PIN** del dispositivo en lugar de escribir la contraseña. Cada persona añade las suyas en [[Mi cuenta]] → Seguridad → **Llaves de acceso**.
- **Entrar con llave de acceso**, en la pantalla de entrada, entra sin contraseña. Después de la contraseña, **Usar llave de acceso** sirve de segundo paso, como un código de la app.
- Una llave exige que el dispositivo verifique a la persona, así que **cuenta como doble factor**, también cuando el doble factor es obligatorio.
- Solo se guarda la **clave pública**; la privada no sale del dispositivo. Un contador de firmas detecta llaves clonadas, y cada reto es de un solo uso y caduca.
- Quitar una llave pide la contraseña (si la cuenta tiene) y se rechaza si es la **única forma de entrar** de la persona: antes tiene que poner una contraseña o vincular un proveedor.

> **Necesita `MIMIRSYNTH_PUBLIC_URL` con HTTPS.** Una llave solo funciona en el dominio en que se creó (el de la URL pública). Defínela antes de que nadie registre una llave: cambiar de dominio después las invalida todas, así que conserva la contraseña como respaldo. Ver [[Variables de entorno]].

### Exigirlo a todos
Pon **Exigir doble factor** en «Sí». A partir de entonces, quien inicie sesión **con contraseña** sin segundo factor **solo ve la pantalla para configurarlo** (una app de autenticación **o** una llave de acceso, y la opción de salir) hasta que lo haga; la propia API también lo bloquea. Mientras esté exigido, nadie puede desactivarlo.
- **No afecta a quien entra por OIDC**: ahí manda el segundo factor que aplique tu proveedor de identidad.
- Activa tú primero tu propio doble factor y guarda tus códigos de recuperación **antes** de exigirlo.

### Si alguien lo pierde
Si pierde el móvil y los códigos de recuperación, el administrador usa **Quitar doble factor** en su ficha. Quita la app de autenticación **y sus llaves de acceso** y cierra sus sesiones; después podrá configurarlo de nuevo.

## Sesiones
Las sesiones son una cookie firmada. Se cierran todas las de una cuenta cuando: cambia su contraseña, un administrador la deshabilita, la persona acepta un enlace de restablecimiento, o pulsa «Cerrar sesión en otros dispositivos».

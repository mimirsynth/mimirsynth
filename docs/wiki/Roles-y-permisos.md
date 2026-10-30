[English](Roles-and-permissions) · **Español**

# Roles y permisos

Hay dos niveles: el **rol dentro de cada brain** y el **rol de instancia**.

## Rol en un brain
Cada rol incluye todo lo del anterior.

| Rol | Puede |
|---|---|
| **Lector** | Ver todo el brain: [[Resumen]], [[Diario]], [[Hechos]], [[Grafo]], [[Consulta Cypher]], [[Conocimiento]] (buscar y abrir documentos), [[Preguntar]] y [[Vocabulario]] (solo lectura), incluido lo que le prestan otros brains ([[Federación]]). Crear tokens de API de rol lector. |
| **Colaborador** | Además, **proponer** memoria ([[Propuestas]]; entra en cuarentena) y **subir documentos**. Ve sus propias propuestas. |
| **Curador** | Además, **aprobar o rechazar** propuestas (las suyas se aprueban al enviarlas, salvo que el detector de [[Secretos]] haya marcado algo), **editar, invalidar, reactivar y borrar hechos**, resolver **contradicciones** en [[Vocabulario]], deshacer operaciones de vocabulario, reindexar el texto de los episodios y gestionar las **consultas de referencia** del brain en [[Preguntar]] (crear, importar, ejecutar y simular). Ve los avisos del brain en la campana de [[Notificaciones]]. |
| **Administrador** | Además, gestionar el **vocabulario** (alias, tipos de entidad, ontología, duplicados, corrector de tipos), las **fuentes de documentos** (carpetas y wikis) y **Buscar duplicados** en [[Conocimiento]], los **miembros** del brain y sus tokens, lo que **presta** a otros brains ([[Federación]]) y su política de **secretos** ([[Secretos]]), y editar el nombre, la descripción y el slug del brain. |
| **Propietario** | Además, **borrar el brain**. |
| **Denegado** | Sin acceso. Prevalece sobre cualquier otro rol. |

Una concesión de federación **no es un rol**: los miembros del brain que la recibe leen lo prestado con su propio rol en él, y a nadie le sube el rol.

## Rol de instancia
La **administración de la instancia** es independiente de los brains. Quien la tiene:
- crea brains y es **propietario implícito de todos**;
- gestiona **usuarios**, la seguridad de las cuentas, el correo, el OIDC, los proveedores de IA (incluido el cambio de modelo de embeddings), las carpetas autorizadas, los límites y los canales de notificación, y ve la auditoría (ver [[Visión general de la administración]]);
- ve **todos los avisos** en la campana de [[Notificaciones]].

Una persona sin ese rol solo ve en Administración la sección «Acceso al brain».

## Tokens de API
Un token pertenece a un usuario y a **un solo brain**, y nunca puede tener más rol que quien lo creó. El máximo es **curador**: ningún token administra la instancia. Un token se anula si su cuenta se deshabilita o se elimina. Solo vale en su propio brain, aunque ese brain reciba memoria de otros por federación. Ver [[Conectar agentes]].

## Reglas de protección
- No puedes deshabilitarte, eliminarte ni quitarte el rol de administrador a ti mismo.
- No se puede eliminar ni degradar al **último administrador activo**.
- Los roles que dan los grupos del proveedor de identidad se **retiran** cuando la persona sale del grupo, pero los puestos a mano no se tocan nunca y por grupo nunca se da «propietario». Ver [[Identidad OIDC]].

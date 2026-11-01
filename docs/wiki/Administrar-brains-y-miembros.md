[English](Brains-and-members) · **Español**

# Administrar brains y miembros

Sección **Acceso al brain** de la administración. Tiene cinco tarjetas: el **brain activo**, sus **miembros**, la **federación**, los **secretos** (solo administradores del brain) y sus **tokens de API**. El brain activo es el que eliges en el selector de la barra lateral.

## Crear un brain
Solo el **administrador de la instancia**. Botón **Crear brain**:
- **Slug:** identificador permanente en minúsculas, números y guiones (2–41 caracteres). Va en las direcciones de la API (`/api/brains/<slug>/…`).
- **Nombre:** el que verás en la interfaz.
- **Descripción** (opcional): de qué trata el brain. El **decisor** la usa, junto con la ontología del brain, para juzgar si una propuesta encaja en él ([[Proveedores de IA]]). Merece la pena rellenarla si usas un decisor.
- **Grafo existente (opcional):** nombre del grafo en FalkorDB que usará el brain (letras, números, `_` y `-`). Vacío = grafo nuevo con el nombre del slug. Si ya existe un grafo con ese nombre, el brain lo **adopta**; si no, el grafo se crea al escribir en él por primera vez.

Como administrador de la instancia, eres propietario implícito del brain que creas.

## Editar un brain
Administradores del brain (botón **Editar**):
- **Nombre** y **Descripción**.
- **Slug.** Si lo cambias, **los tokens siguen funcionando** pero debes **actualizar la URL** en tus hooks y plugins.
- **Grafo** (solo el administrador de la instancia): cambiarlo **copia el grafo con el nuevo nombre, reescribe el identificador de grupo de cada nodo y arista y verifica los conteos**. El **original se conserva** como copia de seguridad: bórralo cuando hayas comprobado que todo está bien. Los agentes que escriban directamente en Graphiti con el nombre antiguo seguirán escribiendo en el grafo viejo: hay que repuntarlos.

## Borrar un brain
Solo el **propietario**. Hay que **escribir el slug** para confirmar. Se eliminan sus miembros, tokens de API, propuestas, ontología, correcciones de tipos, documentos, el índice de texto y sus concesiones de federación. Opcionalmente se **borra también el grafo** de FalkorDB (episodios, entidades y hechos). Si no lo marcas, el grafo se conserva sin brain y puede volver a asociarse creando un brain con ese nombre de grafo. **No se puede deshacer.**

## Miembros
Quién tiene acceso al brain y con qué rol ([[Roles y permisos]]). Solo los administradores del brain gestionan sus miembros.
- **Añadir por email:** escribe el correo y elige el rol. Si esa persona **ya tiene cuenta**, obtiene acceso al momento. Si **no**, se crea una cuenta **invitada**: podrá entrar cuando acepte una invitación ([[Administrar usuarios]]) o, si usas OIDC, al iniciar sesión con ese email verificado.
- **Cambiar el rol** de un miembro.
- **Quitar:** la persona pierde el acceso al brain. **Sus tokens de API siguen existiendo** hasta que se revoquen.
- No puedes asignar ni modificar un rol **superior al tuyo**. Los administradores de la instancia aparecen marcados como propietarios implícitos.

## Federación
Presta la memoria de este brain, solo para leer, a otro brain, o mira qué brains le prestan la suya. Los administradores del brain conceden, cambian y revocan; cualquiera con acceso al brain ve lo que recibe. Ver [[Federación]].

## Secretos
Qué hacer cuando una propuesta o un documento lleva una contraseña, un token o una clave: **enmascararlo** (lo predeterminado), **bloquearlo** o **solo avisar**, además de una lista de excepciones y **Analizar lo ya guardado**. Solo los administradores del brain ven esta tarjeta. Ver [[Secretos]].

## Retención
Cuánto se conserva lo que ya no sirve, solo para el **propietario** del brain (o el administrador de la instancia):
- **Texto de las propuestas rechazadas:** pasados estos días desde que se rechazó, una propuesta pierde su texto (título, cuerpo, origen, nota de revisión, el razonamiento del decisor y el detalle de la corrección). Quedan su estado, sus autores y sus fechas, y [[Propuestas]] muestra «(texto purgado)».
- **Trabajos terminados:** los trabajos terminados, fallidos y cancelados del brain se borran pasados estos días, antes que con el plazo general de la instancia.

Un campo vacío usa el plazo de la instancia ([[Referencia de ajustes]]: `retention_rejected_days`, `retention_jobs_days`) y **0 conserva para siempre**. Por defecto no hay plazo, así que no se purga nada hasta que alguien lo fije. Una tarea diaria los aplica y deja un resumen (la tarjeta enseña el último); **Purgar ahora** la lanza en el momento. Cada cambio queda en la auditoría (`brain.retention`). La auditoría y los episodios nunca se purgan desde aquí.

## Exportar
Una copia de este brain en un paquete (grafo, curación, propuestas, documentos y consultas de referencia; nunca miembros, tokens ni secretos), cifrada si se quiere, para guardarla aparte o llevarla a otra instancia. Se prepara como un trabajo y se descarga una vez. Solo los administradores del brain ven esta tarjeta. Ver [[Exportar un brain]].

## Importar un brain
El administrador de la instancia puede crear un brain nuevo a partir de un paquete exportado, completo o solo su estructura (ontología y alias). El paquete se comprueba entero antes de escribir nada, y un fallo elimina lo que se haya creado. Ver [[Importar un brain]].

## Tokens de API del brain
Tokens para plugins y MCP, acotados a este brain. El rol del token **nunca supera el tuyo** y no puede ser administrador. Se muestran **una sola vez** al crearlos. Puedes ver el prefijo, el propietario y el último uso, y **revocarlos**. Uso en [[Conectar agentes]]. Tus propios tokens de todos los brains están también en [[Mi cuenta]].

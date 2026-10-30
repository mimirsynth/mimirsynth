[English](Entity-types) · **Español**

# Tipos de entidad

Pestaña **Tipos de entidad** de [[Vocabulario]]. Lista cada tipo que tienen las entidades del grafo (Servicio, Persona, Servidor…) con su **número de entidades** y su **descripción**.

## La tabla
- **Tipo:** el nombre. Si el tipo existe en el grafo pero **no está definido en la ontología**, lleva la etiqueta «fuera de la ontología».
- **Entidades:** cuántas entidades tienen ese tipo (filtrable por «en la ontología / fuera»).
- **Descripción:** cuándo se usa ese tipo. **Es importante**: guía tanto al LLM que extrae como al decisor del corrector.

## Acciones (administrador del brain)
### Crear tipo
**Crear tipo** añade uno nuevo a la ontología. El **nombre** va en *PascalCase*, sin espacios (`Service`, `PersonaExterna`). La **descripción** debe decir **cuándo** se usa, con ejemplos y, si hace falta, **cuándo no** («Una aplicación o servicio de software con nombre propio. NUNCA una organización.»).

### Editar / Añadir a la ontología
**Editar** cambia la descripción de un tipo definido. **Añadir a la ontología** da de alta un tipo que ya existía en el grafo pero fuera de ella.

### Renombrar o fusionar
**Renombrar / fusionar** cambia el tipo de **todas las entidades** de ese tipo a uno nuevo:
- Si eliges un tipo **nuevo**, es un **renombrado**.
- Si eliges uno **existente**, es una **fusión**.
Antes de aplicar ves una **vista previa** con cuántas entidades se verán afectadas. El nombre destino debe seguir el formato `PascalCase`.

### Quitar de la ontología
**Quitar** saca el tipo de la ontología: deja de guiar la extracción y el corrector. **Las entidades que ya tienen ese tipo no cambian**: pasan a mostrarse «fuera de la ontología». Las reglas del mapa que usan el tipo se eliminan.

## Historial y deshacer
Debajo de la tabla, **Cambios recientes** lista los 15 últimos cambios de vocabulario del brain: los hechos aquí, las ediciones de la ontología, las fusiones de entidades y los hechos invalidados al resolver [[Contradicciones]]. El **último** tiene un botón **Deshacer** (administradores del brain; mientras no se haga otro cambio después); los revertidos se marcan como «deshecho».

## Buenas prácticas
- Pocos tipos y bien descritos funcionan mejor que muchos solapados.
- Evita tipos «cajón de sastre» (Object, Topic): atraen todo lo que el modelo no sabe clasificar. Si aparecen, usa el [[Corrector de tipos]].
- Cambia las descripciones con cuidado: afectan a las **ingestas futuras**, no a lo ya guardado.

[English](Ontology) · **Español**

# Ontología

La **ontología** de un brain define qué **tipos de entidad** y **tipos de relación** puede extraer el ingestor al escribir, y entre qué tipos se permite cada relación. **Sin ontología, el modelo inventa tipos y relaciones libremente**, y el grafo se llena de variantes y ruido. Con ella, la extracción es mucho más consistente. Además, le dice al [[Corrector de tipos]] qué revisar, al decisor de qué trata el brain (ver [[Propuestas]]) y a [[Contradicciones]] qué relaciones son de un solo valor.

> Los cambios de ontología **guían las ingestas futuras** y no modifican lo que ya está en el grafo. Para arreglar lo ya guardado usa [[Tipos de entidad]], [[Relaciones y alias]] y el [[Corrector de tipos]].

Pestaña **Ontología** de [[Vocabulario]]. Todos pueden verla; solo la editan los administradores del brain.

## Qué contiene
1. **Tipos de entidad** (se editan en su propia pestaña, [[Tipos de entidad]]).
2. **Tipos de relación:** nombre en *PascalCase* sin espacios (`RunsOn`), una **descripción** de cuándo se usa y, opcionalmente, la marca **Un solo valor a la vez** (ver abajo).
3. **Reglas del mapa:** qué relaciones están permitidas entre qué pares de tipos. Por ejemplo, entre *Service* y *Host* se permite `RunsOn`. Una regla tiene **Origen**, **Destino** y la lista de **relaciones permitidas** entre ambos.
4. **Instrucciones de extracción:** texto libre (hasta 4.000 caracteres) que se entrega al LLM: qué es importante, cómo clasificar, qué evitar.

## Paquetes estándar
Un **paquete** es una ontología de partida ya preparada. Cada tipo dice qué es, cuándo usarlo y cuándo no, con ejemplos; cada paquete trae instrucciones de extracción y está alineado con vocabularios conocidos (schema.org, FOAF, Dublin Core, DOAP, ITIL/CMDB…). Los nombres y descripciones de los tipos están en inglés, que es lo que mejor leen los modelos; tus notas pueden estar en cualquier idioma.

| Paquete | Para | Tipos de entidad | Tipos de relación |
|---|---|---|---|
| `general` | Un cuaderno mixto o personal: personas, organizaciones, lugares, eventos, documentos, proyectos, decisiones, temas | 8 | 10 |
| `infrastructure` | Infraestructura y operaciones TI: hosts, guests, servicios, redes, almacenamiento, incidentes, cambios, runbooks | 16 | 15 |
| `team-projects` | Trabajo de equipo y proyectos: personas, equipos, proyectos, tareas, hitos, reuniones, decisiones, riesgos | 11 | 14 |
| `personal-family` | Vida familiar: personas, hogar, mascotas, lugares, viajes, citas, pertenencias, suscripciones, documentos | 12 | 11 |
| `software-knowledge` | Ingeniería de software: repositorios, aplicaciones, componentes, librerías, APIs, entornos, versiones, errores, decisiones | 14 | 15 |

El antiguo paquete `generic` es ahora `general` (el nombre antiguo sigue funcionando). Los brains que lo aplicaron conservan su ontología. Al elegir un paquete en **Aplicar paquete** se muestran su descripción, su tamaño, su versión y los estándares en los que se basa (**Basado en:**). Detalles: [`docs/es/ONTOLOGY.md`](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/ONTOLOGY.md).

## Aplicar un paquete
- **Brain sin ontología:** elige un paquete y pulsa **Aplicar**.
- **Brain con ontología:** tienes dos opciones:
  - **Añadir lo que falta:** suma los tipos, relaciones y reglas del paquete que no tienes, y no toca nada de lo que ya hay.
  - **Sustituir ontología:** pide confirmación y después **reemplaza** los tipos, las relaciones, el mapa y las instrucciones actuales por los del paquete, **incluidos los cambios hechos a mano**. Úsalo al principio, no sobre una ontología que has trabajado.

Las entidades que ya están en el grafo no cambian nunca.

### Actualizaciones de paquete
Los paquetes tienen **versión**, y el brain recuerda qué paquete y qué versión aplicó. Cuando sale una versión nueva, la pestaña avisa de que hay una versión nueva del paquete, con la versión instalada y la disponible y un botón **Actualizar**, que **añade lo que falta** (tipos, relaciones, reglas) sin tocar nada de lo que tienes ni de lo que cambiaste a mano.

## Editar a mano
- **Relaciones:** añadir, editar la descripción o la marca de un solo valor, o quitar. Al quitar una relación se quita también de las reglas del mapa que la usan (el aviso indica cuántas).
- **Reglas del mapa:** añadir o editar (elige origen, destino y marca las relaciones permitidas) o quitar.
- **Instrucciones:** edita el texto de guía.

Tras cada cambio, un aviso ofrece **Deshacer**.

## Relaciones de un solo valor
Marca **Un solo valor a la vez** en un tipo de relación solo si un sujeto **no puede tener dos destinos vigentes a la vez**: dónde está instalado un equipo físico, a quién informa una persona. Las relaciones marcadas llevan la etiqueta **un solo valor**, y dos destinos vigentes del mismo tipo pasan a ser una posible contradicción en [[Contradicciones]].

**Ninguna relación viene marcada por defecto, tampoco en los paquetes**, porque muchas parecen de un solo valor y no lo son. Mide antes con **Medir en todas las relaciones** en [[Contradicciones]] y marca solo las relaciones con una proporción baja de sujetos con varios destinos.

## Escribir buenas descripciones
El LLM decide mirando las descripciones. Las buenas:
- Dicen **cuándo sí** y **cuándo no**, con ejemplos reales.
- Resuelven las confusiones típicas de tu dominio («los servidores físicos son *Host*, nunca *Location*»).
- Son específicas y cortas.

## Qué pasa si una extracción se sale de la ontología
La ingesta no la bloquea: el **informe de la propuesta** ([[Propuestas]]) indica cuántas entidades quedaron *sin tipo* y qué tipos se salieron. Así puedes ver qué le falta a la ontología. El [[Corrector de tipos]] revisa después esas entidades.

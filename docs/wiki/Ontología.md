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
| `infrastructure` | Infraestructura y operaciones TI: hosts, guests, servicios, software, modelos de IA, redes, almacenamiento, incidentes, cambios, runbooks | 18 | 15 |
| `team-projects` | Trabajo de equipo y proyectos: personas, equipos, proyectos, tareas, hitos, reuniones, decisiones, riesgos | 11 | 14 |
| `personal-family` | Vida familiar: personas, hogar, mascotas, lugares, viajes, citas, pertenencias, suscripciones, documentos | 12 | 11 |
| `software-knowledge` | Ingeniería de software: repositorios, aplicaciones, componentes, librerías, modelos de IA, APIs, entornos, versiones, errores, decisiones | 15 | 15 |

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

## Vida útil y hechos a revisar
Hay datos que se quedan viejos sin que nadie los contradiga: una IP, una versión, quién lleva un servicio. Un tipo de relación puede tener una **vida útil** en días (en el diálogo de edición de la relación, **Vida útil (días)**); ninguno la tiene por defecto, ni siquiera en los paquetes, así que nada cambia hasta que un brain la ponga.

Un hecho vigente de esa relación cuya última fecha (su última confirmación o, si no la hay, su fecha de validez) es más antigua que su vida útil queda **a revisar**:
- En el recall pesa menos (`recall_stale_weight`, 0,6 por defecto) y sale marcado «sin confirmar desde …», también en el contexto que lee el agente.
- Aparece en Calidad del contenido → **A revisar**, para curadores: **Confirmar** renueva su fecha (se guarda en PostgreSQL; el grafo no se toca) e **Invalidar** funciona como desde Hechos. Las confirmaciones quedan en la auditoría (`fact.confirm`).
- Una vez al día, el aviso `facts.stale` los cuenta por brain, sin ningún texto.

Un hecho sin fecha de validez (importado de otro sistema, por ejemplo) nunca caduca por fecha: no hay desde dónde medir. Los hechos prestados no se marcan aquí: la vida útil es cosa del brain que presta. Una relación genérica como `RELATES_TO` no puede tener vida útil.

## Retiradas y revisiones de tema
Un tipo de relación puede **marcar una retirada** (en el diálogo de edición de la relación, **Retirada**: se retira el origen o el destino; la tabla la muestra en su propia columna). Un hecho nuevo de esa relación, por ejemplo «Postmark sustituyó a Sendgrid», encola solo una revisión del tema de la entidad retirada, para que los hechos que aún la describen como vigente lleguen a un curador: ver [[Calidad del contenido]] → Temas. Los nombres habituales (`REPLACED_BY`, `SUPERSEDES`, `MIGRATED_TO`…) se reconocen sin marca, incluidos `MigratedTo` y `Supersedes` de los paquetes; la marca es para las relaciones propias de un brain, y manda sobre la lectura habitual de un nombre. Una relación genérica como `RELATES_TO` no puede marcar una.

## Escribir buenas descripciones
El LLM decide mirando las descripciones. Las buenas:
- Dicen **cuándo sí** y **cuándo no**, con ejemplos reales.
- Resuelven las confusiones típicas de tu dominio («los servidores físicos son *Host*, nunca *Location*»).
- Son específicas y cortas.

## Lo que nunca se crea como entidad
Sea cual sea la ontología, algunos nombres que extrae el LLM son un detalle de un hecho, no una cosa propia: una opción de línea de comandos (`--help`, `tool --help flag`), la ruta de un campo en código (`SectionVMInfo.uptime`), una ruta o un fichero de código (`utils/secrets.py`), una URL, una fecha sola (`1 October 2026`) o una frase (cinco palabras o más que empiezan en minúscula, como «sync push from A to B»). Se descartan antes de escribir las entidades, así que los hechos se extraen entre las entidades que quedan y el detalle se queda en su texto. Si el nombre descartado era el único otro extremo de un hecho, ese hecho no se crea: el episodio conserva la frase y el recall la encuentra entre los fragmentos del episodio. Se conservan a propósito, porque un detalle que se escapa lo recoge después el [[Corrector de tipos]] pero una entidad descartada no vuelve: nombres de host (`api.example.com`), productos escritos como ficheros (`Node.js`, `three.js`, `Newtonsoft.Json`, `docs.rs`), unidades de systemd (`nginx.service`), espacios de nombres (`Microsoft.AspNetCore`), `TCP/IP`, nombres propios que empiezan por una partícula («el Ministerio de Sanidad y Consumo»), versiones sueltas (`3.12.10`) y productos con versión (`Debian 13`), para los que está el tipo `Software` de `infrastructure`. El informe de [[Propuestas]] cuenta lo descartado, por clase.

## Qué pasa si una extracción se sale de la ontología
La ingesta no la bloquea: el **informe de la propuesta** ([[Propuestas]]) indica cuántas entidades quedaron *sin tipo* y qué tipos se salieron. Así puedes ver qué le falta a la ontología. El [[Corrector de tipos]] revisa después esas entidades.

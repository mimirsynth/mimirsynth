[English](../ONTOLOGY.md) · **Español**

# Paquetes de ontología

La ontología de un brain le dice al ingestor qué **tipos de entidad** y de **relación** extraer y qué relaciones se permiten entre qué tipos. Sin ella, el modelo inventa tipos libremente. MimirSynth incluye **paquetes estándar** que puedes aplicar en Vocabulario → Ontología.

| Paquete | Para | Tipos de entidad | Tipos de relación |
|---|---|---|---|
| `general` | Un cuaderno mixto o personal: personas, organizaciones, lugares, eventos, documentos, proyectos, decisiones, temas | 8 | 10 |
| `infrastructure` | Infraestructura y operaciones TI: hosts, guests, servicios, redes, almacenamiento, incidentes, cambios, runbooks | 16 | 15 |
| `team-projects` | Trabajo de equipo y proyectos: personas, equipos, proyectos, tareas, hitos, reuniones, decisiones, riesgos | 11 | 14 |
| `personal-family` | Vida familiar: personas, hogar, mascotas, lugares, viajes, citas, pertenencias, suscripciones, documentos | 12 | 11 |
| `software-knowledge` | Ingeniería de software: repositorios, aplicaciones, componentes, librerías, APIs, entornos, versiones, errores, decisiones | 14 | 15 |

> El antiguo paquete `generic` se sustituyó por `general` (el nombre antiguo sigue funcionando como alias). Los brains que ya lo aplicaron conservan su ontología.

## Criterios de diseño
- **Pocos tipos y claros.** Un tipo existe solo si responde a una pregunta que se hará. Lo demás cae al *último recurso* (`Topic`, `RelatesTo`), que todos los paquetes marcan como tal.
- **Alineados con vocabularios existentes** para que nombres y significado resulten familiares: schema.org (Person, Organization, Place, Event, Project, SoftwareApplication), FOAF, Dublin Core, DOAP, elementos de configuración de ITIL/CMDB y registros de decisiones de arquitectura (ADR). Cada paquete indica en qué estándares se basa.
- **Cada tipo dice qué es, cuándo usarlo y cuándo no**, con ejemplos. El modelo clasifica solo con esa descripción.
- **Descripciones y nombres de tipo en inglés**, que es lo que mejor leen los modelos; la interfaz y tus notas pueden estar en cualquier idioma.
- **Un mapa coherente.** Cada tipo de entidad y de relación aparece en al menos una regla, y las reglas nunca usan tipos que no existen (lo comprueban los tests).

## Versiones y actualizaciones
Cada paquete tiene una **versión**. El brain recuerda qué paquete y qué versión aplicó. Cuando sale una versión nueva, Vocabulario → Ontología ofrece **Actualizar**, que **añade lo que falta** (tipos, relaciones, reglas) y nunca toca lo que ya tienes ni lo que cambiaste a mano. **Sustituir la ontología** lo descarta todo y aplica el paquete tal cual. Las entidades que ya están en el grafo no cambian.

## Relaciones de un solo valor y contradicciones
Un tipo de relación puede marcarse como **de un solo valor a la vez** (`"functional": true`; en Vocabulario → Ontología, «Un solo valor a la vez»): un sujeto no puede tener dos destinos vigentes, como dónde está instalado un equipo o a quién informa una persona. Si los tiene, Vocabulario → **Contradicciones** los enseña para que un curador elija cuál queda vigente; los demás se invalidan con la fecha del que se queda y se puede deshacer desde el historial del vocabulario. No se usa ningún modelo de IA: se propone el hecho con la fecha de validez más reciente. Si dos tienen la misma fecha, o si alguno solo tiene la fecha en que se aprendió (que no dice cuál es más actual), no hay propuesta y decide la persona. Las relaciones genéricas como `RELATES_TO` no se comparan nunca ni se pueden marcar. Un grupo que no es una contradicción se puede ocultar hasta que llegue un hecho nuevo. Una vez al día se busca en cada brain con alguna relación marcada y, si hay casos, llega un aviso (`conflicts.found`, información).

- **Ninguna relación lo es por defecto, tampoco en los paquetes.** Muchas parecen de un solo valor y no lo son: medido en un grafo real, «ubicado en» mezclaba hosts, URLs, VLANs y servicios. Cada brain marca las suyas después de medir.
- **Medir antes de marcar:** «Medir en todas las relaciones» cuenta, sin cambiar nada, qué proporción de sujetos tiene más de un destino vigente en cada relación, de menor a mayor. Las candidatas son las de proporción baja con algún caso, no las de proporción alta. También desde la línea de comandos, en solo lectura: `python -m mimirsynth.conflicts <grafo> [--brain-id N]`.
- Las relaciones se comparan tras normalizar formato y alias, y **solo se comparan destinos del mismo tipo de entidad**: «X ubicado en un host» y «X ubicado en una VLAN» no se contradicen. Dos destinos con el mismo nombre salvo mayúsculas y espacios cuentan como el mismo (eso es un duplicado del vocabulario, no una contradicción).

## Corrector de tipos
El corrector de tipos (Vocabulario → Corrector de tipos) no supone ningún dominio: cada paquete indica, en su bloque `retype`, qué se revisa y qué se aparta antes de preguntar al decisor.

```json
"retype": {"review_first": ["Topic", "Item"], "doubtful_rules": []}
```

- **Qué se revisa**, por este orden: entidades sin tipo, entidades cuyo tipo **no está en la ontología del brain** (por ejemplo, los tipos por defecto de un agente que escribe directamente en Graphiti) y entidades de los tipos de `review_first` (los comodines o los que más se confunden en ese paquete). El resto no se toca. Los empates se resuelven por id, así que dos análisis seguidos mantienen el orden.
- **Qué se aparta como dudoso** sin preguntar al decisor: un nombre de cinco palabras o más (en cualquier brain) y, solo si el paquete las activa, las reglas técnicas `file` (ruta o nombre de fichero), `option` (opción de línea de comandos), `code` (expresión de código), `version` (versión al final del nombre) y `problem` (palabras como *bug*, *error*, *fix*). `infrastructure` activa las cinco; `software-knowledge`, solo `option`, porque las demás descartarían sus propios repositorios, documentos, APIs y versiones; el resto de paquetes, ninguna.
- **La pregunta del decisor** no excluye errores ni procedimientos si la ontología tiene un tipo para ellos (`Bug`, `Incident`, `Runbook`…).
- Un brain con la ontología escrita a mano, o cuyo paquete ya no existe, usa lo mínimo: revisa `Object`, `Thing` y `Topic` y no aplica ninguna regla técnica.

El bloque se lee del paquete al ejecutar el corrector, así que cambiarlo no exige una versión nueva del paquete. Los tests comprueban que cada bloque solo usa tipos de su paquete y reglas conocidas, y que las reglas de un paquete no descartan los ejemplos de sus propios tipos.

## Escribir la tuya
Parte del paquete más cercano y edita tipos, relaciones, mapa e instrucciones en la interfaz. Mantén las descripciones cortas y explícitas sobre cuándo **no** usar un tipo.

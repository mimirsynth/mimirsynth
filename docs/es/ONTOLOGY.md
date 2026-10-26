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

## Escribir la tuya
Parte del paquete más cercano y edita tipos, relaciones, mapa e instrucciones en la interfaz. Mantén las descripciones cortas y explícitas sobre cuándo **no** usar un tipo.

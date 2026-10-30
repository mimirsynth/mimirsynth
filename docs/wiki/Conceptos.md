[English](Concepts) · **Español**

# Conceptos

Antes de usar MimirSynth conviene tener claras unas pocas ideas. Todo lo demás se apoya en ellas.

## Memoria con historia
Una base de datos normal guarda el valor actual y olvida el anterior. MimirSynth guarda **qué se sabía y cuándo**. Si un día cuentas «la base de datos corre en el servidor 1» y semanas después «ahora corre en el servidor 2», el primer dato no se borra: se **invalida** (deja de ser cierto desde una fecha) y el segundo pasa a ser el vigente. Puedes preguntar por el estado actual o por cómo era en cualquier momento del pasado.

## Los cuatro niveles de información
| Nivel | Qué es | Dónde lo ves |
|---|---|---|
| **Episodio** | Un texto tal cual se contó: una nota, un mensaje, una propuesta aprobada. Es inmutable. | [[Diario]] |
| **Entidad** | Una «cosa» a la que se refieren los textos: una persona, un servidor, una aplicación, un proyecto. | [[Grafo]], [[Vocabulario]] |
| **Hecho** | Una afirmación entre dos entidades, con fecha de inicio y, si deja de ser cierta, de fin. («El servicio X corre en el servidor Y».) | [[Hechos]] |
| **Documento** | Un fichero o una página de una wiki: se conserva el original y se busca por su contenido, pero no se convierte en hechos. | [[Conocimiento]] |

Los hechos y las entidades **se extraen automáticamente de los episodios** con un modelo de lenguaje (LLM). Los documentos, en cambio, se indexan y se citan siempre con su procedencia.

## Orígenes
Cada entidad y cada hecho recuerdan **de dónde vienen**: los episodios que los mencionan y, a través de ellos, el tipo de fuente (texto, mensaje, documento, carpeta, wiki…), la persona o el token de agente que los propuso y el documento desde el que se promovieron. El [[Grafo]] puede dibujar esos orígenes como **halos** alrededor de los nodos que respaldan, y lo que confirman dos o más orígenes destaca como más sólido.

## Brain
Un **brain** es un dominio de conocimiento aislado: tiene su propio grafo, su ontología, sus documentos, sus miembros y sus tokens. Sirve para separar, por ejemplo, la memoria técnica de un equipo de la personal de cada miembro. Nada de un brain es visible desde otro, salvo que un administrador de un brain **preste** expresamente su lectura a otro (**federación**): entonces el recall del brain que recibe busca también en lo prestado, marcado con su origen. El préstamo es de solo lectura, en un sentido, revocable y auditado. Con el selector de la barra lateral cambias de brain.

## Propuestas y cuarentena
Lo que escribe un **colaborador** (o un agente con un token de colaborador) **no entra directamente al grafo**: se guarda como una **propuesta** pendiente. La revisa un **curador** (o un modelo «decisor», si está configurado) y solo al aprobarse se ingiere. Así un agente que se equivoca no ensucia la memoria. Las propuestas de un curador se aprueban al enviarlas. Antes de guardarse, toda propuesta pasa por el **detector de secretos** del brain, que enmascara o bloquea las credenciales; una con un posible secreto siempre espera a una persona. Ver [[Propuestas]].

## Ontología y vocabulario
La **ontología** es la lista de tipos de entidad (Servicio, Persona, Servidor…) y de relación (CorreEn, DependeDe…) que el ingestor puede usar. Sin ella el modelo inventa tipos y relaciones libremente, con mucho ruido. Una relación se puede marcar como **de un solo valor** (un valor cada vez, como «vive en»): dos hechos vigentes con valores distintos aparecen entonces como una posible **contradicción** para que un curador la resuelva. El **vocabulario** es la pantalla donde mantienes todo esto: unificar relaciones parecidas, fusionar entidades duplicadas, corregir tipos, resolver contradicciones. Ver [[Vocabulario]].

## Recall
**Recall** es la búsqueda que hace un agente antes de contestar. Combina, sin llamar a un LLM y en una fracción de segundo: hechos vigentes e históricos, fragmentos de los textos originales y (si hay) pasajes de documentos, además de lo que otros brains le prestan. El resultado es un bloque de contexto listo para pegar en el prompt. Lo pruebas a mano en [[Preguntar]]; los agentes lo usan por MCP (la herramienta `recall`) o por la [[API REST]] ([[Conectar agentes]]). Para comprobar que sigue respondiendo bien, un brain puede guardar **consultas de referencia**: preguntas con lo que su recall debe traer y lo que no, que se ejecutan a demanda y antes y después de un cambio de modelo de embeddings.

## Roles
Cada persona tiene un **rol por brain** (lector, colaborador, curador, administrador, propietario) y, además, puede ser **administradora de la instancia**. Ver [[Roles y permisos]].

## Trabajos
Todo lo lento (ingerir una propuesta, indexar un documento, reescanear una carpeta, buscar duplicados, ejecutar las consultas de referencia) se hace en segundo plano y aparece en [[Trabajos]] con su progreso.

## Los tres modelos de IA
MimirSynth necesita, como mucho, tres endpoints compatibles con OpenAI (se configuran en [[Proveedores de IA]]):
- **LLM:** extrae entidades y hechos de las propuestas aprobadas. Su tamaño decide la calidad del grafo.
- **Embeddings:** convierte textos en vectores para buscar por significado. Se puede cambiar después, pero eso recalcula todos los vectores.
- **Decisor** (opcional): modelo de decisión cerrada que aprueba automáticamente lo claramente factual y dentro del ámbito del brain, y sugiere correcciones de tipos. Nunca rechaza por su cuenta.

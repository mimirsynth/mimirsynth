[English](FAQ) · **Español**

# Preguntas frecuentes

## General
**¿Qué diferencia hay con una base de datos vectorial normal?**
Una base vectorial devuelve textos parecidos. MimirSynth además extrae **hechos con fechas de validez**, así que sabe que algo *dejó de ser cierto* y no te devuelve el dato antiguo como si fuera actual. Y mantiene los textos originales y los documentos para detalles.

**¿Necesito un LLM?**
Para **ingerir** (extraer hechos) sí. Para **buscar** no: el recall no usa ningún LLM. Los embeddings sí necesitan un modelo de embeddings.

**¿Funciona con modelos locales?**
Sí. Cualquier endpoint compatible con OpenAI (Ollama, vLLM, LM Studio…) sirve para LLM, embeddings y decisor. Los modelos grandes dan mejor extracción.

**¿Puedo usarlo sin FalkorDB incluido?**
Sí, apunta `MIMIRSYNTH_FALKOR_HOST` a tu FalkorDB. Ver [[Instalación]].

**¿Qué es un brain y cuántos necesito?**
Un dominio aislado. Uno basta para empezar; crea más para separar equipos, proyectos o personas. Ver [[Conceptos]].

## Escritura
**Mi agente escribe pero no veo nada nuevo.**
Si usa un token de colaborador, la propuesta está **pendiente**: revísala en [[Propuestas]]. Una propuesta en la que el detector de secretos marcó algo también espera a un curador, la envíe quien la envíe. Si ya está aprobada, mira [[Trabajos]] por si la ingesta falló o no hay LLM configurado.

**¿Puedo editar un episodio?**
No, son inmutables. Corrige el **hecho** ([[Hechos]]) o aporta un episodio nuevo que lo contradiga.

**¿Cómo borro algo que se guardó por error?**
Borra o invalida el hecho en [[Hechos]]. Si fue un secreto, además considera **rotar el secreto**: el texto original sigue en el episodio y pudo enviarse al LLM de extracción. Para evitarlo, el detector de secretos enmascara o bloquea las credenciales antes de guardar una propuesta, según la política del brain (ver [[Propuestas]]).

**Hay vigentes a la vez dos hechos que no pueden ser ciertos los dos.**
Marca la relación como de un solo valor en la [[Ontología]] y resuelve el caso en [[Contradicciones]], que además te ayuda a medir qué relaciones conviene marcar.

**El sistema crea entidades duplicadas o relaciones raras.**
Es normal al principio. Define una [[Ontología]], unifica con [[Relaciones y alias]] y [[Fusionar duplicados]].

## Documentos
**¿Qué formatos admite?** Markdown, texto, HTML, PDF con texto y documentos de Office (`.docx`, `.pptx`, `.xlsx`, `.odt`). Ver [[Conocimiento]].

**¿Se pueden indexar mis wikis?** Sí, en solo lectura: Outline, Confluence (Cloud y Data Center) y Notion. Los adaptadores de Confluence y Notion aún no se han validado contra una instancia real; Docmost todavía no está soportado. Un almacén de Obsidian se indexa como carpeta. Ver [[Memoria documental]].

**El mismo documento está en dos fuentes. ¿Se indexa dos veces?** No: la copia queda como duplicado y solo se indexa la más antigua. **Buscar duplicados** en [[Conocimiento]] revisa los documentos indexados antes de que esto existiera.

**¿Se convierte un documento en hechos?** No; se cita. Para convertir un pasaje, **promuévelo a memoria**.

## Usuarios y seguridad
**¿Cómo invito a alguien?** [[Administrar usuarios]]. Con SMTP configurado recibe un correo; sin él, le pasas el enlace.

**He perdido el móvil del doble factor.** Usa un código de recuperación o una llave de acceso (passkey), o pide a un administrador que lo restablezca ([[Mi cuenta]]).

**¿Puedo usar mi proveedor de identidad (Google, Entra, Keycloak…)?** Sí, ver [[Identidad OIDC]]. Sigue haciendo falta una cuenta o invitación (o alta automática por dominio).

**¿Mis datos salen del servidor?** Los textos de las propuestas se envían al **LLM** configurado para extraer los hechos, y los textos a indexar al modelo de **embeddings**. Con modelos locales, nada sale. El detector de secretos enmascara o bloquea credenciales en propuestas y documentos antes de guardarlos o indexarlos, pero no te fíes solo de él: no guardes secretos en la memoria, guarda solo dónde están.

**¿Qué pasa si pierdo `MIMIRSYNTH_SESSION_SECRET`?** Los secretos guardados cifrados en la base de datos dejan de descifrarse y hay que reintroducirlos: claves de proveedores, contraseña SMTP, secretos OIDC, claves de wikis y secretos de los canales de notificación. Los secretos del doble factor por aplicación de autenticación también se cifran con él, así que esos códigos dejan de aceptarse. Las sesiones se invalidan. El resto de datos no se ve afectado.

## Operación
**¿Cómo actualizo?** [[Actualización y copias de seguridad]].

**¿Cuántos recursos necesita?** Unos 2 GB de RAM para la aplicación, PostgreSQL y FalkorDB con un uso moderado. El LLM y los embeddings son aparte.

**¿Dónde está el código de instalación?** En el registro del contenedor, mientras no haya administrador: `docker compose logs mimirsynth | grep -A3 "PRIMER ARRANQUE"`.

**¿Hay API?** Sí: la [[API REST]], y un servidor MCP con las herramientas `recall` y `remember` para agentes ([[Conectar agentes]]).

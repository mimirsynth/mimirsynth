[English](Quick-start) · **Español**

# Guía rápida

De una máquina vacía a una memoria funcionando con un agente conectado, en unos 15 minutos. Los detalles de cada paso están en las páginas enlazadas.

**Necesitas:**
- **Docker con Compose v2** (y `curl`).
- Un endpoint **compatible con OpenAI** para **embeddings** (p. ej. [Ollama](https://ollama.com) con `nomic-embed-text`) y otro para el **LLM** que extrae los hechos. Pueden ser locales o de un proveedor en la nube, y son independientes: embeddings en local y un LLM por API es una combinación válida. Sin los dos la instancia arranca, pero no hay nada útil que ver: las propuestas no se ingieren y el recall no devuelve nada.

## 1. Prepara la máquina
En un servidor Linux vacío (Debian, Ubuntu), instala `curl` y Docker; en macOS o Windows, instala [Docker Desktop](https://docs.docker.com/desktop/).
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker    # usar docker sin sudo
docker compose version                               # debe responder v2.x
```
**Si los modelos van en Ollama**, descárgalos antes (`ollama pull nomic-embed-text` y un modelo de extracción, ver el paso 4). Con Ollama en el **mismo host Linux**, haz que escuche en todas las interfaces para que el contenedor llegue a él: ver [Preparar Ollama](Instalaci%C3%B3n#preparar-ollama).

## 2. Arranca la aplicación
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
# edita .env: define POSTGRES_PASSWORD y MIMIRSYNTH_SESSION_SECRET (openssl rand -hex 32)
docker compose --profile bundled up -d
```
Abre `http://localhost:8000`. Más detalle en [[Instalación]].

## 3. Crea tu cuenta de administrador
La primera vez la pantalla pide un **código de instalación** que sale en el registro del servidor:
```bash
docker compose logs mimirsynth | grep -A3 "PRIMER ARRANQUE"
```
Pégalo y escribe tu nombre, tu email y una contraseña (de al menos 12 caracteres; el formulario marca cada regla mientras escribes). Ya estás dentro como administrador de la instancia y llegas a **Primeros pasos**: un botón **Crea tu primer brain** y una lista corta (modelos de IA, token de API, conectar un agente) con un enlace a cada pantalla.

## 4. Configura los modelos de IA
En **Administración → Modelo LLM** añade un motor: endpoint (URL base), clave y modelo. Pulsa **Probar** y márcalo como **Por defecto**. Repite en **Embeddings** (p. ej. `nomic-embed-text`, 768 dimensiones). Ver [[Proveedores de IA]].

Qué modelo de extracción: en local, un modelo *instruct* de unos **14B parámetros o más** (p. ej. `qwen2.5:14b-instruct`, unos 10 GB de memoria); por API, un modelo pequeño y barato con salida estructurada. Los de 4B o menos bastan para probar la instalación, no para una memoria que quieras conservar: espera entidades mal formadas o que se pierden. Evita los modelos que «razonan» por defecto, salvo que lo desactives.

> **Elige con cuidado el modelo de embeddings.** Se puede cambiar después (**Reindexar** en Administración → Embeddings), pero eso recalcula todos los vectores de todos los brains.

## 5. Crea un brain
Pulsa **Crea tu primer brain** (o **Administración → Acceso al brain → Crear brain**), ponle nombre y, si quieres, una descripción, y aplica un **paquete de ontología** en *Vocabulario → Ontología*. Ver [[Administrar brains y miembros]].

## 6. Mete tu primera memoria
Ve a **Propuestas → nueva propuesta**: escribe un título y un texto con un dato concreto, con nombres y fechas exactas («El 12 de octubre migramos la base de datos de producción al servidor db02»). Como administrador se aprueba al enviarla y empieza a ingerirse (verás el progreso en **Trabajos**). Cuando termine, mira **Hechos**, **Diario** y **Grafo**.

## 7. Pregúntale algo
En **Preguntar** escribe «¿dónde está la base de datos de producción?». Verás los hechos, los fragmentos de los textos originales, los pasajes de documentos si los hay y el bloque de contexto que recibiría un agente. Ver [[Preguntar]].

## 8. Conecta tu primer agente
En **Mi cuenta → Tokens de API**, crea un token para ese brain con el rol **Colaborador** (solo se muestra una vez). Con Claude Code, por MCP:
```bash
claude mcp add --transport http mimirsynth "http://localhost:8000/api/brains/mi-brain/mcp" --header "Authorization: Bearer mst_..."
```
El agente ya puede leer la memoria (`recall`) y proponer hechos nuevos (`remember`). Lo que propone un colaborador queda en cuarentena en **Propuestas** hasta que lo aprueba un curador o el decisor. Otros agentes y la API HTTP: [[Conectar agentes]]; las opciones de Claude Code: [[Integración con Claude Code]].

## 9. (Opcional) Producción, documentos, usuarios y correo
- Ponlo detrás de HTTPS ([[HTTPS y proxy inverso]]) y apunta un monitor externo a `/api/health`: los avisos integrados no pueden avisar de que se ha caído PostgreSQL ([Vigilar la instancia](Instalaci%C3%B3n#vigilar-la-instancia)).
- Sube ficheros o conecta una carpeta o wiki en **Conocimiento** ([[Conocimiento]], [[Memoria documental]]).
- Invita a más personas en **Administración → Usuarios** ([[Administrar usuarios]]); configura el correo SMTP para que reciban la invitación ([[Correo SMTP]]).
- Exige el doble factor o entra con llaves de acceso ([[Seguridad y doble factor]]).

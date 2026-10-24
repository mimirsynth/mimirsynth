# MimirSynth para Claude Code

Hook `UserPromptSubmit` que consulta MimirSynth antes de cada prompt e inyecta los hechos y fragmentos relevantes.
Solo lectura (rol de token `reader`).

1. En MimirSynth: Mi cuenta → Tokens de API → crea un token de rol *Lector* para tu brain.
2. Guarda la configuración en `~/.config/mimirsynth/config.json`:
   ```json
   {"url": "https://mimirsynth.example.com", "token": "mst_...", "brain": "mi-brain"}
   ```
3. Añade el hook en `~/.claude/settings.json`:
   ```json
   {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 /ruta/a/mimirsynth_recall.py"}]}]}}
   ```
Si el servidor no responde en 4 s no se inyecta nada y el prompt sigue su curso.


## Escribir memoria (propuestas)

`mimirsynth_remember.py` envía un aprendizaje como propuesta:

```bash
python3 mimirsynth_remember.py --title "Base de datos migrada a db02" --content "El 19-oct la base de datos de producción pasó al servidor db02" --confidence 0.8
```

- Usa `write_token` de `~/.config/mimirsynth/config.json` (token de API con rol **colaborador**: entra en cuarentena y la aprueba un curador o el decisor). Sin él usa `token`, que si es de lector devuelve 403.
- Con un token de curador queda aprobada y se ingiere al momento. Para agentes se recomienda colaborador.
- `--dry-run` muestra la petición sin enviarla.

## Documentos en el recall

Desde la memoria documental, el contexto que devuelve `/recall` puede incluir una sección `## Documentos` con hasta 2 pasajes citados (título, sección, `[doc N, trozo M]`). Solo aparece si hay un pasaje realmente relevante, no pasa de ~600 tokens y se omite si la búsqueda tarda más de 0,6 s. El agente puede pedir más contexto con `GET /api/brains/{slug}/docs/{N}/context?chunk={M}` o el original con `/docs/{N}/file`. Para desactivarlo en una petición, `"docs": 0`; el umbral (Administración → Recuerdo → «Similitud mínima de un pasaje») hay que recalibrarlo si se cambia el modelo de embeddings.

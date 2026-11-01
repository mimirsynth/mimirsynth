[English](README.md) · **Español**

# CheckMK → MimirSynth

`mimirsynth.py` es un script de notificación de CheckMK que envía cada notificación a un **webhook de entrada** de MimirSynth con la
plantilla **CheckMK**. Un problema abre una alerta y su recuperación la cierra; MimirSynth lo convierte en una propuesta de memoria
episódica («qué pasó y cuándo») y agrupa los avisos repetidos. Ver «Webhooks de entrada» en la wiki.

## Instalación
1. En MimirSynth, Administración → Acceso al brain → **Webhooks de entrada** → **Crear webhook**, plantilla **CheckMK**. Copia su
   dirección y su secreto (solo se muestra una vez).
2. En el sitio de CheckMK, con el usuario del sitio:
   ```bash
   cp mimirsynth.py ~/local/share/check_mk/notifications/mimirsynth.py
   chmod +x ~/local/share/check_mk/notifications/mimirsynth.py
   ```
3. Setup → Notifications → añade una regla con el método **MimirSynth** y dos parámetros: la dirección del webhook y su secreto.
   Limítala a los hosts y servicios cuyos problemas merezca la pena recordar.

Solo usa la biblioteca estándar. Envía el contexto de la notificación (las variables `NOTIFY_*`) firmado con HMAC-SHA256 en la cabecera
`X-Hub-Signature-256`. Solo `PROBLEM` y `RECOVERY` se convierten en memoria; los reconocimientos, las paradas programadas y el
flapping se quedan fuera.

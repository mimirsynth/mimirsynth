# Seguridad

## Versiones con soporte
MimirSynth está en desarrollo 0.x: solo se corrige la última versión publicada.

## Cómo informar de una vulnerabilidad
**No abras un issue público.** Usa el aviso privado de GitHub: pestaña *Security → Report a vulnerability* de este repositorio.

Incluye los pasos para reproducirlo, la versión afectada y el impacto que estimas. Responderemos lo antes posible y coordinaremos contigo la divulgación.

## Buenas prácticas de despliegue
- Define un `MIMIRSYNTH_SESSION_SECRET` largo y aleatorio; firma las sesiones y cifra los secretos guardados.
- Sirve la aplicación detrás de HTTPS y activa `MIMIRSYNTH_COOKIE_SECURE=true`.
- No uses `MIMIRSYNTH_AUTH_MODE=off` fuera de desarrollo: desactiva el inicio de sesión.
- Exige el doble factor en Administración → Seguridad de cuentas.
- No expongas FalkorDB ni PostgreSQL fuera de la red del despliegue.

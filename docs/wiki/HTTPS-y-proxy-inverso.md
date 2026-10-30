[English](HTTPS-and-reverse-proxy) · **Español**

# HTTPS y proxy inverso

No publiques el puerto de MimirSynth directamente en Internet sin TLS: las contraseñas, las cookies de sesión y los tokens de API viajarían en claro. Pon delante un **proxy inverso** (Caddy, Traefik, nginx, un túnel…) que termine el HTTPS. El HTTPS es además **imprescindible para las llaves de acceso**: los navegadores solo las ofrecen en un origen seguro.

## Ajustes en MimirSynth
En `.env`:
```bash
MIMIRSYNTH_PUBLIC_URL=https://mimirsynth.ejemplo.com
MIMIRSYNTH_COOKIE_SECURE=true
```
- `PUBLIC_URL` se usa para construir la URL de retorno del inicio de sesión OIDC y los enlaces de invitación y recuperación. Su dominio es también el **identificador de la parte que confía de las llaves de acceso**: una llave solo funciona en el dominio en que se creó, así que fija la dirección definitiva antes de que nadie registre una; cambiar de dominio después las invalida (cada persona conserva su contraseña como alternativa). También se puede poner en *Administración → Identidad*.
- `COOKIE_SECURE=true` hace que la cookie de sesión solo viaje por HTTPS.

## Ejemplo con Caddy
```
mimirsynth.ejemplo.com {
    reverse_proxy localhost:8000
}
```
Caddy obtiene y renueva el certificado solo.

## Ejemplo con nginx
```nginx
server {
    server_name mimirsynth.ejemplo.com;
    client_max_body_size 100m;          # ver nota sobre subidas
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    # listen 443 ssl; ssl_certificate ...; (certificado de tu elección)
}
```

## Subidas de ficheros grandes
La interfaz sube los ficheros **por partes** (por defecto de 64 MB como máximo) para que los proxies con límite de tamaño de petición no los rechacen. Si tu proxy limita las peticiones a menos que eso, baja «Tamaño de cada parte de una subida» en *Administración → Límites* (ver [[Carpetas y límites]]). El tamaño máximo de un fichero se ajusta ahí también.

## Cabeceras de reenvío
MimirSynth usa `X-Forwarded-For` para limitar los intentos de inicio de sesión por IP (contraseña, doble factor y llaves de acceso). Asegúrate de que tu proxy lo envía y de que **no** aceptas esa cabecera de clientes externos sin pasar por el proxy.

## Agentes y monitores
- Los agentes se conectan a la dirección pública: `https://mimirsynth.ejemplo.com/api/brains/<slug>/mcp` para MCP, `…/recall` y `…/proposals` para HTTP ([[Conectar agentes]]). El servidor MCP rechaza las peticiones que un navegador envía desde otro origen; los clientes de agentes no lo envían, así que no hay nada que configurar.
- Un monitor externo en otra máquina debe comprobar `https://mimirsynth.ejemplo.com/api/health` a través del proxy ([Vigilar la instancia](Instalaci%C3%B3n#vigilar-la-instancia)).

## Qué no exponer
- **FalkorDB** y **PostgreSQL** no deben ser accesibles desde fuera de la red del despliegue. El Compose incluido no publica sus puertos: déjalo así.
- La documentación interactiva de la API (`/docs`) es accesible a cualquiera que llegue a la aplicación; los datos siguen protegidos por autenticación.

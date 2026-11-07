[English](Verifiable-facts) · **Español**

# Hechos verificables

Muchos hechos describen un sistema al que se le puede preguntar: dónde corre un servicio, qué dirección o versión tiene, si sigue existiendo. Si nadie los toca, siguen vigentes hasta que alguien los contradice por casualidad. Una **sonda** comprueba un hecho contra un sistema vivo una vez al día mediante un **verificador**, y el recall dice cuándo se comprobó cada uno.

## Verificadores
Un verificador es un plugin pequeño: recibe el hecho (sujeto, relación, valor) y los parámetros de la sonda, y responde **verificado**, **refutado** (con el valor actual si lo sabe) o **no verificable**, con su evidencia.
- **Integrado**, solo el de ejemplo `json_inventory`: lee un fichero JSON `{"clave": "valor"}` (o una lista de valores) que la instancia puede leer, por ejemplo un inventario que otra herramienta exporta a una carpeta montada. Su ajuste es la ruta del fichero; cada sonda dice qué clave leer.
- **Los tuyos**: ficheros `.py` en la carpeta que indica `MIMIRSYNTH_VERIFIERS_DIR` ([[Variables de entorno]]), que se cargan al arrancar. Cargar código externo es una decisión explícita del administrador: sin la variable, no se carga nada más. Un fichero:

```python
from mimirsynth.verify import Param, Result, Verifier, register

@register
class Cmdb(Verifier):
    id, label = "cmdb", "CMDB"
    config = [Param("url", "URL"), Param("token", "Token", secret=True)]   # por brain, lo fijan sus administradores
    params = [Param("ci", "Elemento de configuración")]                   # por sonda

    def check(self, fact, params):
        host = ...  # pregunta a la CMDB en self.v["url"] con self.v["token"] por params["ci"]
        if host is None:
            return Result("unverifiable", "no está en la CMDB")
        return Result("verified", f"CMDB: {host}") if host.lower() == fact["target"].lower() else Result("refuted", f"CMDB: {host}", host)
```

Un verificador tiene que ser de solo lectura y rápido. Un error o una respuesta desconocida cuenta como **no verificable**, con lo que falló.

## Ajustes y credenciales
Un administrador del brain fija los ajustes de cada verificador para el brain (`PUT /api/brains/{slug}/verifiers/{id}` con `values`). Los ajustes secretos se guardan sellados, como los secretos de las wikis y de las notificaciones; nunca se devuelven, y dejar uno vacío conserva el guardado. Las sondas corren en un trabajo en segundo plano con esos ajustes, nunca con los permisos de quien lee el brain.

## Sondas
En la página de una entidad ([[Página de entidad]]), cada hecho vigente tiene **Poner sonda** (o **Sonda**, si ya tiene una), para curadores: elige el verificador y rellena lo que pide, y su último resultado sale junto al hecho (*Verificado*, *Refutado*, *No verificable* o *Sin comprobar*, con la evidencia en su descripción emergente). [[Calidad del contenido]] → **Verificación** lista todas las sondas del brain con su hecho y su último resultado, tiene **Comprobar ahora** y, para los administradores del brain, los ajustes de cada verificador; uno secreto solo dice si está guardado. Por el API, un curador pone una sonda a un hecho vigente: `PUT /api/brains/{slug}/facts/{uuid}/probe` con `verifier` y `params`; `DELETE` la quita y `GET /api/brains/{slug}/probes` las lista con su último resultado. Se comprueban una vez al día (las que llevan 24 horas sin comprobarse), y `POST …/probes/run` las comprueba ahora, hasta 500 por ejecución.

## Qué hace cada resultado
- **verificado:** renueva la fecha de confirmación del hecho, como confirmarlo a mano, así que su vida útil cuenta desde entonces ([[Calidad del contenido]] → A revisar).
- **refutado:** una propuesta que sustituye el hecho, con la evidencia y, si el verificador lo da, el valor actual como texto ([[Propuestas]] → Afirmaciones estructuradas). La decide una persona, como una corrección. Nada cambia por su cuenta, y mientras haya una pendiente para ese hecho no se crea otra.
- **no verificable:** no cambia nada; la sonda dice por qué.

## En el recall
Un hecho con sonda lleva `verification` (`state`, `checked_at`, `verifier`) en el JSON del recall. El contexto que lee el agente añade «[verificado el …]» o «[un sistema lo contradijo el …]» junto a él.

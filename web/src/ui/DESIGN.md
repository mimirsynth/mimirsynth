# Reglas de diseño de la interfaz (derivadas de la identidad de MimirSynth)

Estas reglas completan el artefacto de diseño y son las que aplica el kit `src/ui`. Si cambian, cambian aquí y en `theme.css`, no pantalla a pantalla.

## Forma
- **Una sola esquina para todo: 6 px** (`--ms-radius`): botones, campos, selectores, píldoras, paneles, tablas, avisos y pestañas. 10 px solo en diálogos y paneles laterales (`--ms-radius-lg`).
- Los contadores dentro de una píldora o de un selector usan 4 px.
- Los interruptores (`ThemeToggle`, `Toggle`) conservan su forma de pastilla redonda: es la forma que los identifica como interruptores.

## Alturas
- **Control interactivo: 36 px** (`--ms-control-h`): botones, campos, desplegables, selectores de opción (`Segments`) y botones de icono. En una misma fila todo mide igual.
- **Acción dentro de una fila de tabla: 28 px** (`size="row"` en `Btn`).
- **Etiqueta (`Pill`), no interactiva: 24 px** (`--ms-chip-h`).

## Botones
- **Toda acción es un botón y es secundaria por defecto.** Jerarquías: primario (`kind="primary"`, hidromiel, una por zona), secundario (borde), discreto (`kind="ghost"`, sin borde), peligro (`kind="danger"`, borde rojo) y enlace (`kind="link"`). Cancelar es siempre `ghost` y va a la izquierda de la primaria.
- `variant="link"` solo para un enlace dentro de una frase («Ver todas»), nunca para una acción de barra o de tabla.
- Un botón lleva icono si su verbo tiene uno claro en el registro de `ui/Icon.tsx`; los de solo icono son `IconButton` con ayuda emergente.

## Color y contraste
- Texto sobre superficie: `ink` o `muted`; acento (`accent`) solo para estado activo, enlaces y foco.
- Estados con palabra o fecha, nunca solo por color (`invalidado`, `success`, `warn`, `danger`).
- Rayado de tablas en color sólido: marcado en Superficie, sutil en Pozo.

## Estructura de página
- Cada pantalla es una `Page` que ocupa el alto disponible; su zona de datos es una `FillArea` (crece y desplaza por dentro). Ninguna pantalla fija alturas en `vh`.
- Título (`Title order=2`), texto de ayuda en `Text dimmed`, barra de acciones en una sola fila y después los datos.
- Los detalles se abren en `SidePanel` (lectura) o `Modal` (acción o confirmación).

## Qué no se hace
- Importar de Mantine un elemento que tenga componente en el kit (lo vigila `npm run check:ui`).
- Emoji o caracteres como iconos.
- Sombras; el relieve lo dan el filete de 1 px y el color de superficie.

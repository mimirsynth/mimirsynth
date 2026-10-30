[English](../ACCESSIBILITY.md) · **Español**

# Accesibilidad

MimirSynth aspira a cumplir **WCAG 2.2 nivel AA**. Esta página recoge qué se ha comprobado, cómo repetirlo y qué queda pendiente.

## Qué se comprueba

| Comprobación | Cómo | Resultado (0.6.x) |
|---|---|---|
| Reglas automáticas (WCAG 2.0/2.1/2.2 A y AA, más las buenas prácticas de axe, con el tamaño de los objetivos activado) | [axe-core](https://github.com/dequelabs/axe-core) inyectado con Playwright en **28 pantallas × tema claro y oscuro**, más la pantalla de inicio de sesión | Ninguna infracción |
| Contraste de color | La regla `color-contrast` de axe en todas las pantallas y en los dos temas | Ninguna infracción |
| Teclado | Recorrido con el tabulador por Mi cuenta: todo elemento que recibe el foco lo muestra; las filas que se abren con un clic también se abren con Intro o Espacio; los selectores de tipo radio (`Segments`) se manejan con las flechas | Correcto |
| Reajuste del contenido (WCAG 1.4.10) | Ventana de 320 px de ancho en diez pantallas, buscando desplazamiento horizontal | Sin desplazamiento horizontal |
| Regiones y encabezados | Cada pantalla tiene una región `main` y un `h1` (el título de la página), y las secciones son `h2` | Correcto |

Corregido en esta revisión: las páginas no tenían encabezado de nivel uno y las pantallas de inicio de sesión y de instalación no tenían región `main`; las columnas de acciones de las tablas tenían la cabecera vacía (ahora llevan «Acciones», oculto a la vista); el paginador se salía a 320 px; un encabezado se saltaba un nivel.

## Qué queda pendiente

- **Prueba manual con un lector de pantalla (NVDA, VoiceOver)** en las pantallas principales. Las herramientas automáticas encuentran una minoría de los problemas; el orden de lectura, el anuncio de los cambios (avisos emergentes, estados de carga) y el lienzo del grafo necesitan a una persona con la herramienta. La vista del grafo es un lienzo: sus hechos también están como tabla en Hechos, que es la vía accesible.
- No se han probado el zoom al 200 % y al 400 % en un navegador real ni el modo de alto contraste de Windows.

Si usas tecnologías de apoyo y encuentras una barrera, [abre una incidencia](https://github.com/MimirSynth/mimirsynth/issues).

## Repetir la auditoría

```bash
# sirve la build con una base de datos desechable y un administrador y, después, con Playwright:
npm i axe-core
#   page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' })
#   await page.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa','wcag22aa','best-practice'] }, rules: { 'target-size': { enabled: true } } }))
```
Ejecútala en todas las rutas (con `?brain=<slug>`) con los dos valores de `prefers-color-scheme`. Las pantallas que necesitan la base de datos del grafo se pueden simular con respuestas vacías.

## Reglas para pantallas nuevas

Usa los componentes de `web/src/ui` (ya llevan etiquetas, roles y estilos de foco); da a los botones que solo tienen icono un `aria-label`; no transmitas nunca un significado solo con el color (las etiquetas llevan texto); mantén un único `h1` por pantalla (`PageHeader`) y no te saltes niveles de encabezado; da a las cabeceras de tabla vacías una etiqueta oculta a la vista (`DataTable.ActionsHead`).

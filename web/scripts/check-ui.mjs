// Guardián de la interfaz: las pantallas (src/**, salvo src/ui) solo componen componentes del kit.
// Cada regla informa fichero:línea. Una excepción justificada se marca con `// ui-ok: motivo` en la misma línea (o `{/* ui-ok: motivo */}`).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const MANTINE_FORBIDDEN = ["Badge", "Button", "Table", "SegmentedControl", "Tabs", "Modal", "NavLink", "ActionIcon", "Slider", "RangeSlider", "Progress", "Tooltip", "TextInput", "NumberInput", "PasswordInput", "Textarea", "Select", "Autocomplete", "Checkbox", "Switch", "Alert", "Card", "Paper", "CopyButton", "Drawer", "ScrollArea", "Timeline", "Popover", "UnstyledButton", "SimpleGrid"];

const RULES = [
  { id: "style", re: /\bstyle=\{\{/, msg: "estilo en línea: usa una clase del kit o un componente (Page, Stack, Group, ListCard…)" },
  { id: "nativo", re: /<(button|input|select|textarea|table|pre|form|a)\b/, msg: "elemento HTML nativo: usa Btn, TextField, DataTable, CodeBlock, SearchBar…" },
  { id: "color", re: /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:c|color|bg)="(?:red|orange|teal|yellow|blue|gray|green|violet|grape|pink|lime|cyan|indigo)"|--mantine-color/, msg: "color literal: usa un tono (Pill/Notice/Steps tone) o un token (ui/palette.ts, var(--ms-…))" },
  { id: "variant", re: /<(Btn|Pill)\b[^>]*\b(variant|color)=/, msg: "variant/color en Btn o Pill: usa kind (Btn) o tone (Pill)" },
  { id: "btn-size", re: /<Btn\b[^>]*\bsize="(?!row")/, msg: "tamaño de Btn: solo size=\"row\" en acciones de fila" },
  { id: "vh", re: /\b\d*vh\b|100dvh/, msg: "alto en vh: la página ya ocupa la ventana (Page + FillArea)" },
  { id: "texto-estado", re: /<Text\b[^>]*>\s*(Cargando|Buscando|Calculando|No hay|Aún no|Sin resultados)/, msg: "mensaje de carga o vacío suelto: usa EmptyState o DataState" },
  // La anatomía de una vista (DESIGN.md, the Screen Anatomy Rule): cada cosa tiene un solo sitio.
  { id: "subtitulo", re: /<Title\b|<Text\b[^>]*\bfw=/, msg: "subtítulo o texto en negrita propio: usa Block (o el título de ListCard, SettingsGroup o CellText)" },
  { id: "pie", re: /<Text\b[^>]*\b(?:size="xs"[^>]*\bc="dimmed"|c="dimmed"[^>]*\bsize="xs")/, msg: "texto pequeño atenuado suelto (nota al pie, línea de estado): va en la «i» de ViewBar o Block, en `meta` de ViewBar o ListCard, en `sub` de CellText o en la descripción del campo" },
  { id: "medida", re: /\bms-measure\b/, msg: "medida puesta a mano: el kit la aplica al texto corrido (ListCard, ms-prose, ayuda); el resto ocupa su ancho" },
  { id: "ancho", re: /<[A-Z][\w.]*\b[^>]*\s(?:w|maw|mah|miw|h)=[{"]/, msg: "ancho o alto fijo: el ancho lo dan ViewBar, Form, DialogActions y DataTable" },
  { id: "intro", re: /<Notice\b(?![^>]*\btone="(?:warn|danger|success)")(?![^>]*\btitle=)/, msg: "Notice informativo sin título: lo que explica una vista va en la «i» (help de ViewBar o Block); un Notice es un estado y se nombra (title)" },
  { id: "pie-dialogo", re: /justify="flex-end"/, msg: "fila de botones propia: usa DialogActions" },
  { id: "espera", re: /<EmptyState>\s*\{t\("(?:Cargando|Buscando|Calculando|Redactando|Conectando)/, msg: "EmptyState usado como carga: usa Loading o DataState" },
  { id: "panel-pt", re: /<Tabs\.Panel\b[^>]*\bpt=/, msg: "relleno de la pestaña: lo pone el kit" },
  { id: "tabintro", re: /\bTabIntro\b/, msg: "párrafo de introducción: va en la «i» de ViewBar" },
];
const UI_FORBIDDEN = ["Panel"];  // a card a screen draws itself: records go in ListCard, dashboard tiles in Section, settings in SettingsGroup

let bad = 0;
const found = [];
function walk(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) { if (f !== "ui") walk(p); continue; }
    if (!/\.tsx?$/.test(f)) continue;
    const src = readFileSync(p, "utf8");
    for (const m of src.matchAll(/import\s*\{([^}]*)\}\s*from\s*"@mantine\/core"/g)) {
      const used = m[1].split(",").map((s) => s.trim().split(/\s+as\s+/)[0]).filter((n) => MANTINE_FORBIDDEN.includes(n));
      if (used.length && !/ui-ok/.test(m[0])) { found.push(`${p}:${src.slice(0, m.index).split("\n").length}  [mantine] importa ${used.join(", ")}; usa el componente de src/ui`); bad++; }
    }
    for (const m of src.matchAll(/import\s*\{([^}]*)\}\s*from\s*"(?:\.\.?\/)+ui"/g)) {
      const used = m[1].split(",").map((s) => s.trim().split(/\s+as\s+/)[0]).filter((n) => UI_FORBIDDEN.includes(n));
      if (used.length) { found.push(`${p}:${src.slice(0, m.index).split("\n").length}  [panel] importa ${used.join(", ")}: un registro va en ListCard, una cifra en Section, un ajuste en SettingsGroup`); bad++; }
    }
    if (!f.endsWith(".tsx")) continue;
    src.split("\n").forEach((line, i) => {
      if (/ui-ok/.test(line) || src.startsWith("// ui-ok-file")) return;
      for (const r of RULES) if (r.re.test(line)) { found.push(`${p}:${i + 1}  [${r.id}] ${r.msg}`); bad++; }
    });
  }
}
walk("src");
found.forEach((l) => console.error(l));
if (bad) console.error(`\n${bad} incumplimiento(s) de las reglas de interfaz (src/ui/README.md).`);
process.exit(bad ? 1 : 0);

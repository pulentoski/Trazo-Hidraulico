# Estilo visual de Trazo Hidráulico (v2 «Planta APR»)

Sistema visual tomado de las maquetas `docs/referencias/estilo/login.html` (ingreso) y
`docs/referencias/estilo/principal.html` (inicio y estilo general). Las maquetas son solo referencia: **no se copian sus
scripts** (Tailwind por CDN, `onclick` en línea) **ni recursos de otros dominios** (Google Fonts). Fuentes e íconos
se sirven desde el propio proyecto y cumplen la CSP actual (`font-src 'self'`, `script-src 'self'`).

Todo está en tokens CSS con tema claro y oscuro (`frontend/src/styles/identity.css`; marco, inicio, ingreso y Panel
admin en `styles/frame.css`; escenas en `styles/scenes.css`). La posición de los paneles del editor no cambia:
herramientas a la izquierda, mapa al centro, propiedades a la derecha y panel inferior.

## Color

El oscuro es el de la maqueta (azul marino 950/900/850 y cian); el claro, su variante `html.light`.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--bg` / `--bg-hi` | `#eef3f9` / `#ffffff` | `#050d1a` / `#0d1d38` | Fondo de página y foco del degradado del ingreso |
| `--panel` / `--panel-2` / `--panel-3` | `#ffffff` / `#f4f8fc` / `#eaf1f9` | `#091529` / `#0d1d38` / `#0e203d` | Tarjetas, cabeceras de tabla, controles |
| `--glass` | `rgba(255,255,255,.92)` | `rgba(9,21,41,.9)` | Tarjeta del ingreso, accesos rápidos, avisos (con desenfoque) |
| `--line` / `--line-strong` | `#d3deed` / `#b4c4d8` | `#1e293b` / `#334155` | Bordes |
| `--text` / `--text-2` / `--muted` | `#0f172a` / `#334155` / `#5b6b80` | `#f1f5f9` / `#cbd5e1` / `#94a3b8` | Texto |
| `--accent` | `#0369a1` | `#22d3ee` | Enlaces, selección, ítem activo, marca «Trazo» |
| `--accent-vivid` | `#0284c7` | `#06b6d4` | Bordes de foco, íconos, decoración |
| `--btn-1` → `--btn-2` | `#0062c4` → `#0072e0` | igual | Degradado del botón principal (`.primary`, `.cta`) y del menú activo |
| `--ok` / `--warn` / `--bad` | `#047857` / `#b45309` / `#c2272d` | `#34d399` / `#fbbf24` / `#f08a8d` | Estados |
| `--info` | `#4f46e5` | `#818cf8` | Acceso «Abrir el último proyecto» |
| `--logo` / `--river` | `#0284c7` / `#0ea5e9` | `#00d2ff` / `#0ea5e9` | Logo (cordillera y río) |

El botón principal de la maqueta usa `#0077e6 → #0099ff`; aquí se oscureció a `#0062c4 → #0072e0` para que el texto
blanco cumpla AA (el cian claro `#0284c7` de la maqueta queda para decoración: como texto da 4,1:1).

**Contraste (WCAG 2.1, AA ≥ 4,5:1 para texto normal)**, sobre `--panel`:

| | Claro | Oscuro |
|---|---|---|
| Texto | 17,9 | 16,7 |
| Texto secundario (`--muted`) | 5,4 | 7,1 |
| Acento (texto/enlace) | 5,9 | 10,1 |
| Correcto / advertencia / error | 5,5 / 5,0 / 5,8 | 9,5 / 10,9 / 7,6 |
| Texto blanco sobre el degradado del botón | 5,9 → 4,7 | 5,9 → 4,7 |
| Acento sobre `--accent-soft` | 5,2 | 8,2 |

## Tipografía

- **Inter** 400/500/600/700 (texto, títulos y datos), empaquetada con Fontsource (`@fontsource/inter`).
- **IBM Plex Mono** para código e ID.
- Tamaños de la maqueta: título del inicio 2,25 rem/700, títulos de página 1,4 rem/700, de tarjeta 0,95–1,05 rem/600,
  texto 0,875–0,9 rem, rótulos 0,75 rem. Números tabulares en tablas, indicadores y coordenadas.

## Forma, espaciado y sombras

- Radios: 6 px (controles pequeños), **8 px** (botones, campos), **12 px** (accesos rápidos, menús, ítems del menú
  lateral), **16 px** (tarjetas, paneles, modales; `rounded-2xl` de la maqueta), 18 px (tarjeta del ingreso).
- Espaciado: rejilla de 4 px; tarjetas con 16–20 px de relleno, separación de 14–24 px; contenido hasta 1440 px.
- Sombras: `--shadow-sm` (reposo), `--shadow-md` (tarjetas, `shadow-lg` de la maqueta), `--shadow` (menús, modales,
  tarjeta del ingreso), `--btn-shadow` (botón principal).

## Componentes

- **Marco** (`components/AppFrame.tsx`) en inicio, Gestión, Ajustes y Panel admin: menú lateral de 240 px (plegable a
  68 px; en pantallas angostas, cajón) con la marca, Inicio, Proyectos, Importar .inp, Desde Excel, Ajustes y —según
  el rol— Organización o Panel admin; barra superior de 56 px con migas, versión, tema, campana de alertas
  (mantenciones atrasadas reales) y usuario; aviso fijo del modo soporte; pie con versión y estado del sistema
  (`/api/health`).
- **Botones**: principal en degradado azul (derecha del grupo), secundarios neutros, peligrosos en rojo (izquierda,
  siempre con confirmación; las acciones sobre organizaciones piden escribir su nombre).
- **Campos**: fondo `--field`, borde suave, radio 8, anillo cian al enfocar; contraseña con botón mostrar/ocultar.
- **Tarjetas**: radio 16, borde y sombra suave; las de proyecto con miniatura del trazado sobre cuadrícula.
- **Menús desplegables** (`components/MenuButton.tsx`): se dibujan en una capa propia sobre el mapa y los paneles y se
  reubican para no salirse de la ventana (Datos del editor, Datos de Gestión, alertas).
- **Fichas de estado** (`.status-pill`): activo, suspendida, bloqueada, versión.
- **Íconos**: un solo set, Lucide (`lucide-react`), en `components/Icons.tsx`; 18 px (16 px en botones pequeños),
  trazo 1,75. Los mismos de la maqueta (Heroicons de contorno) tienen equivalente en Lucide.

## Tablas

Componente común `components/DataTable.tsx` (lógica en `lib/table.ts`, con pruebas): búsqueda sin tildes,
orden por cualquier columna (texto A–Z con números naturales, números con orden numérico real, fechas ISO o
dd-mm-aaaa; vacíos al final), paginación (25/50/100/todas) y exportar a CSV (las filas visibles, con el orden
actual). Se usa en Nudos, Tramos, Alertas, Clientes, Consultas, Cuarteles, Mediciones, Grifos, Versiones, Resumen
(listas de elementos, clientes sobre cota, mayores consumidores, eventos de pérdidas), Gestión (tablas de detalle,
registros y vista previa de importación), Ajustes (miembros, invitaciones, sesiones, catálogo, auditoría) y Panel
admin (organizaciones, usuarios, auditoría).

## Logo

Cordillera con un río (del menú de la maqueta) en `--logo` y `--river`: grande en el menú lateral, en cuadro
redondeado en el ingreso y la barra del editor, y como `public/favicon.svg`. Marca escrita «**Trazo** Hidráulico» con
«Trazo» en el acento.

## Escenas y animaciones

- **Ingreso**: ciclo del agua en los Andes (cordillera, glaciar, lluvia, río, bocatoma, estanque, viviendas).
  **Inicio**: planta APR (pozo, cloración, estanque, macromedidor, oficina, lectores). Dibujo SVG de la maqueta en
  `components/scenes/*.ts` (sin scripts), avisos al pasar el mouse por cada elemento y nubes que se apartan del
  puntero; botón de pausa.
- Interfaz: transiciones de 120–250 ms (`--dur-fast`, `--dur`, `--dur-slow`), elevación de 1–2 px al pasar el mouse,
  aparición de menús y modales, esqueletos de carga y las animaciones del mapa que ya existían.
- Todas respetan «Animaciones» (Ajustes → Preferencias) y `prefers-reduced-motion`; los e2e las desactivan.

## Lo que la maqueta muestra sin función real (pendiente, no se inventó)

- Menú «Reportes» y «Ayuda» del menú lateral y el enlace «Soporte» del pie.
- Etiqueta «Activo» de cada proyecto (no hay estado de proyecto) y botón «Gestionar» separado de Gestión.
- Selector «Región» y «Fórmula de pérdida» en el diálogo de proyecto nuevo (la fórmula se elige en el editor).
- Indicador «Sistema operativo: en línea» como monitoreo continuo: aquí es una consulta a `/api/health` al cargar.

## Capturas

`docs/capturas/estilo-v2/`: `antes-*` (estilo anterior) y `despues-*` (estilo v2) de ingreso, inicio, editor,
Resumen, Gestión, Ajustes y Panel admin, en tema claro y oscuro, a 1440 y 1024 px. Las regenera `e2e/estilo_v2.py`
(`ESTILO_FASE=antes|despues`; `make test-e2e` produce las «después»). Los correos quedan tapados. Las del estilo
anterior siguen en `docs/capturas/estilo/`.

# Identidad visual de Trazo Hidráulico

Identidad «agua y redes»: azul petróleo como color principal, un acento cálido (naranja cobre) reservado para la
acción más importante de cada pantalla, neutros con un leve tono azulado, sombras suaves y radios consistentes.
Todo está en tokens CSS (`frontend/src/styles/identity.css`, que se carga después de `app.css`) con tema claro y
oscuro. La posición de los paneles del editor no cambia: herramientas a la izquierda, mapa al centro, propiedades a
la derecha y panel inferior.

## Color

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--accent` | `#0a6b73` | `#3fbfc1` | Color principal: botón primario, selección, enlaces, pestaña activa |
| `--accent-strong` | `#07555c` | `#6fd6d6` | Hover del primario |
| `--accent-soft` | `#dcefef` | `#0f3539` | Fondos de estado activo (herramienta, vista, filtro) |
| `--warm` | `#ad4a0c` | `#f2924a` | Acento cálido: **una** acción por pantalla (Simular, Nuevo proyecto) |
| `--bg` | `#edf3f4` | `#0b1519` | Fondo de página |
| `--panel` / `--panel-2` | `#ffffff` / `#f3f8f8` | `#11202a` / `#162a33` | Superficies |
| `--line` / `--line-strong` | `#d5e1e4` / `#b2c5ca` | `#233a45` / `#35525e` | Bordes |
| `--text` / `--muted` | `#10252c` / `#4f6871` | `#dceaee` / `#90a9b2` | Texto |
| `--ok` / `--warn` / `--bad` | `#2b7a4b` / `#9a5a00` / `#bd3328` | `#5cc28a` / `#f0a838` / `#f06a5f` | Estados |

Sobre el primario y el acento el texto usa `--on-accent` / `--on-warm` (blanco en claro, casi negro en oscuro).

**Contraste (WCAG 2.1, AA ≥ 4,5:1 para texto normal)**, sobre `--panel`:

| | Claro | Oscuro |
|---|---|---|
| Texto | 15,9 | 13,5 |
| Texto secundario | 5,9 | 6,7 |
| Principal (texto/enlace) | 6,2 | 7,5 |
| Acento cálido | 5,0 | 7,1 |
| Correcto / advertencia / error | 5,3 / 5,5 / 5,7 | 7,6 / 8,2 / 5,5 |
| Texto sobre botón primario | 6,2 | 8,2 |
| Texto sobre botón cálido | 5,0 | 8,0 |

## Tipografía

- **Títulos**: [Sora](https://fonts.google.com/specimen/Sora) (Google Fonts) 500/600/700, con respaldo IBM Plex
  Sans y la fuente del sistema. Se empaqueta localmente con Fontsource (`@fontsource/sora`): no depende de la red
  ni de servicios externos en tiempo de ejecución.
- **Texto y datos**: IBM Plex Sans; los números de tablas, indicadores, coordenadas y estado usan cifras tabulares
  (`font-variant-numeric: tabular-nums`) para alinearse en columna.
- **Código e ID**: IBM Plex Mono.

## Íconos

Un solo set: **Lucide** (`lucide-react` 1.63.0), centralizado en `frontend/src/components/Icons.tsx` como
`<Icon.nombre />`. Mismo tamaño (`--icon`: 18 px; 16 px en botones pequeños y menús) y mismo grosor de trazo
(1,75). Cada botón lleva ícono y texto; si el ancho obliga a mostrar solo el ícono, el botón tiene `title` y
`aria-label`.

## Logo

Una gota con una red de tres nudos (el último, en el acento cálido) sobre un cuadrado redondeado en el color
principal (`Logo` en `components/PageHeader.tsx`; también `public/favicon.svg`). Aparece en el inicio, en el ingreso
y en la barra superior del editor. La marca escrita es «**Trazo** Hidráulico», con «Trazo» en el color principal.

## Forma

- Radios: 6 px (controles pequeños), 8 px (botones, campos), 12 px (tarjetas), 16 px (modales, tarjeta de ingreso).
- Sombras: `--shadow-sm` (reposo de tarjetas), `--shadow-md` (hover), `--shadow` (menús, modales, avisos).
- Fondo de identidad: curvas de nivel y una red de cañerías (`components/NetPattern.tsx`) en el encabezado del
  inicio y en el ingreso, con un movimiento muy lento que se detiene con «Animaciones» desactivado o
  `prefers-reduced-motion`.

## Botones y jerarquía

- **Principal** (`.primary`): color principal, a la **derecha** del grupo de acciones.
- **Destacada** (`.cta`): acento cálido, solo una por pantalla (Simular en el editor, Nuevo proyecto en el inicio).
- **Secundarias**: estilo neutro, a la izquierda de la principal.
- **Peligrosas** (`.danger`, `.danger-outline`, `.danger-text`): en rojo, en el extremo izquierdo, y siempre con
  confirmación (eliminar proyecto, filas de registros, mediciones o fugas, desactivar o suspender cuentas,
  desactivar el segundo factor, cerrar todas las sesiones, borrar la key del mapa).

## Orden de las botoneras del editor

**Barra superior** (izquierda → derecha, grupos separados):

1. Navegación: Menú, logo, nombre del proyecto
2. Archivo: Guardar (Ctrl+S), Historial, Deshacer (Ctrl+Z), Rehacer (Ctrl+Y)
3. Vistas: Editor, Resumen, Gestión
4. Análisis: Simular (F5), estado del cálculo
5. Datos: menú Importar / Exportar (.inp, .trazo, planilla, SIG/CAD e informe)
6. Usuario (a la derecha): tema y menú de usuario

**Herramientas** (agrupadas, con título y atajo visible):

| Grupo | Herramientas (tecla) |
|---|---|
| Selección | Seleccionar (V), Selección múltiple (B), Mover (M) |
| Red | Nudo (N), Tubería (T), Estanque (E), Reservorio (R), Pozo (W), Válvula de corte (L), Grifo (G) |
| Clientes | Cliente (C) |
| Análisis | Factibilidad (F), Medir (D) |
| Edición | Eliminar (X) |

**Panel inferior** (orden de uso): Resumen, Alertas, Nudos, Tramos, Clientes, Simulación, Gráficos, Diagnóstico,
Escenarios, Cuarteles, Demanda, Mediciones, Consultas, Capas (y al final Grifos y Corrida). Las que no caben pasan
al menú «Más».

## Animaciones

Sobrias, entre 120 y 250 ms (`--dur-fast` 120 ms, `--dur` 180 ms, `--dur-slow` 250 ms):

- Botones y tarjetas: elevación (1–2 px) y cambio de color suave al pasar el mouse; pulsación breve al hacer clic.
- Menús, modales y avisos: aparición con desvanecimiento y escala corta; los avisos entran desde la derecha.
- Carga: esqueletos animados (`components/Skeleton.tsx`) en el inicio, el editor, Gestión y Ajustes.
- Mapa: aparición breve de cada elemento creado (anillo que crece), trazo animado de la tubería recién dibujada,
  resaltado con pulsos al seleccionar o «ir al elemento», y el flujo, los pulsos de alerta y la transición de
  horas que ya existían.
- Íconos: microanimación al activar una herramienta.

Todas respetan el interruptor «Animaciones» (Ajustes → Preferencias) y `prefers-reduced-motion`; los e2e las
desactivan.

## Capturas

`docs/capturas/estilo/`: `antes-*` (estilo anterior) y `despues-*` (esta identidad) de inicio, editor, Gestión,
Ajustes → Mapa base e ingreso, en tema claro y oscuro, a 1440 y 1024 px. Las regenera `e2e/estilo.py`
(`ESTILO_FASE=antes|despues`; `make test-e2e` produce las «después»). Los correos quedan tapados.

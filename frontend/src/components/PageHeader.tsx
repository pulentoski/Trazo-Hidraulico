// Marca de Trazo Hidráulico (estilo v2, docs/referencias/estilo/): cordillera con un río, en el color de marca del
// tema (cian en oscuro, azul en claro). Se usa en el menú lateral, el ingreso y la barra superior del editor.

/** Logo: cordillera y río sobre un cuadrado redondeado con el acento suave. */
export function Logo({ size = 28, plain = false }: { size?: number; plain?: boolean }) {
  const art = (
    <svg viewBox="0 0 120 70" width={plain ? size * 1.7 : size * 0.62} height={plain ? size : size * 0.62} fill="none" aria-hidden="true" focusable="false">
      <path className="logo-ridge" d="M12 56L46 16L66 40L82 24L108 56" strokeWidth={plain ? 3.5 : 7} strokeLinecap="round" strokeLinejoin="round" />
      <path className="logo-snow" d="M35 29L46 16L56 28L49 32L43 26Z" />
      {plain && <path className="logo-snow" d="M74 32L82 24L90 33L83 36L74 32Z" />}
      <path className="logo-river" d="M24 52C42 42 58 58 76 46C88 38 98 46 106 52" strokeWidth={plain ? 2.5 : 5} strokeLinecap="round" />
      {plain && <><circle className="logo-node" cx="46" cy="48" r="2.5" /><circle className="logo-node" cx="76" cy="46" r="2.5" /></>}
    </svg>
  );
  if (plain) return <span className="logo plain">{art}</span>;
  return <span className="logo mark" style={{ width: size, height: size }}>{art}</span>;
}

export function Brand({ big = false }: { big?: boolean }) {
  return (
    <div className={`brand ${big ? "big" : ""}`} title="Trazo Hidráulico — diseño, simulación y gestión de redes de agua potable">
      <Logo size={big ? 44 : 28} />
      <span className="brand-name"><b>Trazo</b> Hidráulico</span>
    </div>
  );
}

// Fondo de identidad: curvas de nivel y una red de cañerías, con un movimiento muy lento (se detiene con
// «Animaciones» desactivado o prefers-reduced-motion). Decorativo: oculto para lectores de pantalla.
const CONTOURS = [
  "M-40 260 C 120 200, 220 300, 380 240 S 640 150, 820 210 S 1100 300, 1280 230",
  "M-40 300 C 140 240, 240 340, 400 280 S 660 190, 840 250 S 1120 340, 1280 270",
  "M-40 340 C 160 280, 260 380, 420 320 S 680 230, 860 290 S 1140 380, 1280 310",
  "M-40 120 C 100 80, 260 150, 420 110 S 700 40, 880 90 S 1160 160, 1280 100",
  "M-40 160 C 110 120, 270 190, 430 150 S 710 80, 890 130 S 1170 200, 1280 140",
  "M-40 400 C 180 330, 300 420, 460 370 S 720 290, 900 340 S 1160 430, 1280 360",
];
const NODES: [number, number][] = [[90, 300], [260, 210], [430, 260], [600, 150], [760, 230], [930, 120], [1100, 200],
  [430, 370], [760, 340], [260, 90]];
const PIPES: [number, number][] = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [2, 7], [4, 8], [1, 9], [7, 8]];

export function NetPattern({ className = "" }: { className?: string }) {
  return (
    <svg className={`net-pattern ${className}`} viewBox="0 0 1240 440" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <g className="np-contours">{CONTOURS.map((d, i) => <path key={i} d={d} />)}</g>
      <g className="np-pipes">
        {PIPES.map(([a, b], i) => <line key={i} x1={NODES[a][0]} y1={NODES[a][1]} x2={NODES[b][0]} y2={NODES[b][1]} />)}
      </g>
      <g className="np-flow">
        {PIPES.map(([a, b], i) => <line key={i} x1={NODES[a][0]} y1={NODES[a][1]} x2={NODES[b][0]} y2={NODES[b][1]} />)}
      </g>
      <g className="np-nodes">{NODES.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 5 ? 7 : 5} className={i === 5 ? "warm" : ""} />)}</g>
    </svg>
  );
}

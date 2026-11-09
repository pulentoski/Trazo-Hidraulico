// Capa SVG de la red: dibujo, selección y edición con todas las herramientas.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CatalogPipe } from "../api/types";
import { classify, linkScale, linkValue as valueOf, pressureScale } from "../lib/colors";
import { fmt, fmtLen } from "../lib/format";
import type { Camera, LngLat, Size } from "../lib/geo";
import { distToSegment, haversine, panBy, project, unproject, zoomAt } from "../lib/geo";
import type { ELink, ENode, Network } from "../lib/network";
import { defaultNodeProps, defaultPipeProps, linkCoords, nextId, roughnessFor, uid } from "../lib/network";
import { criteriaOf, useEditor } from "../state/store";

type Pt = [number, number];
type Gesture =
  | { kind: "none" }
  | { kind: "press"; start: Pt; target: Target; shift: boolean; button: number }
  | { kind: "pan"; last: Pt }
  | { kind: "box"; start: Pt; now: Pt; additive: boolean }
  | { kind: "dragNode"; uid: string }
  | { kind: "dragVertex"; link: string; idx: number };
type Target = { type: "node" | "link"; uid: string } | { type: "vertex"; link: string; idx: number } | { type: "bg" };

const CLICK_TOLERANCE = 4;
const SNAP_PX = 12;

export function defaultCatalogItem(catalog: CatalogPipe[]): CatalogPipe | undefined {
  return catalog.find((c) => c.material === "PVC" && c.pipe_class === "C10" && c.dn === 110) ?? catalog[0];
}

function readTarget(el: EventTarget | null): Target {
  const node = (el as Element | null)?.closest?.("[data-t]") as SVGElement | null;
  if (!node) return { type: "bg" };
  const t = node.dataset.t;
  if (t === "vertex") return { type: "vertex", link: node.dataset.link!, idx: Number(node.dataset.idx) };
  if (t === "node" || t === "link") return { type: t, uid: node.dataset.uid! };
  return { type: "bg" };
}

function midpointAngle(pts: Pt[]): { p: Pt; angle: number; length: number } {
  let total = 0;
  const seg: number[] = [];
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    seg.push(d);
    total += d;
  }
  let acc = 0;
  for (let i = 0; i < seg.length; i++) {
    if (acc + seg[i] >= total / 2 && seg[i] > 0) {
      const t = (total / 2 - acc) / seg[i];
      const a = pts[i];
      const b = pts[i + 1];
      return { p: [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])], angle: Math.atan2(b[1] - a[1], b[0] - a[0]), length: total };
    }
    acc += seg[i];
  }
  return { p: pts[0], angle: 0, length: 0 };
}

interface Props { camera: Camera; size: Size; setCamera: (c: Camera) => void }

export function NetworkLayer({ camera, size, setCamera }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const s = useEditor();
  const { net, tool, selection, result, period, linkMode, labels, profiles, project } = s;
  const [gesture, setGesture] = useState<Gesture>({ kind: "none" });
  const [cursor, setCursor] = useState<Pt | null>(null);
  const [draft, setDraft] = useState<{ from: string; vertices: LngLat[] } | null>(null);
  const [measure, setMeasure] = useState<LngLat[]>([]);
  const gestureRef = useRef(gesture);
  gestureRef.current = gesture;

  const profile = profiles.find((p) => p.id === project?.design_profile_id);
  const criteria = criteriaOf(profile);
  const proj = useCallback((p: LngLat): Pt => project_(p, camera, size), [camera, size]);
  const selected = useMemo(() => new Set(selection), [selection]);

  // Resultados del periodo actual, por ID EPANET.
  const nodeRes = result?.nodes;
  const linkRes = result?.links;
  const linkValue = useCallback((l: ELink): number | null => valueOf(linkMode, l, linkRes?.[l.id], period),
    [linkMode, linkRes, period]);

  const lscale = useMemo(() => {
    const vals = Object.values(net.links).map(linkValue).filter((v): v is number => v !== null);
    return linkScale(linkMode, criteria, vals);
  }, [net.links, linkValue, linkMode, criteria]);
  const pscale = useMemo(() => pressureScale(criteria), [criteria]);

  // Cancela borradores al cambiar de herramienta.
  useEffect(() => {
    setDraft(null);
    setMeasure([]);
  }, [tool]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setDraft(null);
        setMeasure([]);
        setGesture({ kind: "none" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const local = (e: { clientX: number; clientY: number }): Pt => {
    const r = svgRef.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };

  const nearestNode = (p: Pt, exclude?: string): ENode | null => {
    let best: ENode | null = null;
    let bd = SNAP_PX;
    for (const n of Object.values(net.nodes)) {
      if (n.uid === exclude) continue;
      const q = proj(n.pos);
      const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
      if (d < bd) {
        bd = d;
        best = n;
      }
    }
    return best;
  };

  // ── Acciones de edición ──
  const addNode = (kind: ENode["kind"], pos: LngLat): string => {
    const st = useEditor.getState();
    const id = nextId(Object.values(st.net.nodes).map((n) => n.id), kind);
    const node: ENode = { uid: uid(), id, kind, pos, props: defaultNodeProps(kind) };
    st.commit((n) => ({ ...n, nodes: { ...n.nodes, [node.uid]: node } }));
    return node.uid;
  };

  const addPipe = (from: string, to: string, vertices: LngLat[]) => {
    const st = useEditor.getState();
    const item = defaultCatalogItem(st.catalog);
    const id = nextId(Object.values(st.net.links).map((l) => l.id), "pipe");
    const link: ELink = {
      uid: uid(), id, kind: "pipe", from, to, vertices,
      props: defaultPipeProps(item ? {
        material: item.material, pipe_class: item.pipe_class, dn: item.dn, catalog_pipe_id: item.id,
        inner_diameter_mm: item.inner_diameter_mm, roughness: roughnessFor(st.options.headloss, item),
      } : { inner_diameter_mm: 100, roughness: 140 }),
    };
    st.commit((n) => ({ ...n, links: { ...n.links, [link.uid]: link } }));
    st.select([link.uid]);
  };

  const clickAction = (p: Pt, target: Target, shift: boolean, dbl = false) => {
    const st = useEditor.getState();
    const pos = unproject(p, camera, size);
    switch (tool) {
      case "select":
      case "move":
        if (target.type === "node" || target.type === "link") st.select([target.uid], shift);
        else if (target.type === "bg" && !shift) st.select([]);
        return;
      case "multiselect":
        if (target.type === "node" || target.type === "link") st.select([target.uid], true);
        return;
      case "delete":
        if (target.type === "node" || target.type === "link") st.requestDelete([target.uid]);
        return;
      case "junction":
      case "tank":
      case "reservoir":
        if (target.type === "node") st.select([target.uid]);
        else st.select([addNode(tool, pos)]);
        return;
      case "measure":
        setMeasure((m) => (dbl ? m : [...m, pos]));
        return;
      case "pipe": {
        const snap = target.type === "node" ? target.uid : nearestNode(p, draft?.from)?.uid ?? null;
        if (!draft) {
          setDraft({ from: snap ?? addNode("junction", pos), vertices: [] });
          return;
        }
        if (snap && snap !== draft.from) {
          addPipe(draft.from, snap, draft.vertices);
          setDraft({ from: snap, vertices: [] }); // encadenado estilo CAD; Esc o clic derecho termina
          return;
        }
        if (dbl) {
          // El doble clic termina el tramo en un nudo nuevo ubicado en el último vértice.
          const verts = [...draft.vertices];
          const end = verts.pop() ?? pos;
          const endPx = proj(end);
          while (verts.length) {
            const last = proj(verts[verts.length - 1]);
            if (Math.hypot(last[0] - endPx[0], last[1] - endPx[1]) > 3) break;
            verts.pop();
          }
          if (verts.length === 0 && haversine(useEditor.getState().net.nodes[draft.from]?.pos ?? end, end) < 0.01) return;
          const to = addNode("junction", end);
          addPipe(draft.from, to, verts);
          setDraft(null);
          return;
        }
        setDraft({ ...draft, vertices: [...draft.vertices, pos] });
        return;
      }
    }
  };

  // ── Eventos de puntero ──
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button === 2) return;
    svgRef.current?.setPointerCapture(e.pointerId);
    const p = local(e);
    const target = readTarget(e.target);
    if (e.button === 1) {
      setGesture({ kind: "pan", last: p });
      return;
    }
    if (tool === "move" && target.type === "node") {
      useEditor.getState().beginDrag();
      setGesture({ kind: "dragNode", uid: target.uid });
      return;
    }
    if ((tool === "move" || tool === "select") && target.type === "vertex") {
      useEditor.getState().beginDrag();
      setGesture({ kind: "dragVertex", link: target.link, idx: target.idx });
      return;
    }
    setGesture({ kind: "press", start: p, target, shift: e.shiftKey || e.ctrlKey || e.metaKey, button: e.button });
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const p = local(e);
    setCursor(p);
    const g = gestureRef.current;
    const st = useEditor.getState();
    if (g.kind === "press") {
      if (Math.hypot(p[0] - g.start[0], p[1] - g.start[1]) < CLICK_TOLERANCE) return;
      if (tool === "multiselect" || (tool === "select" && g.shift)) setGesture({ kind: "box", start: g.start, now: p, additive: g.shift });
      else setGesture({ kind: "pan", last: g.start });
      return;
    }
    if (g.kind === "pan") {
      setCamera(panBy(camera, p[0] - g.last[0], p[1] - g.last[1]));
      setGesture({ kind: "pan", last: p });
    } else if (g.kind === "box") {
      setGesture({ ...g, now: p });
    } else if (g.kind === "dragNode") {
      const pos = unproject(p, camera, size);
      st.dragTo((n) => ({ ...n, nodes: { ...n.nodes, [g.uid]: { ...n.nodes[g.uid], pos } } }));
    } else if (g.kind === "dragVertex") {
      const pos = unproject(p, camera, size);
      st.dragTo((n) => {
        const l = n.links[g.link];
        const vertices = l.vertices.map((v, i) => (i === g.idx ? pos : v));
        return { ...n, links: { ...n.links, [g.link]: { ...l, vertices } } };
      });
    }
  };

  const onPointerUp = (e: React.PointerEvent) => {
    const g = gestureRef.current;
    const p = local(e);
    const st = useEditor.getState();
    if (g.kind === "press") clickAction(p, g.target, g.shift);
    else if (g.kind === "box") {
      const [x0, x1] = [Math.min(g.start[0], g.now[0]), Math.max(g.start[0], g.now[0])];
      const [y0, y1] = [Math.min(g.start[1], g.now[1]), Math.max(g.start[1], g.now[1])];
      const inside = (q: Pt) => q[0] >= x0 && q[0] <= x1 && q[1] >= y0 && q[1] <= y1;
      const hits: string[] = Object.values(net.nodes).filter((n) => inside(proj(n.pos))).map((n) => n.uid);
      for (const l of Object.values(net.links)) if (linkCoords(net, l).every((c) => inside(proj(c)))) hits.push(l.uid);
      st.select(hits, g.additive);
    } else if (g.kind === "dragNode" || g.kind === "dragVertex") {
      st.endDrag();
    }
    setGesture({ kind: "none" });
  };

  const onDoubleClick = (e: React.MouseEvent) => {
    const p = local(e);
    if (tool === "pipe") clickAction(p, readTarget(e.target), false, true);
    else if (tool === "measure") setMeasure([]);
  };

  const onWheel = (e: React.WheelEvent) => {
    setCamera(zoomAt(camera, size, local(e), e.deltaY < 0 ? 1 : -1));
  };

  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setDraft(null);
    setMeasure([]);
  };

  // ── Render ──
  const zoomScale = Math.max(0.6, Math.min(1.4, (camera.zoom - 12) / 5 + 0.8));
  const linkEls: React.ReactNode[] = [];
  const arrowEls: React.ReactNode[] = [];
  const labelEls: React.ReactNode[] = [];
  const handleEls: React.ReactNode[] = [];

  for (const l of Object.values(net.links)) {
    const coords = linkCoords(net, l);
    if (coords.some((c) => !c)) continue;
    const pts = coords.map(proj);
    const pstr = pts.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" ");
    const v = linkValue(l);
    const color = v === null ? "var(--link-neutral)" : lscale.colors[classify(v, lscale.breaks)];
    const d = l.props.inner_diameter_mm ?? 100;
    const width = (1.6 + Math.min(4.5, Math.sqrt(d / 50))) * zoomScale;
    const isSel = selected.has(l.uid);
    linkEls.push(
      <g key={l.uid}>
        {isSel && <polyline points={pstr} className="link-sel" strokeWidth={width + 7} />}
        <polyline points={pstr} className={`link link-${l.kind}`} stroke={color} strokeWidth={width} />
        <polyline points={pstr} className="hit" data-t="link" data-uid={l.uid} />
      </g>,
    );
    const mid = midpointAngle(pts);
    if (l.kind !== "pipe" && mid.length > 0) {
      const deg = (mid.angle * 180) / Math.PI;
      linkEls.push(
        <g key={`${l.uid}-sym`} transform={`translate(${mid.p[0]},${mid.p[1]}) rotate(${deg})`} className="link-symbol" data-t="link" data-uid={l.uid}>
          {l.kind === "pump" ? (<><circle r={7} /><path d="M -3 -4 L 4 0 L -3 4 Z" /></>) : (<path d="M -7 -5 L 7 5 L 7 -5 L -7 5 Z" />)}
        </g>,
      );
    }
    const q = linkRes?.[l.id]?.flow[period];
    if (q !== undefined && Math.abs(q) > 1e-6 && mid.length > 28) {
      const deg = (mid.angle * 180) / Math.PI + (q < 0 ? 180 : 0);
      arrowEls.push(
        <path key={`${l.uid}-arrow`} className="flow-arrow" transform={`translate(${mid.p[0]},${mid.p[1]}) rotate(${deg})`}
          d={`M ${-4 * zoomScale} ${-4 * zoomScale} L ${5 * zoomScale} 0 L ${-4 * zoomScale} ${4 * zoomScale} Z`} />,
      );
    }
    const texts: string[] = [];
    const r = linkRes?.[l.id];
    if (labels.linkIds) texts.push(l.id);
    if (labels.dn && l.props.dn) texts.push(`DN ${l.props.dn}`);
    if (r && labels.flow) texts.push(`${fmt(r.flow[period], 2)} L/s`);
    if (r && labels.velocity) texts.push(`${fmt(Math.abs(r.velocity[period]), 2)} m/s`);
    if (r && labels.headloss && l.kind === "pipe") texts.push(`${fmt(Math.abs(r.headloss[period]), 2)} m/km`);
    if (texts.length && mid.length > 40) {
      labelEls.push(
        <text key={`${l.uid}-lbl`} x={mid.p[0]} y={mid.p[1] - 8} className="lbl lbl-link" textAnchor="middle">{texts.join(" · ")}</text>,
      );
    }
    if (isSel && (tool === "select" || tool === "move")) {
      l.vertices.forEach((vtx, i) => {
        const vp = proj(vtx);
        handleEls.push(<rect key={`${l.uid}-v${i}`} x={vp[0] - 4} y={vp[1] - 4} width={8} height={8} className="vertex" data-t="vertex" data-link={l.uid} data-idx={i} />);
      });
    }
  }

  const nodeEls: React.ReactNode[] = [];
  for (const n of Object.values(net.nodes)) {
    const [x, y] = proj(n.pos);
    if (x < -50 || y < -50 || x > size.width + 50 || y > size.height + 50) continue;
    const pr = nodeRes?.[n.id]?.pressure[period];
    const fill = n.kind === "junction" && pr !== undefined ? pscale.colors[classify(pr, pscale.breaks)] : "var(--node-fill)";
    const isSel = selected.has(n.uid);
    const r = 4.5 * zoomScale;
    nodeEls.push(
      <g key={n.uid} transform={`translate(${x},${y})`} className={`node node-${n.kind}${isSel ? " sel" : ""}`} data-t="node" data-uid={n.uid}>
        {isSel && <circle r={r + 6} className="node-sel" />}
        {n.kind === "junction" && <circle r={r} fill={fill} />}
        {n.kind === "reservoir" && <path d={`M ${-9 * zoomScale} ${-6 * zoomScale} L ${9 * zoomScale} ${-6 * zoomScale} L ${6 * zoomScale} ${6 * zoomScale} L ${-6 * zoomScale} ${6 * zoomScale} Z`} />}
        {n.kind === "tank" && <rect x={-7 * zoomScale} y={-8 * zoomScale} width={14 * zoomScale} height={16 * zoomScale} rx={2} />}
        <circle r={Math.max(9, r + 4)} className="hit-node" />
      </g>,
    );
    const texts: string[] = [];
    if (labels.nodeIds) texts.push(n.id);
    if (labels.pressure && pr !== undefined) texts.push(`${fmt(pr, 1)} m`);
    if (texts.length) labelEls.push(<text key={`${n.uid}-lbl`} x={x + 9} y={y - 7} className="lbl">{texts.join(" · ")}</text>);
  }

  // Borrador de tubería
  let draftEl: React.ReactNode = null;
  if (draft && net.nodes[draft.from]) {
    const pts = [net.nodes[draft.from].pos, ...draft.vertices].map(proj);
    let end = cursor;
    if (cursor) {
      const snap = nearestNode(cursor, draft.from);
      if (snap) end = proj(snap.pos);
    }
    const all = end ? [...pts, end] : pts;
    draftEl = <polyline points={all.map((q) => q.join(",")).join(" ")} className="draft" />;
  }

  // Medición
  let measureEl: React.ReactNode = null;
  if (tool === "measure" && measure.length) {
    const live = cursor ? [...measure, unproject(cursor, camera, size)] : measure;
    const pts = live.map(proj);
    let acc = 0;
    const tags = live.map((p, i) => {
      if (i > 0) acc += haversine(live[i - 1], p);
      return i > 0 ? <text key={i} x={pts[i][0] + 8} y={pts[i][1] + 14} className="lbl lbl-measure">{fmtLen(acc)}</text> : null;
    });
    measureEl = (
      <g>
        <polyline points={pts.map((q) => q.join(",")).join(" ")} className="measure" />
        {pts.map((q, i) => <circle key={i} cx={q[0]} cy={q[1]} r={3} className="measure-pt" />)}
        {tags}
      </g>
    );
  }

  const box = gesture.kind === "box" ? gesture : null;
  const cursorClass = gesture.kind === "pan" ? "grabbing" : `tool-${tool}`;

  return (
    <svg ref={svgRef} className={`net-layer ${cursorClass}`} width={size.width} height={size.height}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
      onPointerLeave={() => setCursor(null)} onDoubleClick={onDoubleClick} onWheel={onWheel} onContextMenu={onContextMenu}>
      <g>{linkEls}</g>
      <g>{arrowEls}</g>
      <g>{nodeEls}</g>
      <g>{handleEls}</g>
      <g className="labels">{labelEls}</g>
      {draftEl}
      {measureEl}
      {box && (
        <rect className="box" x={Math.min(box.start[0], box.now[0])} y={Math.min(box.start[1], box.now[1])}
          width={Math.abs(box.now[0] - box.start[0])} height={Math.abs(box.now[1] - box.start[1])} />
      )}
    </svg>
  );
}

function project_(p: LngLat, cam: Camera, size: Size): Pt {
  return project(p, cam, size);
}

export function distanceToLinkPx(net: Network, l: ELink, p: Pt, cam: Camera, size: Size): number {
  const pts = linkCoords(net, l).map((c) => project(c, cam, size));
  let best = Infinity;
  for (let i = 1; i < pts.length; i++) best = Math.min(best, distToSegment(p, pts[i - 1], pts[i]));
  return best;
}

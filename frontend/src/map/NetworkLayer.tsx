// Capa SVG de la red: dibujo, selección y edición con todas las herramientas.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CatalogPipe } from "../api/types";
import { classify, linkScale, linkValue as valueOf, pressureScale } from "../lib/colors";
import { fmt, fmtLen } from "../lib/format";
import type { Camera, LngLat, Size } from "../lib/geo";
import { distToSegment, haversine, panBy, project, unproject, zoomAt } from "../lib/geo";
import type { EHydrant, ELink, ENode, EWell, Network } from "../lib/network";
import { defaultNodeProps, defaultPipeProps, estimatedLength, linkCoords, nearestPipe, nextId, pointAlong, projectOnLink,
  roughnessFor, uid } from "../lib/network";
import type { LabelItem } from "../lib/labels";
import { placeLabels } from "../lib/labels";
import { criteriaOf, useEditor } from "../state/store";

type Pt = [number, number];
type Gesture =
  | { kind: "none" }
  | { kind: "press"; start: Pt; target: Target; shift: boolean; button: number }
  | { kind: "pan"; last: Pt }
  | { kind: "box"; start: Pt; now: Pt; additive: boolean }
  | { kind: "dragNode"; uid: string }
  | { kind: "dragVertex"; link: string; idx: number };
type ElType = "node" | "link" | "client" | "shutoff" | "hydrant" | "well";
type Target = { type: ElType; uid: string } | { type: "vertex"; link: string; idx: number } | { type: "bg" };
const EL_TYPES: string[] = ["node", "link", "client", "shutoff", "hydrant", "well"];
const isEl = (t: Target): t is { type: ElType; uid: string } => EL_TYPES.includes(t.type);
const PICK_PIPE_PX = 16;

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
  if (t && EL_TYPES.includes(t)) return { type: t as ElType, uid: node.dataset.uid! };
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

interface Props {
  camera: Camera;
  size: Size;
  setCamera: (c: Camera) => void;
  /** El fondo deja pasar rueda y arrastre al mapa base (solo los elementos de la red reciben el puntero). */
  passThrough?: boolean;
}

const FLASH_MS = 1800;

export function NetworkLayer({ camera, size, setCamera, passThrough = false }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const s = useEditor();
  const { net, tool, selection, result, period, linkMode, labels, profiles, project, designParams: s_designParams, scenarioView } = s;
  const [gesture, setGesture] = useState<Gesture>({ kind: "none" });
  const [cursor, setCursor] = useState<Pt | null>(null);
  const [draft, setDraft] = useState<{ from: string; vertices: LngLat[] } | null>(null);
  const [measure, setMeasure] = useState<LngLat[]>([]);
  const [hoverUid, setHoverUid] = useState<string | null>(null);
  const gestureRef = useRef(gesture);
  gestureRef.current = gesture;

  const profile = profiles.find((p) => p.id === project?.design_profile_id);
  const criteria = criteriaOf(profile, s_designParams);
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

  // Mayús sostenida (selección por caja) vuelve a capturar el fondo aunque el mapa reciba los gestos.
  const [shiftDown, setShiftDown] = useState(false);
  useEffect(() => {
    const on = (e: KeyboardEvent) => setShiftDown(e.shiftKey);
    const off = () => setShiftDown(false);
    window.addEventListener("keydown", on);
    window.addEventListener("keyup", on);
    window.addEventListener("blur", off);
    return () => { window.removeEventListener("keydown", on); window.removeEventListener("keyup", on); window.removeEventListener("blur", off); };
  }, []);

  // Resaltado breve tras «ir al elemento».
  const flash = s.flash;
  const [flashOn, setFlashOn] = useState<number | null>(null);
  useEffect(() => {
    if (!flash) return;
    setFlashOn(flash.nonce);
    const t = window.setTimeout(() => setFlashOn(null), FLASH_MS);
    return () => window.clearTimeout(t);
  }, [flash]);

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

  /** Tubería bajo el puntero (proyección), si está a menos de PICK_PIPE_PX píxeles. */
  const pipeAt = (p: Pt) => {
    const st = useEditor.getState();
    const pr = nearestPipe(st.net, unproject(p, camera, size));
    if (!pr) return null;
    const q = proj(pr.point);
    return Math.hypot(q[0] - p[0], q[1] - p[1]) <= PICK_PIPE_PX ? pr : null;
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

  const nearestOf = (pos: LngLat, kinds: ENode["kind"][], maxM = Infinity): ENode | null => {
    let best: ENode | null = null;
    let bd = maxM;
    for (const n of Object.values(useEditor.getState().net.nodes)) {
      if (!kinds.includes(n.kind)) continue;
      const d = haversine(n.pos, pos);
      if (d < bd) { bd = d; best = n; }
    }
    return best;
  };

  const clickAction = (p: Pt, target: Target, shift: boolean, dbl = false) => {
    const st = useEditor.getState();
    const pos = unproject(p, camera, size);
    if (st.mapPick) {
      st.mapPick(pos);
      st.set({ mapPick: null });
      return;
    }
    switch (tool) {
      case "select":
      case "move":
        if (isEl(target)) {
          st.select([target.uid], shift);
          if (target.type === "link" && st.sectors) {
            const l = st.net.links[target.uid];
            const frac = l ? projectOnLink(st.net, l.uid, pos).fraction : 0;
            const hit = st.sectors.sectors.find((sec) => sec.pieces.some((pc) => pc.link === l?.id && frac >= pc.start - 1e-9 && frac <= pc.end + 1e-9));
            if (hit) st.set({ sectorFocus: hit.id, bottomTab: "sectors" });
          }
        } else if (target.type === "bg" && !shift) st.select([]);
        return;
      case "multiselect":
        if (isEl(target)) st.select([target.uid], true);
        return;
      case "delete":
        if (isEl(target)) st.requestDelete([target.uid]);
        return;
      case "hydrant": {
        if (target.type === "hydrant") { st.select([target.uid]); return; }
        const n = nearestOf(pos, ["junction"]);
        if (!n) { st.toast("El grifo se conecta a un nudo de consumo: dibuje primero la red.", "error"); return; }
        const h: EHydrant = { uid: uid(), id: nextId(Object.values(st.net.hydrants).map((x) => x.id), "hydrant"), pos, node: n.uid,
          props: { description: null, hydrant_type: "columna", condition: null, diameter_mm: 100, fire_flow_lps: 16, min_pressure_m: 5, attributes: {} } };
        st.commit((net) => ({ ...net, hydrants: { ...net.hydrants, [h.uid]: h } }));
        st.select([h.uid]);
        return;
      }
      case "well": {
        if (target.type === "well") { st.select([target.uid]); return; }
        const n = nearestOf(pos, ["reservoir"], 50);
        const w: EWell = { uid: uid(), id: nextId(Object.values(st.net.wells).map((x) => x.id), "well"), pos, node: n?.uid ?? null,
          props: { description: null, condition: null, ground_elevation: null, depth_m: null, static_level_m: null, dynamic_level_m: null,
            authorized_flow_lps: null, attributes: {} } };
        st.commit((net) => ({ ...net, wells: { ...net.wells, [w.uid]: w } }));
        st.select([w.uid]);
        return;
      }
      case "client":
        if (target.type === "client") st.select([target.uid]);
        else if (!Object.values(st.net.links).some((l) => l.kind === "pipe")) st.toast("Dibuje primero una tubería para conectar clientes.", "error");
        else st.set({ clientDraft: { pos } });
        return;
      case "shutoff": {
        if (target.type === "shutoff") { st.select([target.uid]); return; }
        const pr = pipeAt(p);
        if (!pr) { st.toast("Haga clic sobre una tubería para ubicar la llave.", "error"); return; }
        const sh = { uid: uid(), id: nextId(Object.values(st.net.shutoffs).map((x) => x.id), "shutoff"), link: pr.link,
          position: Math.round(pr.fraction * 1000) / 1000, props: { name: null, state: "open" as const, attributes: {} } };
        st.commit((n) => ({ ...n, shutoffs: { ...n.shutoffs, [sh.uid]: sh } }));
        st.select([sh.uid]);
        return;
      }
      case "feasibility": {
        const pr = pipeAt(p);
        if (!pr) { st.toast("Haga clic sobre una tubería para evaluar la conexión.", "error"); return; }
        st.set({ feasibilityDraft: { pos: pr.point, link: pr.link } });
        return;
      }
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

  // Crear con la herramienta activa en una coordenada ingresada («Ingresar coordenadas»): igual que un clic allí.
  const placeRequest = s.placeRequest;
  useEffect(() => {
    if (!placeRequest) return;
    useEditor.getState().set({ placeRequest: null });
    clickAction(proj(placeRequest.pos), { type: "bg" }, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placeRequest]);

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
  const labelItems: LabelItem[] = [];
  const lbl = (uid: string, x: number, y: number, text: string, cls: string, prio: number, anchor: "start" | "middle" = "start") =>
    labelItems.push({ key: `${uid}-lbl`, uid, x, y, text, cls, prio: selected.has(uid) ? 100 : prio, anchor });
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
    if (labels.length && l.kind === "pipe") texts.push(fmtLen(l.props.length_hydraulic_m ?? estimatedLength(net, l)));
    if (r && labels.flow) texts.push(`${fmt(r.flow[period], 2)} L/s`);
    if (r && labels.velocity) texts.push(`${fmt(Math.abs(r.velocity[period]), 2)} m/s`);
    if (r && labels.headloss && l.kind === "pipe") texts.push(`${fmt(Math.abs(r.headloss[period]), 2)} m/km`);
    if (texts.length && mid.length > 40) {
      lbl(l.uid, mid.p[0], mid.p[1] - 8, texts.join(" · "), "lbl lbl-link", 30, "middle");
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
    if (texts.length) lbl(n.uid, x + 9, y - 7, texts.join(" · "), "lbl", n.kind === "junction" ? 50 : 60);
  }

  // Sectores sin agua (escenario de llaves mostrado)
  const dryNodes = new Set(scenarioView?.unsupplied_nodes ?? []);
  const dryLinks = new Set([...(scenarioView?.unsupplied_links ?? []), ...(scenarioView?.closed_links ?? [])]);
  const dryEls: React.ReactNode[] = [];
  if (scenarioView) {
    for (const l of Object.values(net.links)) {
      if (!dryLinks.has(l.id)) continue;
      const pts = linkCoords(net, l).map(proj);
      dryEls.push(<polyline key={`dry-${l.uid}`} className="dry-link" points={pts.map((q) => q.join(",")).join(" ")} />);
    }
    for (const n of Object.values(net.nodes)) {
      if (!dryNodes.has(n.id)) continue;
      const [x, y] = proj(n.pos);
      dryEls.push(<circle key={`dry-${n.uid}`} className="dry-node" cx={x} cy={y} r={9 * zoomScale} />);
    }
  }

  // Llaves de corte
  const shutoffEls: React.ReactNode[] = [];
  const closedByScenario = scenarioView ? new Set(scenarioView.closed_shutoffs) : null;
  for (const sh of Object.values(net.shutoffs)) {
    const l = net.links[sh.link];
    if (!l) continue;
    const coords = linkCoords(net, l);
    const at = proj(pointAlong(coords, sh.position));
    const ahead = proj(pointAlong(coords, Math.min(1, sh.position + 0.01)));
    const behind = proj(pointAlong(coords, Math.max(0, sh.position - 0.01)));
    const deg = (Math.atan2(ahead[1] - behind[1], ahead[0] - behind[0]) * 180) / Math.PI;
    const closed = closedByScenario ? closedByScenario.has(sh.id) : sh.props.state === "closed";
    const k = 6 * zoomScale;
    shutoffEls.push(
      <g key={sh.uid} transform={`translate(${at[0]},${at[1]}) rotate(${deg})`} className={`shutoff ${closed ? "closed" : "open"} ${selected.has(sh.uid) ? "sel" : ""}`}
        data-t="shutoff" data-uid={sh.uid}>
        <title>{`${sh.id}${sh.props.name ? ` · ${sh.props.name}` : ""} — ${closed ? "cerrada" : "abierta"}`}</title>
        {selected.has(sh.uid) && <circle r={k + 6} className="node-sel" />}
        <path d={`M ${-k} ${-k} L ${k} ${k} L ${k} ${-k} L ${-k} ${k} Z`} />
        <circle r={k + 3} className="hit-node" />
      </g>,
    );
    if (labels.linkIds) lbl(sh.uid, at[0] + 9, at[1] + 14, sh.id, "lbl lbl-link", 20);
  }

  // Clientes y sus arranques
  const clientEls: React.ReactNode[] = [];
  const dryClients = new Set(scenarioView?.clients.filter((c) => !c.supplied).map((c) => c.id) ?? []);
  const lowClients = new Set(scenarioView?.clients.filter((c) => c.supplied && c.below_min).map((c) => c.id) ?? []);
  for (const c of Object.values(net.clients)) {
    const [x, y] = proj(c.pos);
    if (x < -50 || y < -50 || x > size.width + 50 || y > size.height + 50) continue;
    const conn = c.connection ? proj(c.connection) : null;
    const nodePos = net.nodes[c.node] ? proj(net.nodes[c.node].pos) : null;
    const k = 5 * zoomScale;
    const state = dryClients.has(c.id) ? "dry" : lowClients.has(c.id) ? "low" : c.props.status;
    clientEls.push(
      <g key={c.uid} className={`client client-${state} ${selected.has(c.uid) ? "sel" : ""}`}>
        {conn && <line className="service-line" x1={x} y1={y} x2={conn[0]} y2={conn[1]} />}
        {conn && nodePos && c.props.connection_mode === "nearest" && (
          <line className="service-assign" x1={conn[0]} y1={conn[1]} x2={nodePos[0]} y2={nodePos[1]} />)}
        <g transform={`translate(${x},${y})`} data-t="client" data-uid={c.uid}>
          <title>{`${c.id}${c.props.name ? ` · ${c.props.name}` : ""} → ${net.nodes[c.node]?.id ?? "?"}`}</title>
          {selected.has(c.uid) && <circle r={k + 6} className="node-sel" />}
          <path d={`M 0 ${-k * 1.2} L ${k} ${-k * 0.2} L ${k} ${k} L ${-k} ${k} L ${-k} ${-k * 0.2} Z`} />
          <circle r={k + 4} className="hit-node" />
        </g>
      </g>,
    );
    if (labels.nodeIds) lbl(c.uid, x + 8, y + 4, c.id, "lbl lbl-link", 10);
  }

  // Grifos y pozos
  const assetEls: React.ReactNode[] = [];
  for (const h of Object.values(net.hydrants)) {
    const [x, y] = proj(h.pos);
    if (x < -50 || y < -50 || x > size.width + 50 || y > size.height + 50) continue;
    const k = 6 * zoomScale;
    const np = net.nodes[h.node] ? proj(net.nodes[h.node].pos) : null;
    assetEls.push(
      <g key={h.uid} className={`hydrant ${selected.has(h.uid) ? "sel" : ""}`}>
        {np && <line className="service-assign" x1={x} y1={y} x2={np[0]} y2={np[1]} />}
        <g transform={`translate(${x},${y})`} data-t="hydrant" data-uid={h.uid}>
          <title>{`Grifo ${h.id} → ${net.nodes[h.node]?.id ?? "?"}`}</title>
          {selected.has(h.uid) && <circle r={k + 6} className="node-sel" />}
          <path d={`M ${-k * 0.6} ${k} L ${-k * 0.6} ${-k * 0.4} L 0 ${-k} L ${k * 0.6} ${-k * 0.4} L ${k * 0.6} ${k} Z M ${-k} 0 L ${k} 0`} />
          <circle r={k + 4} className="hit-node" />
        </g>
      </g>,
    );
    if (labels.nodeIds) lbl(h.uid, x + 9, y - 6, h.id, "lbl", 40);
  }
  for (const w of Object.values(net.wells)) {
    const [x, y] = proj(w.pos);
    if (x < -50 || y < -50 || x > size.width + 50 || y > size.height + 50) continue;
    const k = 7 * zoomScale;
    assetEls.push(
      <g key={w.uid} transform={`translate(${x},${y})`} className={`well ${selected.has(w.uid) ? "sel" : ""}`} data-t="well" data-uid={w.uid}>
        <title>{`Pozo ${w.id}${w.node && net.nodes[w.node] ? ` → ${net.nodes[w.node].id}` : ""}`}</title>
        {selected.has(w.uid) && <circle r={k + 6} className="node-sel" />}
        <circle r={k} /><circle r={k * 0.4} className="well-core" />
        <circle r={k + 4} className="hit-node" />
      </g>,
    );
    if (labels.nodeIds) lbl(w.uid, x + 10, y + 4, w.id, "lbl", 40);
  }

  // Capas del Resumen: zonas por presión y área operacional (bajo la red, sin capturar clics)
  const overlayEls: React.ReactNode[] = [];
  const ringPath = (rings: LngLat[][]) => rings.map((r) => r.map((c, i) => `${i ? "L" : "M"}${proj(c).join(" ")}`).join(" ") + " Z").join(" ");
  for (const z of s.overlay.zones) {
    overlayEls.push(<path key={z.key} className="ov-zone" d={ringPath(z.coords)} style={{ fill: z.color, stroke: z.color }}><title>{z.label}</title></path>);
  }
  for (const a of s.overlay.area) overlayEls.push(<path key={a.key} className="ov-area" d={ringPath(a.coords)} />);

  // Resultado de consulta destacado
  const hl = new Set(s.highlight);
  const hlEls: React.ReactNode[] = [];
  if (hl.size) {
    for (const l of Object.values(net.links)) {
      if (!hl.has(l.uid)) continue;
      hlEls.push(<polyline key={`hl-${l.uid}`} className="hl-link" points={linkCoords(net, l).map(proj).map((q) => q.join(",")).join(" ")} />);
    }
    for (const pool of [net.nodes, net.clients, net.hydrants, net.wells] as Record<string, { uid: string; pos: LngLat }>[]) {
      for (const e of Object.values(pool)) {
        if (!hl.has(e.uid)) continue;
        const [x, y] = proj(e.pos);
        hlEls.push(<circle key={`hl-${e.uid}`} className="hl-point" cx={x} cy={y} r={10 * zoomScale} />);
      }
    }
    for (const sh of Object.values(net.shutoffs)) {
      if (!hl.has(sh.uid) || !net.links[sh.link]) continue;
      const [x, y] = proj(pointAlong(linkCoords(net, net.links[sh.link]), sh.position));
      hlEls.push(<circle key={`hl-${sh.uid}`} className="hl-point" cx={x} cy={y} r={10 * zoomScale} />);
    }
  }

  // Mapa de calor (desde «Gestión»: fugas por tramo, etc.)
  const heatEls: React.ReactNode[] = [];
  if (s.heat) {
    for (const [u, w] of Object.entries(s.heat)) {
      const l = net.links[u];
      if (l) {
        heatEls.push(<polyline key={`ht-${u}`} className="heat-link" points={linkCoords(net, l).map(proj).map((q) => q.join(",")).join(" ")}
          style={{ strokeOpacity: 0.25 + 0.6 * w, strokeWidth: 8 + 12 * w }} />);
        continue;
      }
      const pos = net.nodes[u]?.pos ?? net.clients[u]?.pos ?? net.hydrants[u]?.pos ?? net.wells[u]?.pos;
      if (pos) {
        const [x, y] = proj(pos);
        heatEls.push(<circle key={`ht-${u}`} className="heat-point" cx={x} cy={y} r={8 + 12 * w} style={{ fillOpacity: 0.2 + 0.5 * w }} />);
      }
    }
  }
  const pinEl = s.pin ? (() => {
    const [x, y] = proj(s.pin);
    return (
      <g className="coord-pin" transform={`translate(${x},${y})`} data-pin={`${s.pin[1].toFixed(6)},${s.pin[0].toFixed(6)}`}>
        <circle r={9} /><path d="M -14 0 H -4 M 4 0 H 14 M 0 -14 V -4 M 0 4 V 14" />
      </g>
    );
  })() : null;

  // Anillo del resaltado breve
  const flashEls: React.ReactNode[] = [];
  if (flash && flashOn === flash.nonce) {
    for (const u of flash.uids) {
      const l = net.links[u];
      if (l) {
        flashEls.push(<polyline key={`fl-${u}`} className="flash-link" points={linkCoords(net, l).map(proj).map((q) => q.join(",")).join(" ")} />);
        continue;
      }
      const sh = net.shutoffs[u];
      const pos = net.nodes[u]?.pos ?? net.clients[u]?.pos ?? net.hydrants[u]?.pos ?? net.wells[u]?.pos
        ?? (sh && net.links[sh.link] ? pointAlong(linkCoords(net, net.links[sh.link]), sh.position) : undefined);
      if (!pos) continue;
      const [x, y] = proj(pos);
      flashEls.push(<circle key={`fl-${u}-${flash.nonce}`} className="flash-ring" cx={x} cy={y} r={14} />);
    }
  }

  // Cuartel de corta destacado: tramos del cuartel y válvulas a cerrar
  const sectorEls: React.ReactNode[] = [];
  const focusSector = s.sectors?.sectors.find((x) => x.id === s.sectorFocus);
  if (focusSector) {
    const byLabel = new Map(Object.values(net.links).map((l) => [l.id, l]));
    for (const pc of focusSector.pieces) {
      const l = byLabel.get(pc.link);
      if (!l) continue;
      const coords = linkCoords(net, l);
      const n = 12;
      const pts = Array.from({ length: n + 1 }, (_, i) => proj(pointAlong(coords, pc.start + ((pc.end - pc.start) * i) / n)));
      sectorEls.push(<polyline key={`sec-${pc.link}-${pc.start}`} className="sector-link" points={pts.map((q) => q.join(",")).join(" ")} />);
    }
    const downstream = new Set(focusSector.downstream_nodes);
    for (const n of Object.values(net.nodes)) {
      if (!downstream.has(n.id)) continue;
      const [x, y] = proj(n.pos);
      sectorEls.push(<circle key={`down-${n.uid}`} className="dry-node" cx={x} cy={y} r={9 * zoomScale} />);
    }
    const toClose = new Set(focusSector.valves);
    for (const sh of Object.values(net.shutoffs)) {
      if (!toClose.has(sh.id) || !net.links[sh.link]) continue;
      const [x, y] = proj(pointAlong(linkCoords(net, net.links[sh.link]), sh.position));
      sectorEls.push(<circle key={`close-${sh.uid}`} className="sector-valve" cx={x} cy={y} r={12 * zoomScale} />);
    }
  }

  // Punto de factibilidad pendiente
  const fd = s.feasibilityDraft;
  const feasEl = fd ? (() => { const [x, y] = proj(fd.pos); return <g className="feas-pt" transform={`translate(${x},${y})`}><circle r={9} /><circle r={3} /></g>; })() : null;

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

  // Etiquetas sin superposición: las que chocan se ocultan y aparecen al pasar el mouse sobre su elemento.
  const visible = placeLabels(labelItems, size);
  const labelEls = labelItems.filter((l) => visible.has(l.key)).map((l) =>
    <text key={l.key} x={l.x} y={l.y} className={l.cls} textAnchor={l.anchor === "middle" ? "middle" : undefined}>{l.text}</text>);
  const hidden = hoverUid ? labelItems.find((l) => l.uid === hoverUid && !visible.has(l.key)) : undefined;
  const hoverLabel = hidden ? <text x={hidden.x} y={hidden.y} className={`${hidden.cls} lbl-hover`} textAnchor={hidden.anchor === "middle" ? "middle" : undefined}>{hidden.text}</text> : null;

  const box = gesture.kind === "box" ? gesture : null;
  const pass = passThrough && !shiftDown && gesture.kind === "none";
  const cursorClass = gesture.kind === "pan" ? "grabbing" : s.mapPick ? "tool-pick" : `tool-${tool}`;

  return (
    <svg ref={svgRef} className={`net-layer ${cursorClass}${pass ? " pass" : ""}`} width={size.width} height={size.height}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
      onPointerOver={(e) => { const t = readTarget(e.target); setHoverUid(isEl(t) ? t.uid : null); }}
      onPointerLeave={() => { setCursor(null); setHoverUid(null); }} onDoubleClick={onDoubleClick} onWheel={onWheel} onContextMenu={onContextMenu}>
      <g className="overlay">{overlayEls}</g>
      <g>{dryEls}</g>
      <g>{sectorEls}</g>
      <g className="heat">{heatEls}</g>
      <g>{hlEls}</g>
      <g>{linkEls}</g>
      <g>{arrowEls}</g>
      <g>{clientEls}</g>
      <g>{shutoffEls}</g>
      <g>{nodeEls}</g>
      <g>{assetEls}</g>
      {pinEl}
      <g className="flash" data-flash={flashEls.length ? flash?.uids.join(" ") : undefined}>{flashEls}</g>
      {feasEl}
      <g>{handleEls}</g>
      <g className="labels">{labelEls}</g>
      {hoverLabel}
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

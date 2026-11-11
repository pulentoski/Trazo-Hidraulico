// Subida por partes reanudable de ortofotos: partes de tamaño fijo, reintentos con espera creciente y retoma desde
// el último byte confirmado por el servidor (también tras recargar la página: se recuerda la subida por archivo).
import { apiFetch } from "../api/http";
import type { OrthophotoOut } from "../api/types";

export interface UploadMeta { name?: string; source?: string; captured_on?: string; src_crs?: string; world?: string; target_res_cm?: number | null }
export interface UploadState { ortho: OrthophotoOut; offset: number; size: number; chunk_size: number; complete: boolean }
export interface Progress { sent: number; total: number; speed: number; eta: number | null; retrying: number }

export class UploadError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

const KEY = (pid: string, f: File) => `trazo.upload.${pid}.${f.name}.${f.size}.${f.lastModified}`;

export function rememberedUpload(pid: string, f: File): string | null {
  try { return localStorage.getItem(KEY(pid, f)); } catch { return null; }
}
function remember(pid: string, f: File, oid: string | null): void {
  try { if (oid) localStorage.setItem(KEY(pid, f), oid); else localStorage.removeItem(KEY(pid, f)); } catch { /* sin almacenamiento */ }
}

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const d = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
    throw new UploadError(res.status, typeof d === "string" ? d : `Error ${res.status}`);
  }
  return body as T;
}

/** Envía una parte con XMLHttpRequest (progreso dentro de la parte). Devuelve el estado o el offset esperado (409). */
function putPart(url: string, blob: Blob, onBytes: (n: number) => void, signal: AbortSignal): Promise<UploadState | { offset: number }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => onBytes(e.loaded);
    xhr.onload = () => {
      let body: unknown = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* sin cuerpo */ }
      if (xhr.status === 409 && body && typeof body === "object" && "offset" in body) resolve({ offset: Number((body as { offset: number }).offset) });
      else if (xhr.status >= 200 && xhr.status < 300) resolve(body as UploadState);
      else {
        const d = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
        reject(new UploadError(xhr.status, typeof d === "string" ? d : `Error ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new UploadError(0, "Se perdió la conexión"));
    xhr.ontimeout = () => reject(new UploadError(0, "La conexión tardó demasiado"));
    const abort = () => xhr.abort();
    signal.addEventListener("abort", abort, { once: true });
    xhr.onabort = () => reject(new UploadError(-1, "Subida pausada"));
    xhr.send(blob);
  });
}

const sleep = (ms: number, signal: AbortSignal) => new Promise<void>((res, rej) => {
  const t = window.setTimeout(res, ms);
  signal.addEventListener("abort", () => { window.clearTimeout(t); rej(new UploadError(-1, "Subida pausada")); }, { once: true });
});

/** Sube `file` por partes (o retoma una subida anterior del mismo archivo). */
export async function uploadInParts(pid: string, file: File, meta: UploadMeta, onProgress: (p: Progress) => void,
  signal: AbortSignal): Promise<UploadState> {
  const base = `/api/projects/${encodeURIComponent(pid)}/orthophotos`;
  let state: UploadState | null = null;
  const prev = rememberedUpload(pid, file);
  if (prev) {
    const r = await apiFetch(`${base}/${encodeURIComponent(prev)}/upload`);
    if (r.ok) {
      const s = (await r.json()) as UploadState;
      if (s.ortho.status === "uploading" && s.size === file.size) state = s;
    }
    if (!state) remember(pid, file, null);
  }
  if (!state) {
    state = await json<UploadState>(await apiFetch(`${base}/uploads`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, size: file.size, ...meta }),
    }));
    remember(pid, file, state.ortho.id);
  }
  const url = `${base}/${encodeURIComponent(state.ortho.id)}/upload`;
  let offset = state.offset;
  const t0 = performance.now();
  const start = offset;
  let speed = 0;
  let retrying = 0;
  const report = (sent: number) => {
    const dt = (performance.now() - t0) / 1000;
    if (dt > 0.3) speed = (sent - start) / dt;
    onProgress({ sent, total: file.size, speed, eta: speed > 0 ? (file.size - sent) / speed : null, retrying });
  };
  report(offset);
  while (!state.complete && offset < file.size) {
    const blob = file.slice(offset, Math.min(file.size, offset + state.chunk_size));
    try {
      const r = await putPart(`${url}?offset=${offset}`, blob, (n) => report(offset + n), signal);
      retrying = 0;
      if ("ortho" in r) { state = r; offset = r.offset; } else offset = r.offset;
      report(offset);
    } catch (e) {
      const err = e as UploadError;
      if (err.status === -1 || (err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429)) throw err;
      retrying += 1;  // corte de red o error temporal del servidor: reintentar y retomar desde lo confirmado
      if (retrying > 8) throw new UploadError(0, "No se pudo continuar la subida: revise la conexión y vuelva a elegir el archivo para retomarla.");
      report(offset);
      await sleep(Math.min(30000, 1000 * 2 ** (retrying - 1)), signal);
      try {
        const s = (await (await apiFetch(url)).json()) as UploadState;
        offset = s.offset;
        state = s;
      } catch { /* se reintenta con el offset conocido */ }
    }
  }
  remember(pid, file, null);
  return state;
}

export function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toLocaleString("es-CL", { maximumFractionDigits: 2 })} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toLocaleString("es-CL", { maximumFractionDigits: 1 })} MB`;
  return `${Math.round(n / 1024).toLocaleString("es-CL")} kB`;
}

export function fmtEta(s: number | null): string {
  if (s === null || !Number.isFinite(s)) return "calculando…";
  if (s < 60) return `${Math.ceil(s)} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${Math.round(s % 60)} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

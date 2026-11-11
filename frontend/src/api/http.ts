// Solicitudes a la API con reintento ante «Demasiadas solicitudes» (429): nunca cierran la sesión. Se espera lo
// que indica Retry-After (o una espera creciente: 1, 2, 4, 8… s, con tope) y se avisa una vez por ráfaga.
export const MAX_RETRIES = 6;
const MAX_WAIT_S = 30;

type Notice = (text: string) => void;
let notice: Notice | null = null;
let lastNotice = 0;

/** Lo registra la aplicación (Shell) para mostrar el aviso como toast. */
export function onRateLimitNotice(fn: Notice | null): void {
  notice = fn;
}

/** Segundos a esperar antes del intento `attempt` (0, 1, 2…): Retry-After si viene; si no, exponencial. */
export function retryDelay(res: Response | null, attempt: number): number {
  const h = res?.headers.get("Retry-After");
  const s = h !== null && h !== undefined && h !== "" ? Number(h) : NaN;
  const base = Number.isFinite(s) && s >= 0 ? s : 2 ** attempt;
  return Math.min(MAX_WAIT_S, Math.max(0.5, base));
}

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit, wait: (ms: number) => Promise<void> = sleep): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    // Un Request solo se puede leer una vez: cada intento usa una copia.
    const res = await fetch(input instanceof Request ? input.clone() : input, init);
    if (res.status !== 429 || attempt >= MAX_RETRIES) return res;
    const now = Date.now();
    if (notice && now - lastNotice > 5000) {
      lastNotice = now;
      notice("Demasiadas solicitudes, reintentando…");
    }
    await wait(retryDelay(res, attempt) * 1000);
  }
}

import { afterEach, describe, expect, it, vi } from "vitest";
import { MAX_RETRIES, apiFetch, onRateLimitNotice, retryDelay } from "./http";

const res = (status: number, headers: Record<string, string> = {}) => new Response(status === 200 ? "{}" : "{\"code\":\"rate_limited\"}", { status, headers });

afterEach(() => { vi.unstubAllGlobals(); onRateLimitNotice(null); });

describe("429: reintento sin cerrar la sesión", () => {
  it("respeta Retry-After y luego espera creciente; avisa una vez", async () => {
    const replies = [res(429, { "Retry-After": "3" }), res(429), res(429), res(200)];
    const fetchMock = vi.fn(async () => replies.shift()!);
    vi.stubGlobal("fetch", fetchMock);
    const notices: string[] = [];
    onRateLimitNotice((t) => notices.push(t));
    const waits: number[] = [];
    const r = await apiFetch("/api/auth/me", undefined, async (ms) => { waits.push(ms); });
    expect(r.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(waits).toEqual([3000, 2000, 4000]);
    expect(notices).toEqual(["Demasiadas solicitudes, reintentando…"]);
  });

  it("tras el máximo de reintentos devuelve el 429 (no un 401)", async () => {
    const fetchMock = vi.fn(async () => res(429, { "Retry-After": "1" }));
    vi.stubGlobal("fetch", fetchMock);
    const r = await apiFetch("/api/x", undefined, async () => undefined);
    expect(r.status).toBe(429);
    expect(fetchMock).toHaveBeenCalledTimes(MAX_RETRIES + 1);
  });

  it("Request: cada intento usa una copia (el cuerpo se puede volver a enviar)", async () => {
    const bodies: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (req: Request) => { bodies.push(await req.text()); return bodies.length < 2 ? res(429) : res(200); }));
    const r = await apiFetch(new Request("http://x/api/y", { method: "POST", body: "hola" }), undefined, async () => undefined);
    expect(r.status).toBe(200);
    expect(bodies).toEqual(["hola", "hola"]);
  });

  it("espera: tope de 30 s y mínimo de medio segundo", () => {
    expect(retryDelay(res(429, { "Retry-After": "120" }), 0)).toBe(30);
    expect(retryDelay(res(429, { "Retry-After": "0" }), 0)).toBe(0.5);
    expect(retryDelay(null, 3)).toBe(8);
  });
});

describe("sesión", () => {
  it("un 429 de /api/auth/me no deja la sesión como cerrada; un 401 sí", async () => {
    vi.stubGlobal("window", { setTimeout: () => 0, location: { pathname: "/", search: "", assign: () => undefined } });
    const { ApiError, api } = await import("./client");
    const { useAuth } = await import("../state/auth");
    const spy = vi.spyOn(api, "me").mockRejectedValueOnce(new ApiError(429, "Demasiadas solicitudes", { code: "rate_limited" }));
    await useAuth.getState().refresh();
    expect(useAuth.getState().status).toBe("loading");
    spy.mockRejectedValueOnce(new ApiError(401, "Inicie sesión", { code: "login_required" }));
    await useAuth.getState().refresh();
    expect(useAuth.getState().status).toBe("anon");
  });
});

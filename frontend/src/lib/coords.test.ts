import { describe, expect, it } from "vitest";
import { formatUtm, fromUtm, parseCoordinates, toDms, toUtm, zoneOf } from "./coords";

// Valores de referencia calculados con PROJ (pyproj, EPSG:4326 → EPSG:327xx/326xx).
const REF: [number, number, number, boolean, number, number][] = [
  [-70.6693, -33.4489, 19, true, 344846.72, 6297700.156], // Santiago
  [-71.145, -29.942, 19, true, 292975.074, 6685706.702], // La Serena (APR Demo)
  [-73.05, -36.82, 18, true, 673921.004, 5923321.216], // Concepción, huso 18
  [2.2945, 48.8584, 31, false, 448252.001, 5411954.91], // hemisferio norte
];

describe("UTM ↔ lat/lon", () => {
  it.each(REF)("%f, %f → huso %i", (lon, lat, zone, south, e, n) => {
    const u = toUtm([lon, lat], zone, south);
    expect(u.e).toBeCloseTo(e, 2);
    expect(u.n).toBeCloseTo(n, 2);
    const [lo, la] = fromUtm(u);
    expect(lo).toBeCloseTo(lon, 8);
    expect(la).toBeCloseTo(lat, 8);
  });
  it("huso por longitud y formato", () => {
    expect(zoneOf(-70.67)).toBe(19);
    expect(zoneOf(-73.05)).toBe(18);
    expect(formatUtm(toUtm([-70.6693, -33.4489]))).toMatch(/^19S E 344[.]847 N 6[.]297[.]700$/);
  });
});

describe("grados-minutos-segundos", () => {
  it("formatea con hemisferios", () => {
    expect(toDms([-70.6693, -33.4489])).toBe("33°26′56,0″S 070°40′09,5″W");
    expect(toDms([2.2945, 48.8584], 0)).toBe("48°51′30″N 002°17′40″E");
  });
  it("redondeo que llega a 60″", () => {
    expect(toDms([-70.99999999, -33.99999999])).toBe("34°00′00,0″S 071°00′00,0″W");
  });
});

describe("texto libre → coordenada", () => {
  const close = (p: ReturnType<typeof parseCoordinates>, lon: number, lat: number, d = 5) => {
    expect(p).not.toBeNull();
    expect(p!.pos[0]).toBeCloseTo(lon, d);
    expect(p!.pos[1]).toBeCloseTo(lat, d);
  };
  it("decimal lat, lon", () => {
    const p = parseCoordinates("-33.4489, -70.6693");
    close(p, -70.6693, -33.4489);
    expect(p!.kind).toBe("decimal");
    close(parseCoordinates("-33,4489; -70,6693"), -70.6693, -33.4489);
    close(parseCoordinates("33.4489 S 70.6693 W"), -70.6693, -33.4489);
    close(parseCoordinates("70.6693W 33.4489S"), -70.6693, -33.4489);
  });
  it("grados-minutos-segundos", () => {
    const p = parseCoordinates(`33°26'56"S 70°40'9.5"W`);
    close(p, -70.66931, -33.44889, 4);
    expect(p!.kind).toBe("dms");
    close(parseCoordinates("33° 26′ 56″ S, 70° 40′ 9,5″ O"), -70.66931, -33.44889, 4);
    close(parseCoordinates("S 33° 26.933' W 70° 40.158'"), -70.6693, -33.44888, 4);
    close(parseCoordinates("33 26 56 S 70 40 9.5 W"), -70.66931, -33.44889, 4);
  });
  it("UTM con huso 19S por defecto, rótulos y banda", () => {
    const p = parseCoordinates("344846.72 6297700.156");
    close(p, -70.6693, -33.4489, 6);
    expect(p!.kind).toBe("utm");
    expect(p!.utm).toMatchObject({ zone: 19, south: true });
    close(parseCoordinates("N 6297700,156 E 344846,72"), -70.6693, -33.4489, 6);
    close(parseCoordinates("E=673921.004 N=5923321.216 18S"), -73.05, -36.82, 6);
    close(parseCoordinates("18H 673921 5923321"), -73.05, -36.82, 4);
    close(parseCoordinates("31N 448252.001 5411954.91"), 2.2945, 48.8584, 6);
  });
  it("rechaza textos que no son coordenadas", () => {
    expect(parseCoordinates("Los Aromos 110, La Serena")).toBeNull();
    expect(parseCoordinates("")).toBeNull();
    expect(parseCoordinates("95, 10")).toBeNull();
  });
});

import { describe, expect, it } from "vitest";
import { baseOf } from "./mapBase";
import { nominatimUrl } from "./nominatim";

describe("mapa base", () => {
  it("usa OpenStreetMap por defecto sin key de Google", () => {
    expect(baseOf("auto", "")).toBe("osm");
    expect(baseOf("google", "")).toBe("osm");
    expect(baseOf("auto", "AIzaXYZ")).toBe("google");
    expect(baseOf("osm", "AIzaXYZ")).toBe("osm");
  });
  it("arma la consulta a Nominatim", () => {
    const u = new URL(nominatimUrl("Avenida del Mar 123, La Serena"));
    expect(u.host).toBe("nominatim.openstreetmap.org");
    expect(u.searchParams.get("q")).toBe("Avenida del Mar 123, La Serena");
    expect(u.searchParams.get("format")).toBe("jsonv2");
    expect(u.searchParams.get("limit")).toBe("1");
  });
});

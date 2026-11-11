import { describe, expect, it } from "vitest";
import { cornerMatrix } from "../map/GcpPreviewLayer";
import { fmtBytes, fmtEta } from "./upload";

describe("subida y vista previa", () => {
  it("formatea tamaños y tiempo restante", () => {
    expect(fmtBytes(800 * 1024 * 1024)).toBe("800 MB");
    expect(fmtBytes(2.5 * 1024 ** 3)).toBe("2,5 GB");
    expect(fmtEta(42)).toBe("42 s");
    expect(fmtEta(125)).toBe("2 min 5 s");
    expect(fmtEta(null)).toBe("calculando…");
  });
  it("matriz que lleva las esquinas de la imagen a la pantalla", () => {
    // Imagen 100×50 girada 90°: (0,0)→(10,10), (100,0)→(10,110), (0,50)→(-40,10)
    expect(cornerMatrix(100, 50, [10, 10], [10, 110], [-40, 10])).toEqual([0, 1, -1, 0, 10, 10]);
  });
});

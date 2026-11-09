import { describe, expect, it } from "vitest";
import { canEdit, canReview, ROLE_LABEL } from "./auth";

describe("permisos por rol en la interfaz", () => {
  it("solo administrador y proyectista editan", () => {
    expect(canEdit("admin")).toBe(true);
    expect(canEdit("proyectista")).toBe(true);
    expect(canEdit("revisor")).toBe(false);
    expect(canEdit("lector")).toBe(false);
    expect(canEdit(null)).toBe(false);
  });
  it("solo administrador y revisor aprueban versiones", () => {
    expect(canReview("revisor")).toBe(true);
    expect(canReview("admin")).toBe(true);
    expect(canReview("proyectista")).toBe(false);
    expect(ROLE_LABEL.lector).toBe("Lector");
  });
});

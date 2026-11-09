import createClient from "openapi-fetch";
import type { paths } from "./schema";
import type {
  CatalogPipe, DesignProfile, EngineInfo, ImportResult, NetworkDocument, NetworkSave, NetworkSaveResult,
  ProjectOut, SimulationBlocked, SimulationResult, ValidationReport, VersionOut,
} from "./types";

const client = createClient<paths>({ baseUrl: "" });

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function fail(status: number, body: unknown): never {
  let msg = `Error ${status}`;
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") msg = d;
    else if (d && typeof d === "object" && "message" in d) msg = String((d as { message: unknown }).message);
  }
  throw new ApiError(status, msg, body);
}

async function unwrap<T>(p: Promise<{ data?: unknown; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || !response.ok) fail(response.status, error);
  return data as T;
}

export const api = {
  listProjects: () => unwrap<ProjectOut[]>(client.GET("/api/projects")),
  createProject: (name: string, description = "") =>
    unwrap<ProjectOut>(client.POST("/api/projects", { body: { name, description } })),
  getProject: (id: string) => unwrap<ProjectOut>(client.GET("/api/projects/{project_id}", { params: { path: { project_id: id } } })),
  updateProject: (id: string, body: { name?: string; description?: string; design_profile_id?: number | null }) =>
    unwrap<ProjectOut>(client.PATCH("/api/projects/{project_id}", { params: { path: { project_id: id } }, body })),
  deleteProject: async (id: string) => {
    const { response, error } = await client.DELETE("/api/projects/{project_id}", { params: { path: { project_id: id } } });
    if (!response.ok) fail(response.status, error);
  },
  listVersions: (id: string) =>
    unwrap<VersionOut[]>(client.GET("/api/projects/{project_id}/versions", { params: { path: { project_id: id } } })),
  getNetwork: (id: string, version?: number) =>
    unwrap<NetworkDocument>(client.GET("/api/projects/{project_id}/network", {
      params: { path: { project_id: id }, query: version ? { version } : {} },
    })),
  saveNetwork: (id: string, body: NetworkSave) =>
    unwrap<NetworkSaveResult>(client.PUT("/api/projects/{project_id}/network", { params: { path: { project_id: id } }, body })),
  validate: (id: string, modelVersion: number) =>
    unwrap<ValidationReport>(client.POST("/api/projects/{project_id}/validate", {
      params: { path: { project_id: id } }, body: { model_version: modelVersion },
    })),
  simulate: async (id: string, modelVersion: number): Promise<SimulationResult | SimulationBlocked> => {
    const { data, error, response } = await client.POST("/api/projects/{project_id}/simulate", {
      params: { path: { project_id: id } }, body: { model_version: modelVersion },
    });
    if (response.status === 422 && error && typeof error === "object" && "status" in error) {
      return error as SimulationBlocked;
    }
    if (!response.ok || !data) fail(response.status, error);
    return data;
  },
  catalog: () => unwrap<CatalogPipe[]>(client.GET("/api/catalog/pipes")),
  profiles: () => unwrap<DesignProfile[]>(client.GET("/api/design-profiles")),
  engine: () => unwrap<EngineInfo>(client.GET("/api/engine")),
  importInp: async (file: File, name: string | undefined, crs: string): Promise<ImportResult> => {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    form.append("crs", crs);
    const res = await fetch("/api/projects/import", { method: "POST", body: form });
    const body = await res.json().catch(() => null);
    if (!res.ok) fail(res.status, body);
    return body as ImportResult;
  },
  exportUrl: (id: string, version?: number) =>
    `/api/projects/${encodeURIComponent(id)}/export.inp${version ? `?version=${version}` : ""}`,
};

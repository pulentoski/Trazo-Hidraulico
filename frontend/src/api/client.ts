import createClient from "openapi-fetch";
import type { paths } from "./schema";
import type {
  CatalogPipe, ClientImportResult, CompareResult, DemandInputs, DemandResult, DesignParamsOut, TrazoImportResult, DesignParamUpdate, DesignProfile, EngineInfo,
  FeasibilityRequest, FeasibilityResult, FireResult, Gcp, GcpFit, ImportApplyResult, ImportPreview, ImportResult,
  NetworkDocument, NetworkSave, NetworkSaveResult, OrthophotoOut, ProjectOut, QueryDef, QueryElement, QueryResult,
  SavedQueryOut, ScenarioResult, SearchHit, SectorsResult, SimulationBlocked, SimulationResult, ValidationReport, VersionOut,
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

const STATUS_TEXT: Record<number, string> = {
  401: "Acceso no autorizado: vuelva a ingresar usuario y contraseña.",
  413: "El archivo o la solicitud supera el tamaño máximo permitido.",
  429: "Demasiadas solicitudes: espere un momento y reintente.",
};

function fail(status: number, body: unknown): never {
  let msg = STATUS_TEXT[status] ?? `Error ${status}`;
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

export interface ImportOpts { sheet?: string | null; delete_missing?: boolean; utm_zone?: number | null; hemisphere?: string }

/** POST multipart con un archivo y campos; los 422 con cuerpo de importación se devuelven (no son excepción). */
async function form<T>(url: string, file: File, fields: object): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null && v !== "") fd.append(k, String(v));
  const res = await fetch(url, { method: "POST", body: fd });
  const body = await res.json().catch(() => null);
  if (res.status === 422 && body && typeof body === "object" && "preview" in body) return body as T;
  if (!res.ok) fail(res.status, body);
  return body as T;
}

export const api = {
  listProjects: () => unwrap<ProjectOut[]>(client.GET("/api/projects")),
  createProject: (name: string, description = "", designProfileId: number | null = null) =>
    unwrap<ProjectOut>(client.POST("/api/projects", {
      body: { name, description, ...(designProfileId != null ? { design_profile_id: designProfileId } : {}) },
    })),
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
  designParams: (id: string) =>
    unwrap<DesignParamsOut>(client.GET("/api/projects/{project_id}/design-params", { params: { path: { project_id: id } } })),
  saveDesignParams: (id: string, body: DesignParamUpdate[]) =>
    unwrap<DesignParamsOut>(client.PUT("/api/projects/{project_id}/design-params", { params: { path: { project_id: id } }, body })),
  scenario: (id: string, modelVersion: number, scenario: string) =>
    unwrap<ScenarioResult>(client.POST("/api/projects/{project_id}/scenarios/simulate", {
      params: { path: { project_id: id } }, body: { model_version: modelVersion, scenario },
    })),
  compareScenarios: (id: string, modelVersion: number, a: string, b: string) =>
    unwrap<CompareResult>(client.POST("/api/projects/{project_id}/scenarios/compare", {
      params: { path: { project_id: id } }, body: { model_version: modelVersion, a, b },
    })),
  feasibility: (id: string, body: FeasibilityRequest) =>
    unwrap<FeasibilityResult>(client.POST("/api/projects/{project_id}/feasibility", { params: { path: { project_id: id } }, body })),
  /** Informe HTML: se abre en una pestaña nueva para imprimir o guardar como PDF. */
  feasibilityReport: async (id: string, body: FeasibilityRequest): Promise<string> => {
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/feasibility/report`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!res.ok) fail(res.status, await res.json().catch(() => null));
    return res.text();
  },
  importClients: async (id: string, file: File, baseVersion: number | null): Promise<ClientImportResult> => {
    const form = new FormData();
    form.append("file", file);
    if (baseVersion != null) form.append("base_version", String(baseVersion));
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/clients/import`, { method: "POST", body: form });
    const body = await res.json().catch(() => null);
    if (!res.ok) fail(res.status, body);
    return body as ClientImportResult;
  },
  // ── Demanda y formato .trazo ──
  demandProjection: (id: string) =>
    unwrap<DemandResult>(client.GET("/api/projects/{project_id}/demand/projection", { params: { path: { project_id: id } } })),
  saveDemandProjection: (id: string, body: DemandInputs) =>
    unwrap<DemandResult>(client.PUT("/api/projects/{project_id}/demand/projection", { params: { path: { project_id: id } }, body })),
  resetDemandProjection: (id: string) =>
    unwrap<DemandResult>(client.DELETE("/api/projects/{project_id}/demand/projection", { params: { path: { project_id: id } } })),
  applyDemandScenario: (id: string, scenario: "base" | "actual" | "horizonte") =>
    unwrap<{ version: number; multiplier: number }>(client.POST("/api/projects/{project_id}/demand/scenario", {
      params: { path: { project_id: id } }, body: { scenario },
    })),
  demandXlsxUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/demand/projection.xlsx`,
  trazoUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/export.trazo`,
  importTrazo: (file: File, name?: string) => form<TrazoImportResult>("/api/projects/import-trazo", file, { name }),
  // ── SIG ──
  templateUrl: "/api/sig/template.xlsx",
  excelUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/sig/export.xlsx`,
  dxfUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/export.dxf`,
  gpkgUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/export.gpkg`,
  sectorExportUrl: (id: string, sector: string, fmt: "csv" | "xlsx") =>
    `/api/projects/${encodeURIComponent(id)}/sectors/${encodeURIComponent(sector)}/export?fmt=${fmt}`,
  importPreview: (id: string, file: File, opts: ImportOpts) => form<ImportPreview>(`/api/projects/${encodeURIComponent(id)}/sig/import/preview`, file, opts),
  importApply: (id: string, file: File, opts: ImportOpts & { base_version?: number | null }) =>
    form<ImportApplyResult>(`/api/projects/${encodeURIComponent(id)}/sig/import/apply`, file, opts),
  createFromExcel: (file: File, opts: { name?: string; utm_zone?: number | null }) => form<ImportApplyResult>("/api/projects/import-excel", file, opts),
  sectors: (id: string) => unwrap<SectorsResult>(client.GET("/api/projects/{project_id}/sectors", { params: { path: { project_id: id } } })),
  queryFields: () => unwrap<QueryElement[]>(client.GET("/api/sig/query-fields")),
  query: (id: string, body: QueryDef) =>
    unwrap<QueryResult>(client.POST("/api/projects/{project_id}/query", { params: { path: { project_id: id } }, body })),
  queryExport: async (id: string, body: QueryDef, fmt: "csv" | "xlsx"): Promise<Blob> => {
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/query/export?fmt=${fmt}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!res.ok) fail(res.status, await res.json().catch(() => null));
    return res.blob();
  },
  search: (id: string, q: string) =>
    unwrap<SearchHit[]>(client.GET("/api/projects/{project_id}/search", { params: { path: { project_id: id }, query: { q } } })),
  savedQueries: (id: string) =>
    unwrap<SavedQueryOut[]>(client.GET("/api/projects/{project_id}/queries", { params: { path: { project_id: id } } })),
  saveQuery: (id: string, name: string, definition: QueryDef) =>
    unwrap<SavedQueryOut>(client.POST("/api/projects/{project_id}/queries", { params: { path: { project_id: id } }, body: { name, definition } })),
  deleteQuery: async (id: string, queryId: number) => {
    const { response, error } = await client.DELETE("/api/projects/{project_id}/queries/{query_id}", {
      params: { path: { project_id: id, query_id: queryId } },
    });
    if (!response.ok) fail(response.status, error);
  },
  fire: (id: string) =>
    unwrap<FireResult>(client.POST("/api/projects/{project_id}/hydrants/fire", { params: { path: { project_id: id } } })),
  orthos: (id: string) =>
    unwrap<OrthophotoOut[]>(client.GET("/api/projects/{project_id}/orthophotos", { params: { path: { project_id: id } } })),
  uploadOrtho: async (id: string, file: File, world: File | null, meta: { name?: string; source?: string; captured_on?: string; src_crs?: string }) => {
    const fd = new FormData();
    fd.append("file", file);
    if (world) fd.append("world", world);
    for (const [k, v] of Object.entries(meta)) if (v) fd.append(k, v);
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/orthophotos`, { method: "POST", body: fd });
    const body = await res.json().catch(() => null);
    if (!res.ok) fail(res.status, body);
    return body as OrthophotoOut;
  },
  updateOrtho: (id: string, oid: string, body: { name?: string; source?: string | null; captured_on?: string | null; opacity?: number; visible?: boolean }) =>
    unwrap<OrthophotoOut>(client.PATCH("/api/projects/{project_id}/orthophotos/{ortho_id}", {
      params: { path: { project_id: id, ortho_id: oid } }, body,
    })),
  deleteOrtho: async (id: string, oid: string) => {
    const { response, error } = await client.DELETE("/api/projects/{project_id}/orthophotos/{ortho_id}", {
      params: { path: { project_id: id, ortho_id: oid } },
    });
    if (!response.ok) fail(response.status, error);
  },
  orthoOriginalUrl: (id: string, oid: string) => `/api/projects/${encodeURIComponent(id)}/orthophotos/${encodeURIComponent(oid)}/original`,
  gcps: (id: string, oid: string, gcps: Gcp[], apply: boolean) =>
    unwrap<GcpFit>(client.POST("/api/projects/{project_id}/orthophotos/{ortho_id}/gcps", {
      params: { path: { project_id: id, ortho_id: oid } }, body: { gcps, apply },
    })),
  exportUrl: (id: string, version?: number) =>
    `/api/projects/${encodeURIComponent(id)}/export.inp${version ? `?version=${version}` : ""}`,
};

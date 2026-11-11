import createClient from "openapi-fetch";
import type { paths } from "./schema";
import type {
  CatalogPipe, ClientImportResult, CompareResult, DemandInputs, DemandResult, DesignParamsOut, TrazoImportResult,
  DiagnosisResult, MeasureCompare, AuditOut, AuthStatus, InvitationInfo, Me, MemberOut, MfaSetup, OrgAdminOut, ReviewOut,
  Role, SessionOut, Usage, UserAdminOut, MeasurementIn, MeasurementOut, MonitoringSettings, PumpCalc, DesignParamUpdate, DesignProfile, EngineInfo,
  FeasibilityRequest, FeasibilityResult, FireResult, Gcp, GcpFit, ImportApplyResult, ImportPreview, ImportResult,
  NetworkDocument, NetworkSave, NetworkSaveResult, OrthophotoOut, ProjectOut, QueryDef, QueryElement, QueryResult,
  SavedQueryOut, ScenarioResult, SearchHit, SectorsResult, SimulationBlocked, SimulationResult, ValidationReport, VersionOut,
  LeakEventIn, LeakEventOut, LeakImportResult, MapsStatus, SummaryResult, SummarySettings,
  GFilters, GTab, GestionSettings, OrgSettings, SystemInfo, RecordKind, RecordSpec, RecordImportPreview, TabResult, MaintenanceLogOut,
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
  401: "Su sesión expiró: vuelva a ingresar.",
  403: "Su rol no permite esta acción.",
  413: "El archivo o la solicitud supera el tamaño máximo permitido.",
  429: "Demasiadas solicitudes: espere un momento y reintente.",
};

/** Sin sesión (o con el segundo factor pendiente) se vuelve al ingreso; sin TOTP obligatorio, al perfil. */
function redirectAuth(status: number, body: unknown): void {
  const code = body && typeof body === "object" && "code" in body ? (body as { code: unknown }).code : null;
  const here = window.location.pathname;
  if (status === 401 && (code === "login_required" || code === "mfa_pending") && !/^\/(login|recuperar|invitacion)/.test(here)) {
    window.location.assign(`/login?volver=${encodeURIComponent(here + window.location.search)}`);
  } else if (status === 403 && code === "mfa_setup_required" && here !== "/ajustes/seguridad") {
    window.location.assign("/ajustes/seguridad?mfa=1");
  }
}

function fail(status: number, body: unknown): never {
  redirectAuth(status, body);
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

export interface GQuery { desde?: string; hasta?: string; sector?: string; ruta?: string }
function qs(q: object): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const t = p.toString();
  return t ? `?${t}` : "";
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
  // ── Sesión, perfil, organizaciones y plataforma ──
  authStatus: () => unwrap<AuthStatus>(client.GET("/api/auth/status")),
  me: () => unwrap<Me>(client.GET("/api/auth/me")),
  updateMe: (name: string) => unwrap<Me>(client.PATCH("/api/auth/me", { body: { name } })),
  orgSettings: (org: string) => unwrap<OrgSettings>(client.GET("/api/orgs/{org_id}/settings", { params: { path: { org_id: org } } })),
  saveOrgSettings: (org: string, body: OrgSettings) =>
    unwrap<OrgSettings>(client.PUT("/api/orgs/{org_id}/settings", { params: { path: { org_id: org } }, body })),
  adminSystem: () => unwrap<SystemInfo>(client.GET("/api/admin/system")),
  login: (email: string, password: string) =>
    unwrap<{ mfa_required: boolean }>(client.POST("/api/auth/login", { body: { email, password } })),
  mfa: (code: string) => unwrap<unknown>(client.POST("/api/auth/mfa", { body: { code } })),
  logout: () => unwrap<unknown>(client.POST("/api/auth/logout")),
  logoutAll: () => unwrap<unknown>(client.POST("/api/auth/logout-all")),
  switchOrg: (org_id: string) => unwrap<unknown>(client.POST("/api/auth/org", { body: { org_id } })),
  changePassword: (current_password: string, new_password: string) =>
    unwrap<unknown>(client.POST("/api/auth/password", { body: { current_password, new_password } })),
  mfaSetup: () => unwrap<MfaSetup>(client.POST("/api/auth/mfa/setup")),
  mfaEnable: (code: string) => unwrap<unknown>(client.POST("/api/auth/mfa/enable", { body: { code } })),
  mfaDisable: (password: string) => unwrap<unknown>(client.POST("/api/auth/mfa/disable", { body: { password } })),
  sessions: () => unwrap<SessionOut[]>(client.GET("/api/auth/sessions")),
  closeSession: (sid: string) => unwrap<unknown>(client.DELETE("/api/auth/sessions/{sid}", { params: { path: { sid } } })),
  recover: (email: string) => unwrap<{ email_enabled: boolean }>(client.POST("/api/auth/recover", { body: { email } })),
  resetPassword: (token: string, password: string) => unwrap<unknown>(client.POST("/api/auth/reset", { body: { token, password } })),
  invitation: (token: string) =>
    unwrap<InvitationInfo>(client.GET("/api/auth/invitation/{token}", { params: { path: { token } } })),
  acceptInvitation: (token: string, name: string, password: string) =>
    unwrap<unknown>(client.POST("/api/auth/invitation/{token}", { params: { path: { token } }, body: { name, password } })),
  members: (org: string) => unwrap<MemberOut[]>(client.GET("/api/orgs/{org_id}/members", { params: { path: { org_id: org } } })),
  invite: (org: string, email: string, role: Role, send_email: boolean) =>
    unwrap<{ link: string; emailed: boolean }>(client.POST("/api/orgs/{org_id}/invitations", {
      params: { path: { org_id: org } }, body: { email, role, send_email },
    })),
  updateMember: (org: string, user: string, body: { role?: Role; active?: boolean }) =>
    unwrap<MemberOut>(client.PATCH("/api/orgs/{org_id}/members/{user_id}", { params: { path: { org_id: org, user_id: user } }, body })),
  memberResetLink: (org: string, user: string) =>
    unwrap<{ link: string }>(client.POST("/api/orgs/{org_id}/members/{user_id}/reset-link", { params: { path: { org_id: org, user_id: user } } })),
  audit: (org: string, action?: string) =>
    unwrap<AuditOut[]>(client.GET("/api/orgs/{org_id}/audit", { params: { path: { org_id: org }, query: action ? { action } : {} } })),
  orgUsage: (org: string) => unwrap<Usage>(client.GET("/api/orgs/{org_id}/usage", { params: { path: { org_id: org } } })),
  mapLoad: () => unwrap<{ allowed: boolean; count: number; limit?: number | null }>(client.POST("/api/usage/map-load")),
  adminOrgs: () => unwrap<OrgAdminOut[]>(client.GET("/api/admin/orgs")),
  adminCreateOrg: (body: { name: string; kind?: "apr" | "consultora" | "sanitaria" | "otra"; plan?: "basico" | "profesional" | "ilimitado"; admin_email?: string | null }) =>
    unwrap<{ admin_invitation?: string | null }>(client.POST("/api/admin/orgs", { body: { kind: "apr", plan: "basico", ...body } })),
  adminUpdateOrg: (org: string, body: { plan?: "basico" | "profesional" | "ilimitado"; limits?: Record<string, number | null>; suspended?: boolean }) =>
    unwrap<unknown>(client.PATCH("/api/admin/orgs/{org_id}", { params: { path: { org_id: org } }, body })),
  adminUsers: () => unwrap<UserAdminOut[]>(client.GET("/api/admin/users")),
  adminUpdateUser: (user: string, active: boolean) =>
    unwrap<UserAdminOut>(client.PATCH("/api/admin/users/{user_id}", { params: { path: { user_id: user } }, body: { active } })),
  adminResetLink: (user: string) =>
    unwrap<{ link: string }>(client.POST("/api/admin/users/{user_id}/reset-link", { params: { path: { user_id: user } } })),
  reviews: (id: string, n: number) =>
    unwrap<ReviewOut[]>(client.GET("/api/projects/{project_id}/versions/{number}/reviews", { params: { path: { project_id: id, number: n } } })),
  addReview: (id: string, n: number, status: "comentario" | "aprobada" | "observada", comment: string) =>
    unwrap<ReviewOut>(client.POST("/api/projects/{project_id}/versions/{number}/reviews", {
      params: { path: { project_id: id, number: n } }, body: { status, comment },
    })),
  // ── Pozo, mediciones y diagnóstico ──
  pumpCalc: (id: string, well: string, conventions: "trazo" | "planilla" = "trazo") =>
    unwrap<PumpCalc>(client.GET("/api/projects/{project_id}/wells/{well_id}/pump", {
      params: { path: { project_id: id, well_id: well }, query: { conventions } },
    })),
  wellReportUrl: (id: string, well: string, conventions: "trazo" | "planilla" = "trazo") =>
    `/api/projects/${encodeURIComponent(id)}/wells/${encodeURIComponent(well)}/report.html?conventions=${conventions}`,
  applyWellCurve: (id: string, well: string) =>
    unwrap<{ version: number; pump: string; curve_points: [number, number][] }>(client.POST("/api/projects/{project_id}/wells/{well_id}/apply-curve", {
      params: { path: { project_id: id, well_id: well } },
    })),
  measurements: (id: string) =>
    unwrap<MeasurementOut[]>(client.GET("/api/projects/{project_id}/measurements", { params: { path: { project_id: id } } })),
  addMeasurements: (id: string, body: MeasurementIn[]) =>
    unwrap<MeasurementOut[]>(client.POST("/api/projects/{project_id}/measurements", { params: { path: { project_id: id } }, body })),
  deleteMeasurements: (id: string, ids: number[]) =>
    unwrap<unknown>(client.POST("/api/projects/{project_id}/measurements/delete", { params: { path: { project_id: id } }, body: { ids } })),
  importMeasurements: async (id: string, file: File): Promise<{ created: number; errors: string[] }> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/measurements/import`, { method: "POST", body: fd });
    const body = await res.json().catch(() => null);
    if (res.status === 422 && body && "errors" in body) return body;
    if (!res.ok) fail(res.status, body);
    return body;
  },
  mapsConfig: () => unwrap<{ provider?: "google" | "osm" | "auto"; api_key?: string | null; map_id?: string | null; source: "db" | "none" }>(client.GET("/api/maps/config")),
  mapsStatus: () => unwrap<MapsStatus>(client.GET("/api/admin/maps")),
  saveMaps: (body: { provider?: "google" | "osm" | "auto"; api_key?: string; map_id?: string }) => unwrap<MapsStatus>(client.PUT("/api/admin/maps", { body })),
  deleteMaps: () => unwrap<MapsStatus>(client.DELETE("/api/admin/maps")),
  summary: (id: string, q: { version?: number; scenario?: string; period?: number | null }) =>
    unwrap<SummaryResult>(client.GET("/api/projects/{project_id}/summary", {
      params: { path: { project_id: id }, query: { version: q.version, scenario: q.scenario, period: q.period ?? undefined } },
    })),
  summarySettings: (id: string) =>
    unwrap<SummarySettings>(client.GET("/api/projects/{project_id}/summary/settings", { params: { path: { project_id: id } } })),
  saveSummarySettings: (id: string, body: SummarySettings) =>
    unwrap<SummarySettings>(client.PUT("/api/projects/{project_id}/summary/settings", { params: { path: { project_id: id } }, body })),
  resetSummarySettings: (id: string) =>
    unwrap<SummarySettings>(client.DELETE("/api/projects/{project_id}/summary/settings", { params: { path: { project_id: id } } })),
  summaryUrl: (id: string, fmt: "xlsx" | "html", q: { scenario?: string; period?: number | null } = {}) => {
    const qs = new URLSearchParams();
    if (q.scenario) qs.set("scenario", q.scenario);
    if (q.period !== undefined && q.period !== null) qs.set("period", String(q.period));
    const t = qs.toString();
    return `/api/projects/${encodeURIComponent(id)}/summary.${fmt}${t ? `?${t}` : ""}`;
  },
  areaGeojsonUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/summary/area.geojson`,
  zonesGeojsonUrl: (id: string, q: { scenario?: string; period?: number | null } = {}) =>
    `/api/projects/${encodeURIComponent(id)}/summary/zones.geojson?scenario=${encodeURIComponent(q.scenario ?? "modelo")}${q.period != null ? `&period=${q.period}` : ""}`,
  addLeaks: (id: string, body: LeakEventIn[]) =>
    unwrap<LeakEventOut[]>(client.POST("/api/projects/{project_id}/leaks", { params: { path: { project_id: id } }, body })),
  deleteLeaks: (id: string, ids: number[]) =>
    unwrap<unknown>(client.POST("/api/projects/{project_id}/leaks/delete", { params: { path: { project_id: id } }, body: { ids } })),
  importLeaks: async (id: string, file: File): Promise<LeakImportResult> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/leaks/import`, { method: "POST", body: fd });
    const body = await res.json().catch(() => null);
    if (res.status === 422 && body && "errors" in body) return body;
    if (!res.ok) fail(res.status, body);
    return body;
  },
  leaksTemplateUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/leaks/template.xlsx`,
  measurementsTemplateUrl: (id: string) => `/api/projects/${encodeURIComponent(id)}/measurements/template.xlsx`,
  monitoring: (id: string) =>
    unwrap<MonitoringSettings>(client.GET("/api/projects/{project_id}/monitoring", { params: { path: { project_id: id } } })),
  saveMonitoring: (id: string, body: MonitoringSettings) =>
    unwrap<MonitoringSettings>(client.PUT("/api/projects/{project_id}/monitoring", { params: { path: { project_id: id } }, body })),
  compareMeasurements: (id: string) =>
    unwrap<MeasureCompare>(client.GET("/api/projects/{project_id}/measurements/compare", { params: { path: { project_id: id } } })),
  diagnosis: (id: string, version?: number) =>
    unwrap<DiagnosisResult>(client.GET("/api/projects/{project_id}/diagnosis", {
      params: { path: { project_id: id }, query: version ? { version } : {} },
    })),
  reportUrl: (id: string, version?: number) => `/api/projects/${encodeURIComponent(id)}/report.html${version ? `?version=${version}` : ""}`,
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
  trazoUrl: (id: string, orthos = false) => `/api/projects/${encodeURIComponent(id)}/export.trazo${orthos ? "?ortofotos=true" : ""}`,
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
  gcps: (id: string, oid: string, gcps: Gcp[], apply: boolean, save = false) =>
    unwrap<GcpFit>(client.POST("/api/projects/{project_id}/orthophotos/{ortho_id}/gcps", {
      params: { path: { project_id: id, ortho_id: oid } }, body: { gcps, apply, save },
    })),
  // ── Gestión ──
  gestionFilters: (id: string) => unwrap<GFilters>(client.GET("/api/projects/{project_id}/gestion/filters", { params: { path: { project_id: id } } })),
  gestionSettings: (id: string) => unwrap<GestionSettings>(client.GET("/api/projects/{project_id}/gestion/settings", { params: { path: { project_id: id } } })),
  saveGestionSettings: (id: string, body: GestionSettings) =>
    unwrap<GestionSettings>(client.PUT("/api/projects/{project_id}/gestion/settings", { params: { path: { project_id: id } }, body })),
  resetGestionSettings: (id: string) =>
    unwrap<GestionSettings>(client.DELETE("/api/projects/{project_id}/gestion/settings", { params: { path: { project_id: id } } })),
  gestionTab: (id: string, tab: GTab, q: GQuery) =>
    unwrap<TabResult>(client.GET("/api/projects/{project_id}/gestion/tabs/{tab}", { params: { path: { project_id: id, tab }, query: q } })),
  gestionTableUrl: (id: string, tab: GTab, key: string, fmt: "xlsx" | "csv", q: GQuery) =>
    `/api/projects/${encodeURIComponent(id)}/gestion/tabs/${tab}/tables/${encodeURIComponent(key)}.${fmt}${qs(q)}`,
  gestionReportUrl: (id: string, fmt: "html" | "xlsx", q: GQuery) => `/api/projects/${encodeURIComponent(id)}/gestion/report.${fmt}${qs(q)}`,
  recordSpecs: (id: string) => unwrap<RecordSpec[]>(client.GET("/api/projects/{project_id}/gestion/records", { params: { path: { project_id: id } } })),
  records: (id: string, kind: RecordKind, q: { desde?: string; hasta?: string } = {}) =>
    unwrap<{ kind: RecordKind; rows: Record<string, unknown>[] }>(client.GET("/api/projects/{project_id}/gestion/records/{kind}", {
      params: { path: { project_id: id, kind }, query: q } })),
  addRecords: (id: string, kind: RecordKind, rows: Record<string, unknown>[]) =>
    unwrap<{ rows: Record<string, unknown>[] }>(client.POST("/api/projects/{project_id}/gestion/records/{kind}", {
      params: { path: { project_id: id, kind } }, body: rows })),
  editRecord: (id: string, kind: RecordKind, rid: number, row: Record<string, unknown>) =>
    unwrap<{ rows: Record<string, unknown>[] }>(client.PUT("/api/projects/{project_id}/gestion/records/{kind}/{rid}", {
      params: { path: { project_id: id, kind, rid } }, body: row })),
  deleteRecords: (id: string, kind: RecordKind, ids: number[]) =>
    unwrap<unknown>(client.POST("/api/projects/{project_id}/gestion/records/{kind}/delete", { params: { path: { project_id: id, kind } }, body: { ids } })),
  completeTask: (id: string, rid: number, body: { done_on: string; by?: string | null; note?: string | null }) =>
    unwrap<{ rows: Record<string, unknown>[] }>(client.POST("/api/projects/{project_id}/gestion/records/mantenciones/{rid}/complete", {
      params: { path: { project_id: id, rid } }, body })),
  taskLogs: (id: string) => unwrap<MaintenanceLogOut[]>(client.GET("/api/projects/{project_id}/gestion/records/mantenciones/logs", {
    params: { path: { project_id: id } } })),
  recordTemplateUrl: (id: string, kind: RecordKind) => `/api/projects/${encodeURIComponent(id)}/gestion/records/${kind}/template.xlsx`,
  recordExportUrl: (id: string, kind: RecordKind, fmt: "xlsx" | "csv") => `/api/projects/${encodeURIComponent(id)}/gestion/records/${kind}/export.${fmt}`,
  importRecords: async (id: string, kind: RecordKind, file: File, apply: boolean, onlyValid = false): Promise<RecordImportPreview> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/gestion/records/${kind}/import?apply=${apply}&only_valid=${onlyValid}`,
      { method: "POST", body: fd });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 422 && body && typeof body === "object" && "rows" in body) return body as RecordImportPreview;
      fail(res.status, body);
    }
    return body as RecordImportPreview;
  },
  exportUrl: (id: string, version?: number) =>
    `/api/projects/${encodeURIComponent(id)}/export.inp${version ? `?version=${version}` : ""}`,
};

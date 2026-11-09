// Apertura de proyectos en el editor (compartida por el editor y el historial de versiones).
import { api } from "../api/client";
import { useEditor } from "./store";

export async function openProject(id: string, version?: number): Promise<void> {
  const st = useEditor.getState();
  const [project, doc] = await Promise.all([api.getProject(id), api.getNetwork(id, version)]);
  const { useAuth, canEdit } = await import("./auth");
  st.set({ readOnly: !canEdit(useAuth.getState().roleIn(project.org_id)) });
  st.loadDocument(project, doc);
  api.designParams(id).then((d) => useEditor.getState().set({ designParams: d.params })).catch(() => undefined);
  const { simulateVersion } = await import("./live");
  if ((doc.network.features ?? []).length) await simulateVersion(doc.version, useEditor.getState().revision).catch(() => undefined);
}

/** Mensaje legible de un error de la API (incluye los mensajes del motor al importar). */
export function errorText(e: unknown): string {
  const body = e && typeof e === "object" && "body" in e
    ? (e as { body: unknown }).body as { detail?: { engine_messages?: { message: string }[]; errors?: string[] }; validation?: { errors?: { message: string }[] } } | null : null;
  const engine = body?.detail?.engine_messages?.map((m) => m.message).join(" ");
  const listed = body?.detail?.errors?.slice(0, 3).join(" ");
  const blocked = body?.validation?.errors?.slice(0, 3).map((x) => x.message).join(" ");
  return engine || listed || (blocked ? `La red tiene errores bloqueantes: ${blocked}` : "") || (e instanceof Error ? e.message : "Error inesperado");
}

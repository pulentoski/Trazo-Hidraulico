// Alias de los tipos generados desde el esquema OpenAPI de la API (no editar schema.d.ts a mano).
import type { components } from "./schema";

type S = components["schemas"];
export type ProjectOut = S["ProjectOut"];
export type VersionOut = S["VersionOut"];
export type NetworkDocument = S["NetworkDocument"];
export type NetworkSave = S["NetworkSave"];
export type NetworkSaveResult = S["NetworkSaveResult"];
export type NodeFeature = S["NodeFeature"];
export type LinkFeature = S["LinkFeature"];
export type NodeProperties = S["NodeProperties"];
export type LinkProperties = S["LinkProperties"];
export type HydraulicOptions = S["HydraulicOptions"];
export type SimulationResult = S["SimulationResult"];
export type SimulationBlocked = S["SimulationBlocked"];
export type ValidationReport = S["ValidationReport"];
export type ValidationIssue = S["ValidationIssue"];
export type EngineMessage = S["EngineMessage"];
export type CriteriaAlert = S["CriteriaAlert"];
export type CatalogPipe = S["CatalogPipeOut"];
export type DesignProfile = S["DesignProfileOut"];
export type EngineInfo = S["EngineInfo"];
export type ImportResult = S["ImportResult"];
export type NodeKind = NodeProperties["kind"];
export type LinkKind = NonNullable<LinkProperties["kind"]>;
export type HeadlossFormula = NonNullable<HydraulicOptions["headloss"]>;

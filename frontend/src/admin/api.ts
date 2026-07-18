/**
 * Client API della modalità Admin. Costruito sopra `richiesta` (autenticazione
 * + sessione condivise con l'operatore). Qui la meccanica è visibile: workflow,
 * confidence, SQL, trace — l'admin governa il sistema (§3.9).
 */

import { richiesta, richiestaBlob } from "../shared/api";

export type Totali = {
  n_fatture: number;
  totale: number;
  imponibile: number;
  iva: number;
  ritenute: number;
  da_validare: number;
};

export type CostoCantiere = {
  cantiere_id: string;
  cantiere: string | null;
  budget: number | null;
  n_fatture: number;
  speso: number;
  residuo: number | null;
  quota_budget: number | null;
};

export type CostoFornitore = {
  fornitore_id: string | null;
  fornitore: string | null;
  n_fatture: number;
  speso: number;
};

export type Cruscotto = {
  totali: Totali;
  per_cantiere: CostoCantiere[];
  per_fornitore: CostoFornitore[];
};

export type RigaCoda = {
  id: string;
  fornitore: string | null;
  cantiere: string | null;
  totale: number | null;
  data: string | null;
  confidence_min: number | null;
  creato: string | null;
};

export type Envelope = {
  id: string;
  tipo: string;
  stato: string;
  dati: Record<string, unknown>;
  meta: Record<string, unknown>;
};

export type FeedbackCampo = { campo: string; nota: string; utente: string; ts: string };

export type Revisione = {
  entita: Envelope;
  tipo: string;
  confidence: Record<string, number>;
  blob: string | null;
  run_id: string | null;
  documento_id: string | null;
  feedback: FeedbackCampo[];
  issue: Record<string, unknown> | null;
  validato: boolean;
};

export type Issue = {
  id: string;
  origine: "auto" | "operatore";
  testo: string;
  stato: "aperta" | "chiusa";
  created: string;
  run_id: string | null;
  doc: string | null;
  entity_id: string | null;
  entita: { tipo: string; id: string; stato: string; totale?: number; fornitore?: string } | null;
};

export type StatRun = { totale: number; ok: number; errore: number };

export type Workflow = {
  name: string;
  version: string;
  tier: string | null;
  steps: string[];
  confidence_threshold: number | null;
  stats: StatRun;
  golden: number;
};

export type EventoTrace = Record<string, unknown> & { evento: string; ts?: string };

export type EsitoAsk = { sql: string; rows: Record<string, unknown>[] };

export type RigaReplay = {
  golden_id: string;
  doc: string;
  uguale: boolean;
  differenze: string[];
  nota?: string | null;
};

export type Patch = {
  id: string;
  workflow: string;
  da_versione: string;
  a_versione: string;
  stato: "proposta" | "approvata" | "rifiutata";
  analisi: string;
  motivazione: string;
  file_skill: string;
  diff_skill: string;
  diff_manifest: string | null;
  origine: Record<string, unknown>;
  replay: { totale: number; ok: number; casi: RigaReplay[] };
  creato: string | null;
  deciso_da: string | null;
};

export type EsitoApprovazione = {
  patch: Patch;
  versione: string;
  rerun: { run_id: string; entity_id: string | null; esito: string; ritenuta?: number | null } | null;
};

export type DatasetStats = {
  run: { totale: number; ok: number; errore: number };
  llm_call: number;
  tool_call: number;
  toolcalls_dataset: number;
  costo_totale_usd: number;
  documenti: number;
  costo_per_documento_usd: number;
  run_per_workflow: Record<string, number>;
};

export type GruppoQuery = { fingerprint: string; conteggio: number; esempio: string };

export const admin = {
  cruscotto: () => richiesta<Cruscotto>("/dashboard/costs"),

  codaRevisione: () =>
    richiesta<{ da_rivedere: RigaCoda[] }>("/review").then((r) => r.da_rivedere),

  revisione: (id: string) => richiesta<Revisione>(`/review/${id}`),

  originale: (id: string) =>
    richiestaBlob(`/review/${id}/originale`).then((b) => URL.createObjectURL(b)),

  feedback: (id: string, campo: string, nota: string) =>
    richiesta(`/review/${id}/feedback`, corpo({ campo, nota })).then(() => undefined),

  valida: (id: string) =>
    richiesta<{ stato: string; golden_id: string | null }>(
      `/review/${id}/validate`,
      corpo({}),
    ),

  issues: (stato?: "aperta" | "chiusa") =>
    richiesta<{ issues: Issue[] }>(`/issues${stato ? `?stato=${stato}` : ""}`).then(
      (r) => r.issues,
    ),

  chiudiIssue: (id: string) =>
    richiesta<{ stato: string }>(`/issues/${id}/close`, corpo({})),

  workflows: () =>
    richiesta<{ workflows: Workflow[] }>("/workflows").then((r) => r.workflows),

  trace: (runId: string) =>
    richiesta<{ eventi: EventoTrace[] }>(`/runs/${runId}/trace`).then((r) => r.eventi),

  chiediSql: (question: string) =>
    richiesta<EsitoAsk>("/ask", corpo({ question, mode: "admin" })),

  patches: (stato?: string) =>
    richiesta<{ patches: Patch[] }>(`/patches${stato ? `?stato=${stato}` : ""}`).then(
      (r) => r.patches,
    ),

  migliora: (workflow: string, body: { run_id?: string; issue_id?: string }) =>
    richiesta<Patch>(`/workflows/${workflow}/improve`, corpo(body)),

  approva: (id: string) =>
    richiesta<EsitoApprovazione>(`/patches/${id}/approve`, corpo({})),

  rifiuta: (id: string) =>
    richiesta<{ stato: string }>(`/patches/${id}/reject`, corpo({})),

  datasetStats: () => richiesta<DatasetStats>("/dataset/stats"),

  datasetQueries: () =>
    richiesta<{ gruppi: GruppoQuery[] }>("/dataset/queries").then((r) => r.gruppi),

  scaricaToolcalls: () => richiestaBlob("/dataset/export"),
};

function corpo(dati: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dati),
  };
}

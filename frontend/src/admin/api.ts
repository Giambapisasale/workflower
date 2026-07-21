/**
 * Client API della modalità Admin. Costruito sopra `richiesta` (autenticazione
 * + sessione condivise con l'operatore). Qui la meccanica è visibile: workflow,
 * confidence, SQL, trace — l'admin governa il sistema (§3.9).
 */

import { richiesta, richiestaBlob, scaricaFile } from "../shared/api";

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

export type Attivita = {
  n_ddt: number;
  n_sal: number;
  ore_totali: number;
  costo_manodopera: number;
};

export type Cruscotto = {
  totali: Totali;
  attivita: Attivita;
  per_cantiere: CostoCantiere[];
  per_fornitore: CostoFornitore[];
};

export type RegistroTotali = {
  speso_fatture: number;
  n_fatture: number;
  budget: number | null;
  quota_budget: number | null;
  ore_totali: number;
  costo_manodopera: number;
  giornate: number;
  avanzamento: number | null;
  scostamento: { previsto: number; consuntivo_abbinato: number; delta: number } | null;
};

export type RegistroCantiere = {
  cantiere: Record<string, unknown>;
  totali: RegistroTotali;
  fatture: { id: string; numero: string | null; data: string | null; totale: number | null; stato: string; fornitore: string | null }[];
  ddt: { id: string; numero: string | null; data: string | null; n_righe: number; stato: string; fornitore: string | null }[];
  sal: { id: string; numero: string | null; data: string | null; importo_progressivo: number | null; percentuale_avanzamento: number | null; stato: string }[];
};

export type RigaCoda = {
  id: string;
  tipo: string;
  fornitore: string | null;
  cantiere: string | null;
  totale: number | null;
  data: string | null;
  confidence_min: number | null;
  creato: string | null;
};

export const ETICHETTA_TIPO: Record<string, string> = {
  fattura: "Fattura",
  ddt: "DDT",
  sal: "SAL",
  rapportino: "Rapportino",
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
  esempi_finetuning: number;
};

export type VoceLog = {
  ts: string;
  livello: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  fase: string;
  logger: string;
  messaggio: string;
  run_id?: string;
  workflow?: string;
  step?: string;
  documento?: string;
  utente?: string;
  dettagli?: unknown;
  eccezione?: string;
};

export type ElencoLog = { voci: VoceLog[]; fasi: string[]; livelli: string[] };

export type StatsLog = {
  totale: number;
  errori: number;
  giorni: number;
  per_livello: Record<string, number>;
  per_fase: Record<string, number>;
};

export type ConfigLog = { livello: string; livelli: string[] };

export type FiltroLog = {
  livello?: string;
  fase?: string;
  q?: string;
  giorni?: number;
  limite?: number;
};

export type GruppoQuery = {
  fingerprint: string;
  conteggio: number;
  esempio: string;
  consolidato?: string | null; // nome dell'artefatto (v_* o t_*) se già consolidato
  letterali: string[]; // letterali dell'esempio, candidati a diventare parametri di un tool
};

export type ToolRegistry = { name: string; descrizione: string; usi: number; ciclo: string };

export type VistaConsolidata = {
  creato: string;
  nome: string;
  vista: string;
  fingerprint: string;
  corpo: string;
  esempio: string;
  creato_da: string;
};

export type ToolParametrico = {
  creato: string;
  nome: string;
  macro: string; // t_<nome>
  parametri: string[];
  fingerprint: string;
  corpo: string;
  esempio: string;
  creato_da: string;
};

export type SkillsTools = {
  tools: ToolRegistry[];
  candidati: GruppoQuery[];
  viste: VistaConsolidata[];
  macro: ToolParametrico[];
};

export type ScostamentoCantiere = {
  cantiere_id: string;
  cantiere: string | null;
  previsto: number;
  consuntivo: number;
  delta: number;
};

export type ScostamentoVoce = {
  cantiere_id: string;
  voce_id: string;
  codice: string | null;
  descrizione: string;
  categoria: string | null;
  previsto: number;
  consuntivo: number;
  delta: number;
  quota: number | null;
};

export type Scostamenti = { per_cantiere: ScostamentoCantiere[]; voci: ScostamentoVoce[] };

export type EsitoCollega = {
  abbinate: number;
  totali: number;
  senza_computo?: boolean;
  dettaglio: { riga: number; voce_id: string | null; punteggio: number }[];
};

/** Schema JSON (sottoinsieme che ci serve per generare i form). */
export type JsonSchema = {
  type?: string | string[];
  title?: string;
  description?: string;
  format?: string;
  pattern?: string;
  enum?: unknown[];
  minimum?: number;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
};

/** Un tipo entità gestibile a mano, con il suo schema per il form generico. */
export type MetaTipo = {
  tipo: string;
  etichetta: string;
  is_master: boolean;
  per_anno: boolean;
  schema: JsonSchema;
  riferimenti: Record<string, string>; // campo → tipo referenziato
};

export type VoceEntita = {
  id: string;
  stato: string;
  titolo: string | null;
  dati: Record<string, unknown>;
};

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

  registro: (cantiereId: string) =>
    richiesta<RegistroCantiere>(`/cantieri/${cantiereId}/registro`),

  scaricaReport: (cantiereId?: string) =>
    scaricaFile(
      `/reports/mensile.xlsx${cantiereId ? `?cantiere_id=${cantiereId}` : ""}`,
      `report-${cantiereId ?? "tutti"}.xlsx`,
    ),

  scostamenti: (cantiereId?: string) =>
    richiesta<Scostamenti>(
      `/dashboard/scostamenti${cantiereId ? `?cantiere_id=${cantiereId}` : ""}`,
    ),

  collega: (id: string) => richiesta<EsitoCollega>(`/review/${id}/collega`, corpo({})),

  datasetStats: () => richiesta<DatasetStats>("/dataset/stats"),

  datasetQueries: () =>
    richiesta<{ gruppi: GruppoQuery[] }>("/dataset/queries").then((r) => r.gruppi),

  scaricaToolcalls: () => richiestaBlob("/dataset/export"),

  skillsTools: () => richiesta<SkillsTools>("/tools"),

  consolida: (fingerprint: string, nome: string) =>
    richiesta<{ vista: string; corpo: string; righe: number; creato: string }>(
      "/dataset/consolida",
      corpo({ fingerprint, nome }),
    ),

  consolidaTool: (
    fingerprint: string,
    nome: string,
    parametri: { valore: string; nome: string }[],
  ) =>
    richiesta<{ macro: string; corpo: string; parametri: string[]; righe: number; creato: string }>(
      "/dataset/consolida-tool",
      corpo({ fingerprint, nome, parametri }),
    ),

  eliminaTool: (macro: string) =>
    richiesta<{ rimosso: string }>(`/dataset/tool/${encodeURIComponent(macro)}`, {
      method: "DELETE",
    }),

  eliminaVista: (vista: string) =>
    richiesta<{ rimosso: string }>(`/dataset/vista/${encodeURIComponent(vista)}`, {
      method: "DELETE",
    }),

  scaricaFinetuning: () => scaricaFile("/dataset/finetuning.jsonl", "finetuning.jsonl"),

  // Diagnostica (logbook): elenco filtrabile, statistiche, livello a runtime.
  logs: (filtro: FiltroLog = {}) => {
    const q = new URLSearchParams();
    if (filtro.livello) q.set("livello", filtro.livello);
    if (filtro.fase) q.set("fase", filtro.fase);
    if (filtro.q) q.set("q", filtro.q);
    if (filtro.giorni) q.set("giorni", String(filtro.giorni));
    if (filtro.limite) q.set("limite", String(filtro.limite));
    const qs = q.toString();
    return richiesta<ElencoLog>(`/logs${qs ? `?${qs}` : ""}`);
  },

  logStats: (giorni = 7) => richiesta<StatsLog>(`/logs/stats?giorni=${giorni}`),

  logConfig: () => richiesta<ConfigLog>("/logs/config"),

  impostaLogLivello: (livello: string) =>
    richiesta<ConfigLog>("/logs/config", metodoJson("PUT", { livello })),

  scaricaLog: () => scaricaFile("/logs/export", "log-oggi.jsonl"),

  // Gestione manuale dei dati (M13): CRUD generico guidato dagli schemi.
  entitiesMeta: () => richiesta<{ tipi: MetaTipo[] }>("/entities/meta").then((r) => r.tipi),

  entitiesLista: (tipo: string) =>
    richiesta<{ voci: VoceEntita[] }>(`/entities/${tipo}`).then((r) => r.voci),

  entitiesGet: (tipo: string, id: string) => richiesta<Envelope>(`/entities/${tipo}/${id}`),

  entitiesCrea: (tipo: string, dati: Record<string, unknown>) =>
    richiesta<{ id: string; stato: string }>(`/entities/${tipo}`, corpo({ dati })),

  entitiesAggiorna: (tipo: string, id: string, dati: Record<string, unknown>) =>
    richiesta<{ id: string; stato: string }>(
      `/entities/${tipo}/${id}`,
      metodoJson("PUT", { dati }),
    ),

  entitiesElimina: (tipo: string, id: string) =>
    richiesta<{ ok: boolean }>(`/entities/${tipo}/${id}`, metodoJson("DELETE")),
};

function corpo(dati: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dati),
  };
}

function metodoJson(metodo: string, dati?: unknown): RequestInit {
  return {
    method: metodo,
    headers: dati === undefined ? {} : { "Content-Type": "application/json" },
    body: dati === undefined ? undefined : JSON.stringify(dati),
  };
}

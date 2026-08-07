/**
 * Client API della modalità Admin. Costruito sopra `richiesta` (autenticazione
 * + sessione condivise con l'operatore). Qui la meccanica è visibile: workflow,
 * confidence, trace e strumenti — l'admin governa il sistema (§3.9).
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
  costo_mezzi: number;
};

export type ScadenzaImminente = {
  id: string;
  descrizione: string;
  data_scadenza: string;
  tipo: string | null;
  cantiere_id: string | null;
  cantiere: string | null;
  mezzo_id: string | null;
  mezzo: string | null;
  giorni: number;
};

export type Cruscotto = {
  totali: Totali;
  attivita: Attivita;
  per_cantiere: CostoCantiere[];
  per_fornitore: CostoFornitore[];
  scadenze: ScadenzaImminente[];
};

export type RegistroTotali = {
  speso_fatture: number;
  n_fatture: number;
  budget: number | null;
  quota_budget: number | null;
  ore_totali: number;
  costo_manodopera: number;
  costo_mezzi: number | null;
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

/** Un'esecuzione riassunta (elenco Run): il trace completo si carica a parte. */
export type RigaRun = {
  run_id: string;
  workflow: string | null;
  version: string | null;
  input: string | null;
  ts: string | null;
  esito: string;
  entity_id: string | null;
  errore: string | null;
  costo_usd: number;
  tokens: number;
  durata_ms: number;
  n_llm: number;
  n_tool: number;
  escalation: number;
};

/** Un caso golden ha **due forme** e l'elenco le mescola (backend: core/golden.py):
 *  un caso-`documento` ha `doc` (il blob da rieseguire), un caso storico ha
 *  solo `domanda` e lascia vuoti `doc`/`entity_tipo`/`entity_id`.
 *  I nullable qui non sono prudenza: nei dati reali sono la maggior parte. */
export type CasoGolden = {
  id: string;
  tipo: "documento" | "legacy_sql";
  workflow: string;
  version: string;
  doc: string | null;
  domanda: string | null;
  entity_tipo: string | null;
  entity_id: string | null;
  run_id: string | null;
  validato_da: string | null;
  creato: string | null;
  n_campi: number;
  originale_presente: boolean;
};

export type Scartato = {
  id: string;
  tipo: string;
  etichetta: string;
  titolo: string | null;
  motivo: string | null;
  scartato_da: string | null;
  scartato_il: string | null;
  era_validato: boolean;
  erp_id: string | null;
};

/** Un campo che l'ufficio corregge spesso: dove vale la pena un tool. */
export type CandidatoToolsmith = {
  workflow: string | null;
  tipo: string | null;
  campo: string;
  occorrenze: number;
  valori: unknown[];
};

export type CasoTest = {
  argomenti: Record<string, unknown>;
  atteso: Record<string, unknown>;
  ottenuto?: Record<string, unknown> | null;
  ok?: boolean;
  errore?: string;
};

export type PropostaTool = {
  id: string;
  nome: string;
  candidato: {
    nome: string;
    tipo: string;
    campi_input: string[];
    campo_output: string;
    workflow: string | null;
  };
  codice: string;
  schema: Record<string, unknown>;
  test: CasoTest[];
  esito_test: { totale: number; ok: number; casi: CasoTest[] };
  esempi: number;
  stato: "proposta" | "approvata" | "rifiutata";
  creato: string | null;
  deciso_da: string | null;
  pytool?: string | null;
  patch_skill?: string | null;
};

export type EsitoApprovaProposta = {
  proposta: string;
  stato: string;
  pytool: string;
  patch_skill: { id: string; replay: { totale: number; ok: number }; diff_skill: string } | null;
};

/** Idoneità di un modello locale (T3) misurata contro il tier di riferimento. */
export type QuotaT3 = { tool: number; args: number };

export type EvalT3 = {
  modello_candidato: string | null;
  modello_riferimento: string | null;
  tier_candidato: string;
  tier_riferimento: string;
  soglia: number;
  esempi: number;
  /** Esempi validati di cui non si è potuta ricostruire l'immagine originale. */
  non_rigiocabili: number;
  /** Prompt che il trace ha troncato: abbassano l'accuratezza assoluta di entrambi i tier. */
  prompt_troncati: number;
  /** Falso se `LLM_T3_MODEL` non è impostato: T3 ricade su T1 e la misura si confronta con sé. */
  t3_configurato: boolean;
  totale: { candidato: QuotaT3; riferimento: QuotaT3 };
  workflow: Record<
    string,
    {
      esempi: number;
      candidato: QuotaT3;
      riferimento: QuotaT3;
      regressione: boolean;
      pronto_per_t3: boolean;
    }
  >;
  pronti: string[];
  regressioni: string[];
  agente_dati?: {
    casi: number;
    candidato: QuotaT3 & { result?: number };
    riferimento: QuotaT3 & { result?: number };
    regressione: boolean;
    pronto_per_t3: boolean;
  };
};

export type MessaggioAgente = { role: "user" | "assistant"; content: string; run_id?: string };
export type ConversazioneAgente = { messages: MessaggioAgente[]; max_messages: number };
export type EsitoAgente = ConversazioneAgente & {
  answer: string;
  run_id: string;
  used_tools: string[];
  sources: { tool: string; source: string }[];
};
export type PropostaAgente = {
  id: string;
  stato: "proposta" | "approvata" | "rifiutata";
  feedback: string;
  analisi: string;
  motivazione: string;
  intenti?: string[];
  parametri?: unknown[];
  esempi?: string[];
  risultato_atteso?: string;
  tool?: Record<string, unknown> | null;
  skill?: { name: string; content?: string } | null;
  compilazione?: { ok: boolean; righe?: number; minimo?: number; errore?: string };
  replay: { totale: number; ok: number; falliti: number };
};
export type EvoluzioneAgente = {
  tools: { name: string; description: string; roles?: string[]; scope?: string }[];
  proposals: PropostaAgente[];
};

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

export type AzioneSuggerita = {
  tipo: "improver" | "modifica_dato" | "nessuna" | string;
  workflow: string | null;
  dettaglio: string;
};

export type SorgenteLetta = { file: string; lineno?: number; estratto: string };

export type Diagnosi = {
  id: string;
  firma: string;
  stato: "proposta" | "risolta" | "archiviata";
  deciso_da: string | null;
  fase: string | null;
  livello: string | null;
  messaggio: string | null;
  run_id: string | null;
  workflow: string | null;
  documento: string | null;
  n_occorrenze: number;
  prima_occorrenza: string | null;
  ultima_occorrenza: string | null;
  categoria: "dato" | "architettura";
  titolo: string;
  analisi: string;
  causa_radice: string;
  proposta: string;
  azione_suggerita: AzioneSuggerita;
  file_coinvolti: string[];
  confidenza: number;
  eccezione?: string | null;
  campione?: VoceLog[];
  sorgenti_lette: SorgenteLetta[];
  creato: string | null;
};

export type GruppoQuery = {
  fingerprint: string;
  conteggio: number;
  esempio: string;
  consolidato?: string | null; // nome dell'artefatto (v_* o t_*) se già consolidato
  letterali: string[]; // letterali dell'esempio, candidati a diventare parametri di un tool
};

export type ToolRegistry = {
  name: string;
  descrizione: string;
  usi: number;
  ciclo: string;
  /** "nativa" = inclusa nell'app; "pytool" = consolidata dal Toolsmith (rimovibile). */
  origine?: string;
};

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

export type SkillsTools = { tools: ToolRegistry[] };

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

/** Un tentativo di sincronizzazione ERP dal ledger `dataset/erp_sync.jsonl`. */
export type ErpTentativo = {
  ts: string;
  entity_id: string;
  esito: string; // "ok" | "errore"
  erp_id: string | null;
  errore: string | null;
  run_id: string | null;
};

export type ErpContatori = {
  validate: number;
  sincronizzate: number;
  da_sincronizzare: number;
};

/** Stato dell'integrazione ERP (M28): contatori, arretrati, ultimi tentativi. */
export type ErpStato = {
  erp_attivo: boolean;
  per_tipo: Record<string, ErpContatori>;
  da_sincronizzare: { id: string; tipo: string }[];
  ultimi_tentativi: ErpTentativo[];
};

export type ErpEsitoBatch = {
  esito: string;
  tentate: number;
  ok: number;
  errori: number;
  saltate?: number; // es. rapportini di soli terzi: non inviati e non in errore
  interrotto: boolean;
};

export type ErpEsitoSingolo = {
  esito: string;
  erp_id?: string;
  doctype?: string;
  errore?: string;
  motivo?: string;
};

export type ErpEsitoPagamenti = {
  esito: string;
  creati: number;
  aggiornati: number;
  errori: number;
};

/** Contatori del carico anagrafiche (M31), per tipo entità. */
export type ErpContatoriAnagrafiche = {
  inviate: number;
  gia_allineate: number;
  saltate: number;
  errori: number;
};

export type ErpEsitoAnagrafiche = {
  esito: string; // "ok" | "erp_non_configurato"
  per_tipo: Record<string, ErpContatoriAnagrafiche>;
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

export type DatiAzienda = {
  denominazione: string;
  indirizzo: string;
  partita_iva: string;
};

/** `configurata` la calcola il backend: qui non si duplica quella regola. */
export type Azienda = DatiAzienda & { configurata: boolean };

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

  // Run: le esecuzioni riassunte, porta d'ingresso ai trace.
  run: (filtro: { workflow?: string; esito?: string; limite?: number } = {}) => {
    const q = new URLSearchParams();
    if (filtro.workflow) q.set("workflow", filtro.workflow);
    if (filtro.esito) q.set("esito", filtro.esito);
    if (filtro.limite) q.set("limite", String(filtro.limite));
    const qs = q.toString();
    return richiesta<{ run: RigaRun[] }>(`/runs${qs ? `?${qs}` : ""}`).then((r) => r.run);
  },

  // Golden set: la rete di regressione dell'Improver, ispezionabile e correggibile.
  golden: (workflow?: string) =>
    richiesta<{ golden: CasoGolden[] }>(
      `/golden${workflow ? `?workflow=${encodeURIComponent(workflow)}` : ""}`,
    ).then((r) => r.golden),

  eliminaGolden: (id: string) =>
    richiesta<{ rimosso: string }>(`/golden/${encodeURIComponent(id)}`, metodoJson("DELETE")),

  // Scarto di un inserimento sbagliato, e ripristino.
  scarta: (id: string, motivo: string) =>
    richiesta<{ stato: string; golden_rimossi: string[]; segnalazioni_chiuse: string[] }>(
      `/review/${id}/scarta`,
      corpo({ motivo }),
    ),

  scartati: () => richiesta<{ scartati: Scartato[] }>("/scartati").then((r) => r.scartati),

  ripristina: (id: string) =>
    richiesta<{ id: string; stato: string }>(`/scartati/${id}/ripristina`, metodoJson("POST")),

  // Toolsmith (F3): consolidamento di un calcolo ricorrente in un tool Python.
  toolsmithCandidati: () =>
    richiesta<{ candidati: CandidatoToolsmith[] }>("/toolsmith/candidati").then(
      (r) => r.candidati,
    ),

  toolsmithProponi: (body: {
    nome: string;
    tipo: string;
    campi_input: string[];
    campo_output: string;
    workflow?: string | null;
  }) => richiesta<PropostaTool>("/toolsmith/proponi", corpo(body)),

  toolsmithProposte: () =>
    richiesta<{ proposte: PropostaTool[] }>("/toolsmith/proposte").then((r) => r.proposte),

  toolsmithApprova: (id: string) =>
    richiesta<EsitoApprovaProposta>(`/toolsmith/proposte/${id}/approve`, metodoJson("POST")),

  toolsmithRifiuta: (id: string) =>
    richiesta<{ id: string; stato: string }>(
      `/toolsmith/proposte/${id}/reject`,
      metodoJson("POST"),
    ),

  eliminaPytool: (nome: string) =>
    richiesta<{ rimosso: string }>(`/dataset/pytool/${encodeURIComponent(nome)}`, {
      method: "DELETE",
    }),

  // Idoneità T3: misura sul set validato. Costa token — solo su richiesta esplicita.
  evalT3: () => richiesta<EvalT3>("/dataset/eval-t3"),

  conversazioneAgente: () => richiesta<ConversazioneAgente>("/agent/conversation"),

  messaggioAgente: (content: string) =>
    richiesta<EsitoAgente>("/agent/messages", corpo({ content })),

  resetConversazioneAgente: () =>
    richiesta<ConversazioneAgente>("/agent/conversation/reset", corpo({})),

  configurazioneAgente: () => richiesta<{ max_messages: number }>("/agent/config"),

  salvaConfigurazioneAgente: (max_messages: number) =>
    richiesta<{ max_messages: number }>("/agent/config", metodoJson("PUT", { max_messages })),

  evoluzioneAgente: () => richiesta<EvoluzioneAgente>("/agent/evolution"),

  proponiEvoluzioneAgente: (feedback: string) =>
    richiesta<PropostaAgente>("/agent/evolution/proposals", corpo({ feedback })),

  approvaEvoluzioneAgente: (id: string) =>
    richiesta<PropostaAgente>(`/agent/evolution/proposals/${id}/approve`, corpo({})),

  rifiutaEvoluzioneAgente: (id: string) =>
    richiesta<PropostaAgente>(`/agent/evolution/proposals/${id}/reject`, corpo({})),

  patches: (stato?: string) =>
    richiesta<{ patches: Patch[] }>(`/patches${stato ? `?stato=${stato}` : ""}`).then(
      (r) => r.patches,
    ),

  migliora: (workflow: string, body: { run_id?: string; issue_id?: string; feedback?: string }) =>
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

  skillsTools: () => richiesta<SkillsTools>("/tools"),

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

  // Diagnosi: analisi automatica degli errori con proposta di risoluzione.
  diagnosi: (stato?: string) =>
    richiesta<{ diagnosi: Diagnosi[] }>(`/diagnoses${stato ? `?stato=${stato}` : ""}`).then(
      (r) => r.diagnosi,
    ),

  diagnosiDettaglio: (id: string) => richiesta<Diagnosi>(`/diagnoses/${id}`),

  analizzaErrori: (giorni = 1) =>
    richiesta<{ analizzate: number; diagnosi: Diagnosi[] }>(
      "/diagnoses/analyze",
      metodoJson("POST", { giorni }),
    ),

  risolviDiagnosi: (id: string) =>
    richiesta<Diagnosi>(`/diagnoses/${id}/resolve`, metodoJson("POST")),

  archiviaDiagnosi: (id: string) =>
    richiesta<Diagnosi>(`/diagnoses/${id}/archive`, metodoJson("POST")),

  // Integrazione ERP (M28): registro delle sincronizzazioni e recupero manuale.
  erpStato: () => richiesta<ErpStato>("/erp/stato"),

  erpRisincronizza: () => richiesta<ErpEsitoBatch>("/erp/risincronizza", metodoJson("POST")),

  erpRisincronizzaUno: (entityId: string) =>
    richiesta<ErpEsitoSingolo>(`/erp/risincronizza/${entityId}`, metodoJson("POST")),

  erpRileggiPagamenti: () =>
    richiesta<ErpEsitoPagamenti>("/erp/rileggi-pagamenti", metodoJson("POST")),

  erpCaricaAnagrafiche: () =>
    richiesta<ErpEsitoAnagrafiche>("/erp/carica-anagrafiche", metodoJson("POST")),

  // L'azienda che usa il sistema: il riferimento per riconoscere i documenti
  // intestati a noi. Dato in data/config/azienda.json, non variabile d'ambiente.
  azienda: () => richiesta<Azienda>("/config/azienda"),

  salvaAzienda: (dati: DatiAzienda) =>
    richiesta<Azienda>("/config/azienda", metodoJson("PUT", dati)),

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

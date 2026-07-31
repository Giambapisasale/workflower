/** Run: le esecuzioni dei workflow, con il trace di ognuna.
 *
 * Prima esisteva solo `GET /runs/{id}/trace`: per aprire un trace bisognava già
 * conoscere il run, e l'unica scorciatoia era una segnalazione. Le esecuzioni
 * andate male senza che nessuno segnalasse erano invisibili — e sono proprio
 * quelle che si vogliono vedere. */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { admin, type RigaRun } from "./api";
import { useCarica } from "./formato";
import TracePanel from "./TracePanel";
import { Badge, Bottone, Card, Errore, Kpi, LinkVerso, Stato } from "./ui";

const ESITI = [
  { valore: "", etichetta: "Tutti" },
  { valore: "ok", etichetta: "Riusciti" },
  { valore: "errore", etichetta: "Falliti" },
  { valore: "in_corso", etichetta: "In corso" },
];

const CLASSE_SELECT = "rounded-lg border border-slate-300 px-3 py-2 text-sm";

function tonoEsito(esito: string): string {
  return esito === "ok" ? "verde" : esito === "errore" ? "rosso" : "giallo";
}

function durata(ms: number): string {
  if (!ms) return "—";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function costo(usd: number): string {
  if (!usd) return "—";
  return `${usd.toFixed(4)} $`;
}

function quando(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("it-IT");
}

/** "blobs/caricati/2026/ab12cd-fattura.pdf" → "fattura.pdf" */
function documento(input: string | null): string {
  if (!input) return "—";
  const nome = input.split("/").pop() ?? input;
  const trattino = nome.indexOf("-");
  return trattino > 0 && trattino <= 9 ? nome.slice(trattino + 1) : nome;
}

export default function Run() {
  const [parametri, setParametri] = useSearchParams();
  const workflow = parametri.get("workflow") ?? "";
  const esito = parametri.get("esito") ?? "";
  const [aperto, setAperto] = useState<string | null>(null);

  const { dati, errore, inCorso, ricarica } = useCarica(
    () => admin.run({ workflow: workflow || undefined, esito: esito || undefined, limite: 200 }),
    [workflow, esito],
  );
  const elencoWorkflow = useCarica(() => admin.workflows());

  function imposta(chiave: string, valore: string) {
    const nuovi = new URLSearchParams(parametri);
    if (valore) nuovi.set(chiave, valore);
    else nuovi.delete(chiave);
    setParametri(nuovi, { replace: true });
  }

  if (inCorso) return <Stato>Carico i run…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const run = dati ?? [];
  const falliti = run.filter((r) => r.esito === "errore").length;
  const spesa = run.reduce((somma, r) => somma + r.costo_usd, 0);
  const escalation = run.reduce((somma, r) => somma + r.escalation, 0);

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi etichetta="Run mostrati" valore={run.length} />
        <Kpi etichetta="Falliti" valore={falliti} nota={falliti ? "guarda il trace" : "nessuno"} />
        <Kpi etichetta="Costo LLM" valore={costo(spesa)} nota="somma dei run mostrati" />
        <Kpi
          etichetta="Escalation"
          valore={escalation}
          nota="step rifatti su un tier superiore"
        />
      </div>

      <Card
        titolo="Esecuzioni"
        azioni={
          <div className="flex flex-wrap items-center gap-2">
            <select
              className={CLASSE_SELECT}
              value={workflow}
              onChange={(e) => imposta("workflow", e.target.value)}
            >
              <option value="">Tutti i workflow</option>
              {(elencoWorkflow.dati ?? []).map((w) => (
                <option key={w.name} value={w.name}>{w.name}</option>
              ))}
            </select>
            <select
              className={CLASSE_SELECT}
              value={esito}
              onChange={(e) => imposta("esito", e.target.value)}
            >
              {ESITI.map((v) => (
                <option key={v.valore} value={v.valore}>{v.etichetta}</option>
              ))}
            </select>
            <Bottone onClick={ricarica}>Aggiorna</Bottone>
          </div>
        }
      >
        {run.length === 0 ? (
          <Stato>
            Nessun run con questi filtri. Le esecuzioni nascono quando un operatore carica un
            documento.
          </Stato>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <th className="pb-2">Quando</th>
                <th className="pb-2">Workflow</th>
                <th className="pb-2">Documento</th>
                <th className="pb-2">Esito</th>
                <th className="pb-2 text-right">Costo</th>
                <th className="pb-2 text-right">Durata</th>
                <th className="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {run.map((r) => (
                <RigaEsecuzione
                  key={r.run_id}
                  run={r}
                  aperto={aperto === r.run_id}
                  onApri={() => setAperto(aperto === r.run_id ? null : r.run_id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

function RigaEsecuzione({
  run,
  aperto,
  onApri,
}: {
  run: RigaRun;
  aperto: boolean;
  onApri: () => void;
}) {
  return (
    <>
      <tr className="border-b border-slate-50 align-top">
        <td className="py-2 pr-3 whitespace-nowrap text-slate-500">{quando(run.ts)}</td>
        <td className="py-2 pr-3 text-slate-700">
          {run.workflow ?? "—"}
          {run.version ? <span className="text-slate-400">@{run.version}</span> : null}
        </td>
        <td className="py-2 pr-3">
          <div className="text-slate-700">{documento(run.input)}</div>
          {run.entity_id ? (
            <LinkVerso
              a={`/admin/revisione/${run.entity_id}`}
              className="font-mono text-xs text-sky-700 hover:underline"
            >
              {run.entity_id}
            </LinkVerso>
          ) : null}
        </td>
        <td className="py-2 pr-3">
          <Badge tono={tonoEsito(run.esito)}>{run.esito}</Badge>
          {run.escalation ? (
            <div className="mt-1">
              <Badge tono="blu">↑ {run.escalation}</Badge>
            </div>
          ) : null}
        </td>
        <td className="py-2 pr-3 text-right tabular-nums text-slate-600">{costo(run.costo_usd)}</td>
        <td className="py-2 pr-3 text-right tabular-nums text-slate-600">
          {durata(run.durata_ms)}
        </td>
        <td className="py-2 text-right">
          <Bottone onClick={onApri}>{aperto ? "Nascondi trace" : "Trace"}</Bottone>
        </td>
      </tr>
      {run.errore ? (
        <tr>
          <td colSpan={7} className="pb-2 text-xs text-red-700">
            {run.errore}
          </td>
        </tr>
      ) : null}
      {aperto ? (
        <tr>
          <td colSpan={7} className="pb-4">
            <div className="mb-1 text-xs text-slate-400">
              <span className="font-mono">{run.run_id}</span> · {run.n_llm} chiamate al modello ·{" "}
              {run.n_tool} tool · {run.tokens.toLocaleString("it-IT")} token
            </div>
            <TracePanel runId={run.run_id} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

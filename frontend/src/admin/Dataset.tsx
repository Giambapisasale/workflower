import { admin } from "./api";
import { useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Kpi, Stato } from "./ui";

const SOGLIA_CONSOLIDAMENTO = 3; // oltre, la query è "candidata a tool" (§3.6)

function costo(v: number): string {
  return `$ ${v.toFixed(4)}`;
}

async function esporta() {
  const blob = await admin.scaricaToolcalls();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "toolcalls.jsonl";
  a.click();
  URL.revokeObjectURL(url);
}

export default function Dataset() {
  const stats = useCarica(() => admin.datasetStats());
  const queries = useCarica(() => admin.datasetQueries());

  if (stats.inCorso) return <Stato>Carico i dati…</Stato>;
  if (stats.errore || !stats.dati) return <Errore>{stats.errore ?? "Nessun dato"}</Errore>;
  const s = stats.dati;
  const gruppi = queries.dati ?? [];

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi etichetta="Run" valore={s.run.totale} nota={`${s.run.ok} ok · ${s.run.errore} errore`} />
        <Kpi etichetta="Costo LLM" valore={costo(s.costo_totale_usd)} nota={`${s.llm_call} chiamate`} />
        <Kpi etichetta="Costo per documento" valore={costo(s.costo_per_documento_usd)} nota={`${s.documenti} documenti`} />
        <Kpi etichetta="Tool call" valore={s.tool_call} nota={`${s.toolcalls_dataset} nel dataset`} />
      </div>

      <Card
        titolo="Dataset tool call"
        azioni={<Bottone onClick={esporta}>Esporta toolcalls.jsonl</Bottone>}
      >
        <p className="text-sm text-slate-600">
          Ogni chiamata a un tool dei run validati è un esempio per il futuro fine-tuning
          di un modello locale (§3.7). Sono {s.toolcalls_dataset} righe.
        </p>
        {Object.keys(s.run_per_workflow).length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(s.run_per_workflow).map(([wf, n]) => (
              <Badge key={wf} tono="grigio">{wf}: {n} run</Badge>
            ))}
          </div>
        ) : null}
      </Card>

      <Card titolo={`Query di Interroga per fingerprint (${gruppi.length})`}>
        {gruppi.length === 0 ? (
          <Stato>Nessuna query registrata: prova la pagina Interroga.</Stato>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <th className="pb-2">Query (esempio)</th>
                <th className="pb-2 text-right">Volte</th>
                <th className="pb-2 pl-4"></th>
              </tr>
            </thead>
            <tbody>
              {gruppi.map((g) => (
                <tr key={g.fingerprint} className="border-b border-slate-50 align-top">
                  <td className="py-2 pr-4 font-mono text-xs text-slate-600">{g.esempio}</td>
                  <td className="py-2 text-right tabular-nums font-semibold">{g.conteggio}</td>
                  <td className="py-2 pl-4">
                    {g.conteggio >= SOGLIA_CONSOLIDAMENTO ? (
                      <Badge tono="giallo">candidata a tool</Badge>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

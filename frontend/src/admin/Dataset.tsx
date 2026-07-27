import { useState } from "react";
import { ErroreApi } from "../shared/api";
import { admin, type EvalT3 } from "./api";
import { useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Kpi, Stato } from "./ui";

const SOGLIA_CONSOLIDAMENTO = 3; // oltre, la query è "candidata a tool" (§3.6)

function costo(v: number): string {
  return `$ ${v.toFixed(4)}`;
}

function quota(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
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

/** Idoneità T3: il modello locale candidato è abbastanza bravo da prendersi traffico?
 *
 *  Non parte da sola, e non deve: rigioca **tutto** il set validato su due tier, e
 *  quindi costa token due volte. È una misura che si chiede quando serve una
 *  decisione, non un numero da tenere aggiornato in cruscotto. */
function IdoneitaT3() {
  const [esito, setEsito] = useState<EvalT3 | null>(null);
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  async function misura() {
    setInCorso(true);
    setErrore(null);
    try {
      setEsito(await admin.evalT3());
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Misura non riuscita.");
    } finally {
      setInCorso(false);
    }
  }

  const righe = Object.entries(esito?.workflow ?? {});

  return (
    <Card
      titolo="Idoneità T3 — il modello locale"
      azioni={
        <Bottone variante="primario" onClick={misura} disabled={inCorso}>
          {inCorso ? "Misuro…" : "Misura adesso"}
        </Bottone>
      }
    >
      <p className="mb-3 text-sm text-slate-600">
        Rigioca gli esempi già validati sul tier <b>T3</b> (modello locale) e sul tier di
        riferimento <b>T1</b>, e confronta la precisione con cui scelgono il tool e i suoi
        argomenti. Dice quali workflow sono <b>pronti</b> e dove il locale{" "}
        <b>regredirebbe</b>. Nessun addestramento: solo misura. Costa token su due tier, perciò
        parte solo quando lo chiedi.
      </p>

      {errore ? <Errore>{errore}</Errore> : null}

      {esito === null ? (
        <Stato>Nessuna misura in questa sessione.</Stato>
      ) : esito.modello_candidato === null ? (
        <Stato>
          Nessun modello T3 configurato: imposta <code>LLM_T3_MODEL</code> nell'ambiente e
          rilancia la misura.
        </Stato>
      ) : esito.esempi === 0 ? (
        <Stato>
          Nessun esempio validato da rigiocare: valida qualche documento in Revisione, poi
          torna qui.
        </Stato>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2 text-xs text-slate-500">
            <Badge tono="blu">T3: {esito.modello_candidato}</Badge>
            <Badge tono="grigio">T1: {esito.modello_riferimento ?? "—"}</Badge>
            <span>
              {esito.esempi} esempi · soglia {quota(esito.soglia)} · complessivo{" "}
              {quota(esito.totale.candidato.args)} contro {quota(esito.totale.riferimento.args)}
            </span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <th className="pb-2">Workflow</th>
                <th className="pb-2 text-right">Esempi</th>
                <th className="pb-2 text-right">T3 tool</th>
                <th className="pb-2 text-right">T3 argomenti</th>
                <th className="pb-2 text-right">T1 argomenti</th>
                <th className="pb-2">Verdetto</th>
              </tr>
            </thead>
            <tbody>
              {righe.map(([nome, v]) => (
                <tr key={nome} className="border-b border-slate-50">
                  <td className="py-2 pr-3 text-slate-700">{nome}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{v.esempi}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{quota(v.candidato.tool)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{quota(v.candidato.args)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums text-slate-500">
                    {quota(v.riferimento.args)}
                  </td>
                  <td className="py-2">
                    {v.pronto_per_t3 ? (
                      <Badge tono="verde">pronto per T3</Badge>
                    ) : v.regressione ? (
                      <Badge tono="rosso">regredirebbe</Badge>
                    ) : (
                      <Badge tono="giallo">sotto soglia</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  );
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

      <IdoneitaT3 />

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

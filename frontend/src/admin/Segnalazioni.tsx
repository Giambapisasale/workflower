import { useState } from "react";
import { Link } from "react-router-dom";
import { admin } from "./api";
import { dataBreve, euro, useCarica } from "./formato";
import TracePanel from "./TracePanel";
import { Badge, Bottone, Card, Errore, Stato } from "./ui";

export default function Segnalazioni() {
  const { dati, errore, inCorso, ricarica } = useCarica(() => admin.issues());
  const [azione, setAzione] = useState<string | null>(null);
  const [traceAperto, setTraceAperto] = useState<string | null>(null);

  if (inCorso) return <Stato>Carico le segnalazioni…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const issues = dati ?? [];

  async function chiudi(id: string) {
    setAzione(id);
    try {
      await admin.chiudiIssue(id);
      ricarica();
    } finally {
      setAzione(null);
    }
  }

  return (
    <Card titolo={`Segnalazioni (${issues.filter((i) => i.stato === "aperta").length} aperte)`}>
      {issues.length === 0 ? (
        <Stato>Nessuna segnalazione. Tutto tranquillo.</Stato>
      ) : (
        <div className="space-y-3">
          {issues.map((i) => (
            <div
              key={i.id}
              className={`rounded-lg border p-4 ${
                i.stato === "aperta" ? "border-slate-200 bg-white" : "border-slate-100 bg-slate-50 opacity-70"
              }`}
            >
              <div className="mb-1 flex items-center gap-2 text-xs">
                <span className="font-mono text-slate-400">{i.id}</span>
                <Badge tono={i.origine === "operatore" ? "blu" : "grigio"}>{i.origine}</Badge>
                <Badge tono={i.stato === "aperta" ? "giallo" : "verde"}>{i.stato}</Badge>
                <span className="text-slate-400">{dataBreve(i.created)}</span>
              </div>
              <p className="text-sm text-slate-800">{i.testo}</p>
              {i.entita ? (
                <div className="mt-1 text-xs text-slate-500">
                  {i.entita.fornitore ? `${i.entita.fornitore} · ` : ""}
                  {i.entita.totale !== undefined ? euro(i.entita.totale) : ""}
                </div>
              ) : null}
              <div className="mt-3 flex items-center gap-3 text-sm">
                {i.entity_id ? (
                  <Link className="font-medium text-sky-700 hover:underline" to={`/admin/revisione/${i.entity_id}`}>
                    Rivedi
                  </Link>
                ) : null}
                {i.run_id ? (
                  <button
                    className="text-sky-700 hover:underline"
                    onClick={() => setTraceAperto(traceAperto === i.run_id ? null : i.run_id)}
                  >
                    {traceAperto === i.run_id ? "Nascondi trace" : "Trace"}
                  </button>
                ) : null}
                {i.stato === "aperta" ? (
                  <Bottone onClick={() => chiudi(i.id)} disabled={azione === i.id}>
                    Segna risolta
                  </Bottone>
                ) : null}
              </div>
              {traceAperto === i.run_id && i.run_id ? (
                <div className="mt-3">
                  <TracePanel runId={i.run_id} />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

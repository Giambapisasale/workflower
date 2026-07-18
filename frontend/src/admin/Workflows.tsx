import { admin } from "./api";
import { useCarica } from "./formato";
import { Badge, Card, Errore, Stato } from "./ui";

export default function Workflows() {
  const { dati, errore, inCorso } = useCarica(() => admin.workflows());
  if (inCorso) return <Stato>Carico i workflow…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const workflows = dati ?? [];

  return (
    <Card titolo="Workflow">
      <div className="space-y-4">
        {workflows.map((w) => (
          <div key={w.name} className="rounded-lg border border-slate-200 p-4">
            <div className="flex items-center gap-3">
              <span className="font-mono font-semibold text-slate-800">{w.name}</span>
              <Badge tono="blu">v{w.version}</Badge>
              {w.tier ? <Badge tono="grigio">{w.tier}</Badge> : null}
            </div>
            {w.steps.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {w.steps.map((s) => (
                  <span key={s} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{s}</span>
                ))}
              </div>
            ) : null}
            <div className="mt-3 flex gap-6 text-sm text-slate-600">
              <span>
                <span className="font-semibold text-slate-800">{w.stats.totale}</span> run
              </span>
              <span className="text-green-700">{w.stats.ok} ok</span>
              <span className="text-red-600">{w.stats.errore} errore</span>
              <span>
                <span className="font-semibold text-slate-800">{w.golden}</span> casi golden
              </span>
              {w.confidence_threshold !== null ? (
                <span className="text-slate-400">soglia confidenza {w.confidence_threshold}</span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

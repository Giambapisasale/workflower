/** Confronto computo/consuntivo (M9): previsto vs speso, per cantiere e per voce. */

import { useMemo, useState } from "react";
import { admin, type ScostamentoVoce } from "./api";
import { euro, percento, useCarica } from "./formato";
import { Badge, Card, Errore, Kpi, Stato } from "./ui";

function tonoQuota(quota: number | null): string {
  if (quota === null) return "grigio";
  if (quota > 1) return "rosso";
  if (quota >= 0.8) return "giallo";
  return "verde";
}

function Barra({ quota }: { quota: number | null }) {
  const perc = Math.min(100, Math.round((quota ?? 0) * 100));
  const colore = quota !== null && quota > 1 ? "bg-red-500" : quota !== null && quota >= 0.8 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="h-2 w-full rounded-full bg-slate-100">
      <div className={`h-2 rounded-full ${colore}`} style={{ width: `${perc}%` }} />
    </div>
  );
}

export default function Scostamenti() {
  const { dati, errore, inCorso } = useCarica(() => admin.scostamenti());
  const [scelto, setScelto] = useState<string | null>(null);

  const cantieri = dati?.per_cantiere ?? [];
  const attivo = scelto ?? cantieri[0]?.cantiere_id ?? null;
  const voci: ScostamentoVoce[] = useMemo(
    () => (dati?.voci ?? []).filter((v) => v.cantiere_id === attivo),
    [dati, attivo],
  );

  if (inCorso) return <Stato>Carico gli scostamenti…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  if (cantieri.length === 0)
    return <Stato>Nessun computo caricato: non c'è ancora un preventivo con cui confrontare.</Stato>;

  return (
    <>
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        {cantieri.map((c) => (
          <button key={c.cantiere_id} onClick={() => setScelto(c.cantiere_id)} className="text-left">
            <div
              className={`rounded-xl border p-4 shadow-sm ${
                c.cantiere_id === attivo ? "border-slate-800 bg-white" : "border-slate-200 bg-white hover:bg-slate-50"
              }`}
            >
              <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
                {c.cantiere ?? c.cantiere_id}
              </div>
              <div className="mt-1 text-lg font-bold text-slate-800">{euro(c.consuntivo)}</div>
              <div className="mt-0.5 text-xs text-slate-500">
                abbinato su {euro(c.previsto)} previsti · {percento(c.previsto ? c.consuntivo / c.previsto : null)}
              </div>
            </div>
          </button>
        ))}
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Kpi etichetta="Previsto (computo)" valore={euro(voci.reduce((s, v) => s + v.previsto, 0))} />
        <Kpi etichetta="Consuntivo abbinato" valore={euro(voci.reduce((s, v) => s + v.consuntivo, 0))} />
        <Kpi
          etichetta="Voci sopra soglia"
          valore={voci.filter((v) => v.quota !== null && v.quota >= 0.8).length}
          nota="consumo ≥ 80% del previsto"
        />
      </div>

      <Card titolo="Voci di computo — previsto vs speso">
        {voci.length === 0 ? (
          <Stato>Questo cantiere non ha voci di computo.</Stato>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <th className="pb-2">Voce</th>
                <th className="pb-2">Categoria</th>
                <th className="pb-2 text-right">Previsto</th>
                <th className="pb-2 text-right">Speso</th>
                <th className="pb-2 w-40">Consumo</th>
              </tr>
            </thead>
            <tbody>
              {voci.map((v) => (
                <tr key={v.voce_id} className="border-b border-slate-50">
                  <td className="py-2 text-slate-700">
                    <span className="font-mono text-xs text-slate-400">{v.codice ?? v.voce_id}</span>{" "}
                    {v.descrizione}
                  </td>
                  <td className="py-2 text-slate-500">{v.categoria ?? "—"}</td>
                  <td className="py-2 text-right tabular-nums">{euro(v.previsto)}</td>
                  <td className="py-2 text-right tabular-nums">{euro(v.consuntivo)}</td>
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      <Barra quota={v.quota} />
                      <Badge tono={tonoQuota(v.quota)}>{percento(v.quota)}</Badge>
                    </div>
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

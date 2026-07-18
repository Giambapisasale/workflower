/** Registro di cantiere (M10): il fascicolo consolidato — spesa, ore, avanzamento. */

import { Link, useParams } from "react-router-dom";
import { admin } from "./api";
import { dataBreve, euro, percento, useCarica } from "./formato";
import { Badge, Card, Errore, Kpi, Stato } from "./ui";

function statoBadge(stato: string) {
  const tono = stato === "validato" ? "verde" : stato === "errore" ? "rosso" : "giallo";
  return <Badge tono={tono}>{stato}</Badge>;
}

export default function Cantiere() {
  const { id = "" } = useParams();
  const { dati, errore, inCorso } = useCarica(() => admin.registro(id), [id]);
  if (inCorso) return <Stato>Carico il registro…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Cantiere non trovato"}</Errore>;

  const c = dati.cantiere as Record<string, unknown>;
  const t = dati.totali;
  const scost = t.scostamento;

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link to="/admin" className="text-slate-400 hover:text-slate-700">← Cruscotto</Link>
        <h1 className="text-lg font-bold">{String(c.nome ?? id)}</h1>
        <span className="text-sm text-slate-500">{String(c.comune ?? "")}</span>
      </div>
      <div className="mb-6 text-sm text-slate-500">
        Committente: <b className="text-slate-700">{String(c.committente ?? "—")}</b> · Capocantiere:{" "}
        <b className="text-slate-700">{String(c.capocantiere ?? "—")}</b>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi
          etichetta="Speso (fatture)"
          valore={euro(t.speso_fatture)}
          nota={`su ${euro(t.budget)} · ${percento(t.quota_budget)}`}
        />
        <Kpi
          etichetta="Ore manodopera"
          valore={t.ore_totali ?? 0}
          nota={`${euro(t.costo_manodopera)} · ${t.giornate} giornate`}
        />
        <Kpi etichetta="Avanzamento (SAL)" valore={t.avanzamento !== null ? `${t.avanzamento}%` : "—"} />
        <Kpi
          etichetta="Scostamento computo"
          valore={scost ? euro(scost.consuntivo_abbinato) : "—"}
          nota={scost ? `previsto ${euro(scost.previsto)}` : "nessun computo"}
        />
      </div>

      <Card titolo={`Fatture (${dati.fatture.length})`}>
        {dati.fatture.length === 0 ? (
          <Stato>Nessuna fattura su questo cantiere.</Stato>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <th className="pb-2">Numero</th>
                <th className="pb-2">Fornitore</th>
                <th className="pb-2">Data</th>
                <th className="pb-2 text-right">Totale</th>
                <th className="pb-2">Stato</th>
              </tr>
            </thead>
            <tbody>
              {dati.fatture.map((f) => (
                <tr key={f.id} className="border-b border-slate-50">
                  <td className="py-2">
                    <Link className="text-sky-700 hover:underline" to={`/admin/revisione/${f.id}`}>
                      {f.numero ?? f.id}
                    </Link>
                  </td>
                  <td className="py-2 text-slate-700">{f.fornitore ?? "—"}</td>
                  <td className="py-2 text-slate-500">{dataBreve(f.data)}</td>
                  <td className="py-2 text-right tabular-nums">{euro(f.totale)}</td>
                  <td className="py-2">{statoBadge(f.stato)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card titolo={`DDT (${dati.ddt.length})`}>
          {dati.ddt.length === 0 ? (
            <Stato>Nessun DDT.</Stato>
          ) : (
            <ul className="space-y-2 text-sm">
              {dati.ddt.map((d) => (
                <li key={d.id} className="flex items-center justify-between border-b border-slate-50 pb-2">
                  <span className="text-slate-700">
                    {d.numero ?? d.id} · {d.fornitore ?? "—"}
                  </span>
                  <span className="text-slate-500">{dataBreve(d.data)} · {d.n_righe} righe</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card titolo={`SAL (${dati.sal.length})`}>
          {dati.sal.length === 0 ? (
            <Stato>Nessuno stato avanzamento.</Stato>
          ) : (
            <ul className="space-y-2 text-sm">
              {dati.sal.map((s) => (
                <li key={s.id} className="flex items-center justify-between border-b border-slate-50 pb-2">
                  <span className="text-slate-700">SAL n. {s.numero ?? s.id}</span>
                  <span className="text-slate-500">
                    {dataBreve(s.data)} · {s.percentuale_avanzamento}% · {euro(s.importo_progressivo)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

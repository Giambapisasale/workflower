import { Link } from "react-router-dom";
import { admin } from "./api";
import { euro, percento, useCarica } from "./formato";
import { Card, Errore, Kpi, Stato } from "./ui";

export default function Cruscotto() {
  const { dati, errore, inCorso } = useCarica(() => admin.cruscotto());
  if (inCorso) return <Stato>Carico il cruscotto…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const t = dati.totali;

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi etichetta="Fatture" valore={t.n_fatture} nota={<Link className="text-sky-700 hover:underline" to="/admin/revisione">{t.da_validare} da validare →</Link>} />
        <Kpi etichetta="Totale documenti" valore={euro(t.totale)} nota={`imponibile ${euro(t.imponibile)}`} />
        <Kpi etichetta="IVA" valore={euro(t.iva)} />
        <Kpi etichetta="Ritenute d'acconto" valore={euro(t.ritenute)} />
      </div>

      <Card titolo="Costi per cantiere">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <th className="pb-2">Cantiere</th>
              <th className="pb-2 text-right">Fatture</th>
              <th className="pb-2 text-right">Speso</th>
              <th className="pb-2 text-right">Budget</th>
              <th className="pb-2 pl-6">Consumo</th>
            </tr>
          </thead>
          <tbody>
            {dati.per_cantiere.map((c) => (
              <tr key={c.cantiere_id} className="border-b border-slate-50">
                <td className="py-2 font-medium text-slate-700">{c.cantiere ?? c.cantiere_id}</td>
                <td className="py-2 text-right tabular-nums">{c.n_fatture}</td>
                <td className="py-2 text-right tabular-nums">{euro(c.speso)}</td>
                <td className="py-2 text-right tabular-nums text-slate-500">{euro(c.budget)}</td>
                <td className="py-2 pl-6">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-32 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-sky-500"
                        style={{ width: `${Math.min(100, (c.quota_budget ?? 0) * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-slate-500">{percento(c.quota_budget)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card titolo="Fornitori principali">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <th className="pb-2">Fornitore</th>
              <th className="pb-2 text-right">Fatture</th>
              <th className="pb-2 text-right">Speso</th>
            </tr>
          </thead>
          <tbody>
            {dati.per_fornitore.map((f) => (
              <tr key={f.fornitore_id ?? f.fornitore} className="border-b border-slate-50">
                <td className="py-2 text-slate-700">{f.fornitore ?? f.fornitore_id}</td>
                <td className="py-2 text-right tabular-nums">{f.n_fatture}</td>
                <td className="py-2 text-right tabular-nums">{euro(f.speso)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

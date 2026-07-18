import { Link } from "react-router-dom";
import { admin, ETICHETTA_TIPO } from "./api";
import { dataBreve, euro, percento, useCarica } from "./formato";
import { Badge, Card, Errore, Stato } from "./ui";

function tono(c: number | null): string {
  if (c === null) return "grigio";
  return c >= 0.9 ? "verde" : c >= 0.75 ? "giallo" : "rosso";
}

export default function Revisione() {
  const { dati, errore, inCorso } = useCarica(() => admin.codaRevisione());
  if (inCorso) return <Stato>Carico la coda…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const coda = dati ?? [];

  return (
    <Card titolo={`Bozze da rivedere (${coda.length})`}>
      {coda.length === 0 ? (
        <Stato>Niente da rivedere: tutte le bozze sono validate.</Stato>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <th className="pb-2">Documento</th>
              <th className="pb-2">Fornitore</th>
              <th className="pb-2">Cantiere</th>
              <th className="pb-2 text-right">Totale</th>
              <th className="pb-2">Data</th>
              <th className="pb-2">Confidenza</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {coda.map((r) => (
              <tr key={r.id} className="border-b border-slate-50">
                <td className="py-2">
                  <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-slate-500">
                    {ETICHETTA_TIPO[r.tipo] ?? r.tipo}
                  </span>
                  <span className="font-mono text-xs text-slate-500">{r.id}</span>
                </td>
                <td className="py-2 text-slate-700">{r.fornitore ?? "—"}</td>
                <td className="py-2 text-slate-700">{r.cantiere ?? "—"}</td>
                <td className="py-2 text-right tabular-nums">{euro(r.totale)}</td>
                <td className="py-2">{dataBreve(r.data)}</td>
                <td className="py-2">
                  <Badge tono={tono(r.confidence_min)}>{percento(r.confidence_min)}</Badge>
                </td>
                <td className="py-2 text-right">
                  <Link className="font-medium text-sky-700 hover:underline" to={`/admin/revisione/${r.id}`}>
                    Rivedi →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

/** Gli inserimenti scartati: l'archivio da cui si ripristina.
 *
 * Uno scarto non cancella niente — sposta il documento fuori dai conti. Questa
 * pagina è la prova che sia vero: qui si vede *cosa* è stato scartato, *perché* e
 * da chi, e da qui si torna indietro. */

import { useState } from "react";
import { Link } from "react-router-dom";
import { ErroreApi } from "../shared/api";
import { admin } from "./api";
import { dataBreve, useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Stato } from "./ui";

export default function Scartati() {
  const { dati, errore, inCorso, ricarica } = useCarica(() => admin.scartati());
  const [inAzione, setInAzione] = useState<string | null>(null);
  const [erroreAzione, setErroreAzione] = useState<string | null>(null);

  async function ripristina(id: string) {
    setInAzione(id);
    setErroreAzione(null);
    try {
      await admin.ripristina(id);
      ricarica();
    } catch (e) {
      setErroreAzione(e instanceof ErroreApi ? e.message : "Ripristino non riuscito.");
    } finally {
      setInAzione(null);
    }
  }

  if (inCorso) return <Stato>Carico gli scartati…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const scartati = dati ?? [];

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link to="/admin/dati" className="text-slate-400 hover:text-slate-700">← Dati</Link>
        <h1 className="text-lg font-bold">Scartati</h1>
      </div>

      <Card titolo="Inserimenti scartati">
        <p className="mb-4 text-sm text-slate-600">
          Documenti che l'ufficio ha ripudiato: non contano nei costi, non sono in revisione e
          non arrivano in contabilità. <strong>Non sono cancellati</strong> — <em>Ripristina</em>{" "}
          li rimette dov'erano. Ogni scarto e ogni ripristino è un commit nel repo dati.
        </p>

        {scartati.length === 0 ? (
          <Stato>Nessun inserimento scartato.</Stato>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <th className="pb-2">Documento</th>
                <th className="pb-2">Motivo</th>
                <th className="pb-2">Scartato da</th>
                <th className="pb-2">Quando</th>
                <th className="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {scartati.map((s) => (
                <tr key={s.id} className="border-b border-slate-50 align-top">
                  <td className="py-2 pr-3">
                    <div className="font-mono text-xs text-slate-700">{s.id}</div>
                    <div className="text-xs text-slate-500">
                      {s.etichetta}
                      {s.titolo ? ` · ${s.titolo}` : ""}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {s.era_validato ? <Badge tono="giallo">era validato</Badge> : null}
                      {s.erp_id ? <Badge tono="grigio">era in contabilità</Badge> : null}
                    </div>
                  </td>
                  <td className="py-2 pr-3 text-slate-700">{s.motivo ?? "—"}</td>
                  <td className="py-2 pr-3 text-slate-600">{s.scartato_da ?? "—"}</td>
                  <td className="py-2 pr-3 whitespace-nowrap text-slate-500">
                    {dataBreve(s.scartato_il)}
                  </td>
                  <td className="py-2 text-right">
                    <Bottone onClick={() => ripristina(s.id)} disabled={inAzione === s.id}>
                      {inAzione === s.id ? "Ripristino…" : "Ripristina"}
                    </Bottone>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {erroreAzione ? (
          <div className="mt-3">
            <Errore>{erroreAzione}</Errore>
          </div>
        ) : null}
      </Card>
    </>
  );
}

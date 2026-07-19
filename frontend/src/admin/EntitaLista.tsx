/** Elenco gestibile di un tipo entità (M13): nuovo, modifica, elimina. */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErroreApi } from "../shared/api";
import { admin } from "./api";
import { useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Stato } from "./ui";

function statoBadge(stato: string) {
  const tono = stato === "validato" ? "verde" : stato === "errore" ? "rosso" : "giallo";
  return <Badge tono={tono}>{stato}</Badge>;
}

export default function EntitaLista() {
  const { tipo = "" } = useParams();
  const { dati, errore, inCorso, ricarica } = useCarica(async () => {
    const [tipi, voci] = await Promise.all([admin.entitiesMeta(), admin.entitiesLista(tipo)]);
    return { metaTipo: tipi.find((t) => t.tipo === tipo), voci };
  }, [tipo]);

  const [conferma, setConferma] = useState<string | null>(null);
  const [erroreElimina, setErroreElimina] = useState<string | null>(null);
  const [inElimina, setInElimina] = useState(false);

  if (inCorso) return <Stato>Carico…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Non trovato"}</Errore>;
  const etichetta = dati.metaTipo?.etichetta ?? tipo;

  async function elimina(id: string) {
    setInElimina(true);
    setErroreElimina(null);
    try {
      await admin.entitiesElimina(tipo, id);
      setConferma(null);
      ricarica();
    } catch (e) {
      setErroreElimina(e instanceof ErroreApi ? e.message : "Errore nell'eliminazione");
    } finally {
      setInElimina(false);
    }
  }

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link to="/admin/dati" className="text-slate-400 hover:text-slate-700">← Dati</Link>
        <h1 className="text-lg font-bold">{etichetta}</h1>
        <span className="text-sm text-slate-400">{dati.voci.length}</span>
        <div className="ml-auto">
          <Link to={`/admin/dati/${tipo}/nuovo`}>
            <Bottone variante="primario">+ Nuovo</Bottone>
          </Link>
        </div>
      </div>

      {erroreElimina ? <div className="mb-4"><Errore>{erroreElimina}</Errore></div> : null}

      <Card>
        {dati.voci.length === 0 ? (
          <Stato>Ancora niente. Usa “+ Nuovo”.</Stato>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <th className="pb-2">Codice</th>
                <th className="pb-2">Descrizione</th>
                <th className="pb-2">Stato</th>
                <th className="pb-2 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {dati.voci.map((v) => (
                <tr key={v.id} className="border-b border-slate-50">
                  <td className="py-2 font-mono text-xs text-slate-500">{v.id}</td>
                  <td className="py-2 font-medium text-slate-800">{v.titolo ?? "—"}</td>
                  <td className="py-2">{statoBadge(v.stato)}</td>
                  <td className="py-2 text-right">
                    {conferma === v.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-slate-500">Eliminare?</span>
                        <button
                          onClick={() => elimina(v.id)}
                          disabled={inElimina}
                          className="text-xs font-medium text-red-600 hover:underline disabled:opacity-40"
                        >
                          Sì, elimina
                        </button>
                        <button
                          onClick={() => setConferma(null)}
                          className="text-xs text-slate-500 hover:underline"
                        >
                          No
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-3">
                        <Link
                          to={`/admin/dati/${tipo}/${v.id}`}
                          className="text-xs font-medium text-sky-700 hover:underline"
                        >
                          Modifica
                        </Link>
                        <button
                          onClick={() => {
                            setConferma(v.id);
                            setErroreElimina(null);
                          }}
                          className="text-xs font-medium text-red-600 hover:underline"
                        >
                          Elimina
                        </button>
                      </span>
                    )}
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

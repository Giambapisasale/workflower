import { type FormEvent, useState } from "react";
import { ErroreApi } from "../shared/api";
import { admin, type EsitoAsk } from "./api";
import { Bottone, Card, Errore, Stato } from "./ui";

const ESEMPI = [
  "Quanto abbiamo speso per ogni cantiere?",
  "Quali fatture hanno una ritenuta d'acconto?",
  "Totale IVA di tutte le fatture",
];

function cella(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return new Intl.NumberFormat("it-IT").format(v);
  return String(v);
}

export default function Interroga() {
  const [domanda, setDomanda] = useState("");
  const [esito, setEsito] = useState<EsitoAsk | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(false);

  async function chiedi(testo: string) {
    if (!testo.trim()) return;
    setInCorso(true);
    setErrore(null);
    setEsito(null);
    try {
      setEsito(await admin.chiediSql(testo.trim()));
    } catch (err) {
      setErrore(err instanceof ErroreApi ? err.message : "Non sono riuscito a rispondere");
    } finally {
      setInCorso(false);
    }
  }

  function invia(e: FormEvent) {
    e.preventDefault();
    chiedi(domanda);
  }

  const colonne = esito && esito.rows.length ? Object.keys(esito.rows[0]) : [];

  return (
    <>
      <Card titolo="Interroga i dati">
        <form onSubmit={invia} className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="Fai una domanda sui costi, in italiano…"
            value={domanda}
            onChange={(e) => setDomanda(e.target.value)}
          />
          <Bottone variante="primario" type="submit" disabled={inCorso}>
            {inCorso ? "Interrogo…" : "Chiedi"}
          </Bottone>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {ESEMPI.map((e) => (
            <button
              key={e}
              onClick={() => {
                setDomanda(e);
                chiedi(e);
              }}
              className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              {e}
            </button>
          ))}
        </div>
      </Card>

      {errore ? <Errore>{errore}</Errore> : null}

      {esito ? (
        <>
          <Card titolo="SQL generato">
            <pre className="overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{esito.sql}</pre>
          </Card>
          <Card titolo={`Risultato (${esito.rows.length} righe)`}>
            {esito.rows.length === 0 ? (
              <Stato>Nessun risultato.</Stato>
            ) : (
              <div className="overflow-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                      {colonne.map((c) => (
                        <th key={c} className="pb-2 pr-4">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {esito.rows.map((r, i) => (
                      <tr key={i} className="border-b border-slate-50">
                        {colonne.map((c) => (
                          <td key={c} className="py-1.5 pr-4 tabular-nums text-slate-700">{cella(r[c])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : null}
    </>
  );
}

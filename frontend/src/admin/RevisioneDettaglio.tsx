import { type FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { admin } from "./api";
import { euro, percento, useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Stato } from "./ui";

const MONETARI = new Set(["imponibile", "iva", "totale", "ritenuta_acconto"]);

function tono(c: number | undefined): string {
  if (c === undefined) return "grigio";
  return c >= 0.9 ? "verde" : c >= 0.75 ? "giallo" : "rosso";
}

function mostraValore(campo: string, v: unknown): string {
  if (v === null || v === undefined) return "— (vuoto)";
  if (MONETARI.has(campo) && typeof v === "number") return euro(v);
  return String(v);
}

export default function RevisioneDettaglio() {
  const { id = "" } = useParams();
  const { dati: rev, errore, inCorso, ricarica } = useCarica(() => admin.revisione(id), [id]);
  const [urlOriginale, setUrlOriginale] = useState<string | null>(null);
  const [mostraJson, setMostraJson] = useState(false);
  const [campoNota, setCampoNota] = useState<string | null>(null);
  const [testoNota, setTestoNota] = useState("");
  const [azione, setAzione] = useState<string | null>(null);

  useEffect(() => {
    let url: string | null = null;
    admin
      .originale(id)
      .then((u) => {
        url = u;
        setUrlOriginale(u);
      })
      .catch(() => setUrlOriginale(null));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [id]);

  if (inCorso) return <Stato>Carico la revisione…</Stato>;
  if (errore || !rev) return <Errore>{errore ?? "Revisione non trovata"}</Errore>;

  const dati = rev.entita.dati as Record<string, unknown>;
  const righe = (Array.isArray(dati.righe) ? dati.righe : []) as Record<string, unknown>[];
  const scalari = Object.entries(dati).filter(([k]) => k !== "righe");
  const noteDi = (campo: string) => rev.feedback.filter((f) => f.campo === campo);

  async function valida() {
    setAzione("valida");
    try {
      await admin.valida(id);
      ricarica();
    } finally {
      setAzione(null);
    }
  }

  async function inviaNota(e: FormEvent) {
    e.preventDefault();
    if (!campoNota || !testoNota.trim()) return;
    setAzione("nota");
    try {
      await admin.feedback(id, campoNota, testoNota.trim());
      setCampoNota(null);
      setTestoNota("");
      ricarica();
    } finally {
      setAzione(null);
    }
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/admin/revisione" className="text-slate-400 hover:text-slate-700">← Coda</Link>
          <h1 className="font-mono text-lg font-bold">{rev.entita.id}</h1>
          {rev.validato ? (
            <Badge tono="verde">validato · {String(rev.entita.meta.validato_da ?? "")}</Badge>
          ) : (
            <Badge tono="giallo">bozza</Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Bottone onClick={() => setMostraJson((v) => !v)}>{mostraJson ? "Nascondi dati" : "Mostra dati"}</Bottone>
          {!rev.validato && (
            <Bottone variante="primario" onClick={valida} disabled={azione === "valida"}>
              {azione === "valida" ? "Salvo…" : "Salva come validato"}
            </Bottone>
          )}
        </div>
      </div>

      {rev.issue ? (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Segnalazione aperta:{" "}
          <span className="font-medium">{String((rev.issue as { testo?: string }).testo ?? "")}</span>
          {" — "}
          <Link className="underline" to="/admin/segnalazioni">vai alle segnalazioni</Link>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card titolo="Originale">
          {urlOriginale ? (
            <iframe title="originale" src={urlOriginale} className="h-[640px] w-full rounded-lg border border-slate-200" />
          ) : (
            <Stato>Anteprima non disponibile.</Stato>
          )}
        </Card>

        <Card titolo="Campi estratti">
          <table className="w-full text-sm">
            <tbody>
              {scalari.map(([campo, valore]) => (
                <tr key={campo} className="border-b border-slate-50 align-top">
                  <td className="py-2 pr-3 font-medium text-slate-500">{campo}</td>
                  <td className="py-2 pr-3 text-slate-800">{mostraValore(campo, valore)}</td>
                  <td className="py-2 pr-3">
                    <Badge tono={tono(rev.confidence[campo])}>{percento(rev.confidence[campo])}</Badge>
                  </td>
                  <td className="py-2 text-right">
                    {noteDi(campo).map((f, i) => (
                      <div key={i} className="mb-1 text-xs text-amber-700">💬 {f.nota}</div>
                    ))}
                    {campoNota === campo ? (
                      <form onSubmit={inviaNota} className="flex gap-1">
                        <input
                          autoFocus
                          value={testoNota}
                          onChange={(e) => setTestoNota(e.target.value)}
                          placeholder="cosa non torna…"
                          className="w-40 rounded border border-slate-300 px-2 py-1 text-xs"
                        />
                        <Bottone type="submit" disabled={azione === "nota"}>ok</Bottone>
                      </form>
                    ) : (
                      <button onClick={() => setCampoNota(campo)} className="text-xs text-sky-700 hover:underline">
                        + nota
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {righe.length > 0 && (
            <div className="mt-4">
              <div className="mb-1 text-xs font-medium uppercase text-slate-400">Righe</div>
              <table className="w-full text-sm">
                <tbody>
                  {righe.map((r, i) => (
                    <tr key={i} className="border-b border-slate-50">
                      <td className="py-1 text-slate-700">{String(r.descrizione ?? "")}</td>
                      <td className="py-1 text-right text-slate-500">
                        {r.quantita ? `${r.quantita} ${r.unita_misura ?? ""}` : ""}
                      </td>
                      <td className="py-1 text-right tabular-nums">{euro(r.importo as number)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {mostraJson && (
            <pre className="mt-4 max-h-72 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(rev.entita.dati, null, 2)}
            </pre>
          )}
        </Card>
      </div>
    </>
  );
}

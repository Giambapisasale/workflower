/** Diagnosi: l'analisi automatica degli errori con proposta di risoluzione.
 * `dato` = risolvibile modificando skill/tool/schema (spesso via Improver);
 * `architettura` = sola analisi sul codice-cornice. Nulla si applica da qui. */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Diagnosi as TDiagnosi } from "./api";
import { admin } from "./api";
import { dataBreve } from "./formato";
import { Badge, Bottone, Card, Errore, Stato } from "./ui";

const STATI = [
  { v: "proposta", etichetta: "Aperte" },
  { v: "risolta", etichetta: "Risolte" },
  { v: "archiviata", etichetta: "Archiviate" },
  { v: "", etichetta: "Tutte" },
];

const TONO_LIVELLO: Record<string, string> = {
  WARNING: "giallo",
  ERROR: "rosso",
  CRITICAL: "rosso",
};

function Sezione({ titolo, children }: { titolo: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{titolo}</div>
      <div className="mt-1 text-sm text-slate-700">{children}</div>
    </div>
  );
}

function Azione({ d }: { d: TDiagnosi }) {
  const a = d.azione_suggerita;
  if (d.categoria === "architettura") {
    return (
      <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
        Tocca l'architettura dell'applicazione: <strong>sola analisi</strong>, la modifica al
        codice va valutata a mano.
      </div>
    );
  }
  if (a.tipo === "improver" && a.workflow) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/admin/workflows">
          <Bottone variante="primario">Apri nell'Improver ({a.workflow})</Bottone>
        </Link>
        {a.dettaglio ? <span className="text-xs text-slate-500">{a.dettaglio}</span> : null}
      </div>
    );
  }
  return a.dettaglio ? (
    <div className="text-sm text-slate-700">{a.dettaglio}</div>
  ) : null;
}

function CartaDiagnosi({ d, onCambio }: { d: TDiagnosi; onCambio: () => void }) {
  const [aperta, setAperta] = useState(false);
  const [inCorso, setInCorso] = useState(false);

  const agisci = useCallback(
    async (fn: () => Promise<unknown>) => {
      setInCorso(true);
      try {
        await fn();
        onCambio();
      } finally {
        setInCorso(false);
      }
    },
    [onCambio],
  );

  const dato = d.categoria === "dato";
  return (
    <Card
      titolo={
        <span className="flex flex-wrap items-center gap-2 normal-case">
          <span className="font-mono text-xs text-slate-400">{d.id}</span>
          <span className="text-sm font-semibold text-slate-700">{d.titolo}</span>
          <Badge tono={dato ? "giallo" : "blu"}>
            {dato ? "correggibile (dato)" : "architettura · analisi"}
          </Badge>
          {d.livello ? <Badge tono={TONO_LIVELLO[d.livello] ?? "grigio"}>{d.livello}</Badge> : null}
          {d.stato !== "proposta" ? <Badge tono="verde">{d.stato}</Badge> : null}
        </span>
      }
      azioni={
        d.stato === "proposta" ? (
          <div className="flex gap-2">
            <Bottone disabled={inCorso} onClick={() => agisci(() => admin.risolviDiagnosi(d.id))}>
              Segna risolta
            </Bottone>
            <Bottone disabled={inCorso} onClick={() => agisci(() => admin.archiviaDiagnosi(d.id))}>
              Archivia
            </Bottone>
          </div>
        ) : null
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
          <span>fase: <span className="font-mono text-slate-600">{d.fase}</span></span>
          <span>occorrenze: <span className="font-semibold text-slate-700">{d.n_occorrenze}</span></span>
          <span>ultima: {dataBreve(d.ultima_occorrenza)}</span>
          {d.workflow ? <span>workflow: {d.workflow}</span> : null}
          <span>confidenza: {Math.round(d.confidenza * 100)}%</span>
        </div>

        {d.messaggio ? (
          <div className="rounded bg-slate-100 px-3 py-2 font-mono text-xs text-slate-600">
            {d.messaggio}
          </div>
        ) : null}

        <Sezione titolo="Analisi">{d.analisi}</Sezione>
        {d.causa_radice ? <Sezione titolo="Causa radice">{d.causa_radice}</Sezione> : null}

        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Proposta di risoluzione
          </div>
          <div className="mt-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            {d.proposta || "—"}
          </div>
          <div className="mt-2"><Azione d={d} /></div>
        </div>

        {d.file_coinvolti.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {d.file_coinvolti.map((f) => (
              <Badge key={f} tono="grigio">{f}</Badge>
            ))}
          </div>
        ) : null}

        {(d.sorgenti_lette.length > 0 || d.eccezione) ? (
          <div>
            <button
              type="button"
              onClick={() => setAperta((x) => !x)}
              className="text-xs font-medium text-slate-500 hover:text-slate-700"
            >
              {aperta ? "▾ nascondi" : "▸ mostra"} codice letto e traceback
            </button>
            {aperta ? (
              <div className="mt-2 space-y-3">
                {d.sorgenti_lette.map((s) => (
                  <div key={s.file}>
                    <div className="font-mono text-xs text-slate-500">
                      {s.file}{s.lineno ? `:${s.lineno}` : ""}
                    </div>
                    <pre className="mt-1 overflow-x-auto rounded bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
                      {s.estratto}
                    </pre>
                  </div>
                ))}
                {d.eccezione ? (
                  <pre className="overflow-x-auto rounded bg-red-950 p-3 text-xs leading-relaxed text-red-100">
                    {d.eccezione}
                  </pre>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export default function Diagnosi() {
  const [diagnosi, setDiagnosi] = useState<TDiagnosi[]>([]);
  const [stato, setStato] = useState("proposta");
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(true);
  const [analizzando, setAnalizzando] = useState(false);
  const [esito, setEsito] = useState<string | null>(null);

  const carica = useCallback(async () => {
    setInCorso(true);
    setErrore(null);
    try {
      setDiagnosi(await admin.diagnosi(stato || undefined));
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore di rete");
    } finally {
      setInCorso(false);
    }
  }, [stato]);

  useEffect(() => {
    carica();
  }, [carica]);

  const analizza = useCallback(async () => {
    setAnalizzando(true);
    setEsito(null);
    try {
      const r = await admin.analizzaErrori(1);
      setEsito(
        r.analizzate === 0
          ? "Nessun errore recente da analizzare."
          : `Analizzati ${r.analizzate} gruppi di errore.`,
      );
      await carica();
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore di rete");
    } finally {
      setAnalizzando(false);
    }
  }, [carica]);

  return (
    <>
      <Card
        titolo="Diagnosi automatica degli errori"
        azioni={
          <Bottone variante="primario" disabled={analizzando} onClick={analizza}>
            {analizzando ? "Analizzo…" : "Analizza errori adesso"}
          </Bottone>
        }
      >
        <p className="text-sm text-slate-600">
          All'arrivo di errori il sistema ne analizza la causa e propone una risoluzione: se
          impatta un <strong>dato</strong> modificabile (skill, tool, schema) suggerisce la
          modifica — spesso passando per l'Improver; se riguarda l'<strong>architettura</strong>,
          fornisce la sola analisi leggendo il proprio codice sorgente. Ogni proposta resta in
          attesa di una decisione umana.
        </p>
        {esito ? <p className="mt-3 text-sm font-medium text-slate-700">{esito}</p> : null}
        <div className="mt-4 flex gap-2">
          {STATI.map((s) => (
            <button
              key={s.v || "tutte"}
              type="button"
              onClick={() => setStato(s.v)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                stato === s.v
                  ? "bg-slate-800 text-white"
                  : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {s.etichetta}
            </button>
          ))}
        </div>
      </Card>

      {errore ? (
        <Errore>{errore}</Errore>
      ) : inCorso ? (
        <Stato>Carico le diagnosi…</Stato>
      ) : diagnosi.length === 0 ? (
        <Stato>Nessuna diagnosi: usa «Analizza errori adesso» quando compaiono errori nel Log.</Stato>
      ) : (
        diagnosi.map((d) => <CartaDiagnosi key={d.id} d={d} onCambio={carica} />)
      )}
    </>
  );
}

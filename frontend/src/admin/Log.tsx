/** Diagnostica: il logbook trasversale (tutte le fasi, errori in evidenza) con
 * livello di log configurabile a runtime, filtri e scarico. */

import { useCallback, useEffect, useState } from "react";
import type { ConfigLog, StatsLog, VoceLog } from "./api";
import { admin } from "./api";
import { Badge, Bottone, Card, Errore, Kpi, Stato } from "./ui";

const TONO_LIVELLO: Record<string, string> = {
  DEBUG: "grigio",
  INFO: "blu",
  WARNING: "giallo",
  ERROR: "rosso",
  CRITICAL: "rosso",
};

const LIVELLI_SOGLIA = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

function ora(ts: string): string {
  return ts.length >= 19 ? ts.slice(11, 23).replace("T", " ") : ts;
}

function contesto(v: VoceLog): string {
  return [
    v.workflow && `wf:${v.workflow}`,
    v.step && `step:${v.step}`,
    v.documento && `doc:${v.documento}`,
    v.utente && `utente:${v.utente}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function Voce({ v }: { v: VoceLog }) {
  const [aperta, setAperta] = useState(false);
  const ctx = contesto(v);
  const espandibile = Boolean(v.eccezione || v.dettagli || v.run_id);
  return (
    <div className="border-b border-slate-100 py-2 text-sm last:border-0">
      <button
        type="button"
        onClick={() => espandibile && setAperta((x) => !x)}
        className={`flex w-full items-start gap-3 text-left ${espandibile ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="w-28 shrink-0 font-mono text-xs text-slate-400">{ora(v.ts)}</span>
        <span className="w-20 shrink-0">
          <Badge tono={TONO_LIVELLO[v.livello] ?? "grigio"}>{v.livello}</Badge>
        </span>
        <span className="w-24 shrink-0 font-mono text-xs text-slate-500">{v.fase}</span>
        <span className="flex-1 text-slate-700">
          {v.messaggio}
          {ctx ? <span className="ml-2 text-xs text-slate-400">{ctx}</span> : null}
        </span>
        {espandibile ? (
          <span className="w-4 shrink-0 text-slate-400">{aperta ? "▾" : "▸"}</span>
        ) : null}
      </button>
      {aperta ? (
        <div className="ml-28 mt-2 space-y-2">
          {v.run_id ? (
            <div className="text-xs text-slate-500">
              run: <span className="font-mono text-slate-700">{v.run_id}</span>
            </div>
          ) : null}
          {v.dettagli !== undefined && v.dettagli !== null ? (
            <pre className="overflow-x-auto rounded bg-slate-100 p-2 text-xs text-slate-700">
              {JSON.stringify(v.dettagli, null, 2)}
            </pre>
          ) : null}
          {v.eccezione ? (
            <pre className="overflow-x-auto rounded bg-red-950 p-3 text-xs leading-relaxed text-red-100">
              {v.eccezione}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function Log() {
  const [config, setConfig] = useState<ConfigLog | null>(null);
  const [stats, setStats] = useState<StatsLog | null>(null);
  const [voci, setVoci] = useState<VoceLog[]>([]);
  const [fasi, setFasi] = useState<string[]>([]);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(true);

  // filtri
  const [livello, setLivello] = useState("DEBUG");
  const [fase, setFase] = useState("");
  const [testo, setTesto] = useState("");
  const [giorni, setGiorni] = useState(7);
  const [auto, setAuto] = useState(false);
  const [salvandoLivello, setSalvandoLivello] = useState(false);

  const carica = useCallback(async () => {
    setErrore(null);
    try {
      const [elenco, s, c] = await Promise.all([
        admin.logs({ livello, fase: fase || undefined, q: testo || undefined, giorni }),
        admin.logStats(giorni),
        admin.logConfig(),
      ]);
      setVoci(elenco.voci);
      setFasi(elenco.fasi);
      setStats(s);
      setConfig(c);
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore di rete");
    } finally {
      setInCorso(false);
    }
  }, [livello, fase, testo, giorni]);

  useEffect(() => {
    carica();
  }, [carica]);

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(carica, 5000);
    return () => clearInterval(id);
  }, [auto, carica]);

  const cambiaLivelloGlobale = useCallback(async (nuovo: string) => {
    setSalvandoLivello(true);
    try {
      const c = await admin.impostaLogLivello(nuovo);
      setConfig(c);
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore di rete");
    } finally {
      setSalvandoLivello(false);
    }
  }, []);

  const warning = stats?.per_livello?.WARNING ?? 0;

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi
          etichetta="Eventi"
          valore={stats?.totale ?? "—"}
          nota={`ultimi ${giorni} giorni`}
        />
        <Kpi etichetta="Errori" valore={stats?.errori ?? "—"} nota="ERROR + CRITICAL" />
        <Kpi etichetta="Avvisi" valore={warning} nota="WARNING" />
        <Kpi
          etichetta="Livello attivo"
          valore={config?.livello ?? "—"}
          nota="soglia di registrazione"
        />
      </div>

      <Card
        titolo="Livello di log"
        azioni={
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-slate-500">
              <input
                type="checkbox"
                checked={auto}
                onChange={(e) => setAuto(e.target.checked)}
              />
              auto-aggiorna
            </label>
            <Bottone onClick={carica}>Aggiorna</Bottone>
            <Bottone onClick={() => admin.scaricaLog()}>Esporta (oggi)</Bottone>
          </div>
        }
      >
        <p className="mb-3 text-sm text-slate-600">
          Registra dalla soglia scelta in su. La modifica vale subito ed è persistita
          (sopravvive al riavvio). Il default all'avvio arriva da <code>LOG_LEVEL</code>.
        </p>
        <div className="flex flex-wrap gap-2">
          {(config?.livelli ?? LIVELLI_SOGLIA).map((l) => (
            <button
              key={l}
              type="button"
              disabled={salvandoLivello || config?.livello === l}
              onClick={() => cambiaLivelloGlobale(l)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-100 ${
                config?.livello === l
                  ? "bg-slate-800 text-white"
                  : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </Card>

      <Card titolo="Eventi">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-500">
            Da livello
            <select
              value={livello}
              onChange={(e) => setLivello(e.target.value)}
              className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              {LIVELLI_SOGLIA.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">
            Fase
            <select
              value={fase}
              onChange={(e) => setFase(e.target.value)}
              className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="">tutte</option>
              {fasi.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">
            Periodo
            <select
              value={giorni}
              onChange={(e) => setGiorni(Number(e.target.value))}
              className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value={1}>oggi</option>
              <option value={7}>7 giorni</option>
              <option value={30}>30 giorni</option>
            </select>
          </label>
          <label className="flex-1 text-xs text-slate-500">
            Cerca nel testo
            <input
              value={testo}
              onChange={(e) => setTesto(e.target.value)}
              placeholder="messaggio, run_id, documento…"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
          </label>
        </div>

        {errore ? (
          <Errore>{errore}</Errore>
        ) : inCorso ? (
          <Stato>Carico i log…</Stato>
        ) : voci.length === 0 ? (
          <Stato>Nessun evento per questi filtri.</Stato>
        ) : (
          <div className="rounded-lg border border-slate-100">
            {voci.map((v, i) => (
              <div key={i} className="px-3">
                <Voce v={v} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

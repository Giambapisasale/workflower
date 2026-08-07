import { type FormEvent, useEffect, useState } from "react";
import { ErroreApi } from "../shared/api";
import { Input } from "../ds";
import { admin, type MessaggioAgente } from "./api";
import TracePanel from "./TracePanel";
import { Bottone, Card, Chip, Errore, Stato } from "./ui";

const ESEMPI = [
  "Quanto abbiamo speso per ogni cantiere?",
  "Quali fatture hanno una ritenuta d'acconto?",
  "Quali scadenze abbiamo in arrivo?",
];

export default function Interroga() {
  const [domanda, setDomanda] = useState("");
  const [messaggi, setMessaggi] = useState<MessaggioAgente[]>([]);
  const [limite, setLimite] = useState(20);
  const [tools, setTools] = useState<string[]>([]);
  const [fonti, setFonti] = useState<{ tool: string; source: string }[]>([]);
  const [ultimoRun, setUltimoRun] = useState<string | null>(null);
  const [traceAperto, setTraceAperto] = useState<string | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(false);

  useEffect(() => {
    void admin.conversazioneAgente().then((r) => {
      setMessaggi(r.messages);
      setLimite(r.max_messages);
    });
  }, []);

  async function chiedi(testo: string) {
    if (!testo.trim() || inCorso) return;
    setInCorso(true);
    setErrore(null);
    try {
      const r = await admin.messaggioAgente(testo.trim());
      setMessaggi(r.messages);
      setLimite(r.max_messages);
      setTools(r.used_tools);
      setFonti(r.sources);
      setUltimoRun(r.run_id);
      setDomanda("");
    } catch (err) {
      setErrore(err instanceof ErroreApi ? err.message : "Non sono riuscito a rispondere.");
    } finally {
      setInCorso(false);
    }
  }

  function invia(e: FormEvent) {
    e.preventDefault();
    void chiedi(domanda);
  }

  async function azzera() {
    const r = await admin.resetConversazioneAgente();
    setMessaggi(r.messages);
    setLimite(r.max_messages);
    setTools([]);
    setFonti([]);
    setUltimoRun(null);
    setTraceAperto(null);
  }

  return (
    <>
      <Card titolo="Agente dati">
        <p className="mb-3 text-sm text-slate-600">
          Risponde usando strumenti verificati. Contesto: {messaggi.length}/{limite} messaggi.
        </p>
        <form onSubmit={invia} style={{ display: "flex", gap: 8 }}>
          <Input
            placeholder="Fai una domanda sui dati…"
            value={domanda}
            onChange={(e) => setDomanda(e.target.value)}
          />
          <Bottone variante="primario" type="submit" disabled={inCorso}>
            {inCorso ? "Rispondo…" : "Invia"}
          </Bottone>
          <Bottone type="button" onClick={() => void azzera()} disabled={inCorso}>
            Nuova conversazione
          </Bottone>
        </form>
        <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
          {ESEMPI.map((e) => <Chip key={e} onClick={() => void chiedi(e)}>{e}</Chip>)}
        </div>
      </Card>

      {errore ? <Errore>{errore}</Errore> : null}
      {messaggi.length === 0 && !inCorso ? <Stato>Inizia con una domanda.</Stato> : null}
      {messaggi.map((m, i) => (
        <Card key={`${m.role}-${i}`} titolo={m.role === "user" ? "Tu" : "Agente"}>
          <div className="whitespace-pre-wrap text-sm">{m.content}</div>
          {m.role === "assistant" && m.run_id ? (
            <div className="mt-2 text-xs">
              <button
                className="text-sky-700 underline"
                onClick={() => setTraceAperto(traceAperto === m.run_id ? null : m.run_id ?? null)}
              >
                {traceAperto === m.run_id ? "Nascondi trace" : "Apri trace"}
              </button>
              {traceAperto === m.run_id ? <div className="mt-2"><TracePanel runId={m.run_id} /></div> : null}
            </div>
          ) : null}
        </Card>
      ))}
      {inCorso ? <Stato>Controllo i dati…</Stato> : null}
      {tools.length ? (
        <Card titolo="Fonti e strumenti usati">
          <div className="text-sm text-slate-600">{Array.from(new Set(tools)).join(", ")}</div>
          {fonti.length ? (
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
              {fonti.map((fonte) => <Chip key={`${fonte.tool}-${fonte.source}`}>{fonte.source}</Chip>)}
            </div>
          ) : null}
        </Card>
      ) : null}
      {ultimoRun ? (
        <Card titolo="Trace">
          <p className="text-sm text-slate-600">Run registrato: {ultimoRun}</p>
          <a className="text-sm text-sky-700 underline" href="/admin/run">Apri l'elenco dei run</a>
        </Card>
      ) : null}
    </>
  );
}

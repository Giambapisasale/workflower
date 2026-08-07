import { useEffect, useState } from "react";
import { ErroreApi } from "../shared/api";
import { admin, type EvoluzioneAgente as Evoluzione, type PropostaAgente } from "./api";
import { Bottone, Card, Errore, Stato } from "./ui";

export default function EvoluzioneAgente() {
  const [dati, setDati] = useState<Evoluzione | null>(null);
  const [feedback, setFeedback] = useState("");
  const [limite, setLimite] = useState(20);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(false);

  async function carica() {
    try {
      const [evoluzione, config] = await Promise.all([admin.evoluzioneAgente(), admin.configurazioneAgente()]);
      setDati(evoluzione);
      setLimite(config.max_messages);
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Non riesco a caricare l'evoluzione.");
    }
  }
  useEffect(() => { void carica(); }, []);

  async function proponi() {
    if (!feedback.trim()) return;
    setInCorso(true); setErrore(null);
    try { await admin.proponiEvoluzioneAgente(feedback.trim()); setFeedback(""); await carica(); }
    catch (e) { setErrore(e instanceof ErroreApi ? e.message : "Non riesco a creare la proposta."); }
    finally { setInCorso(false); }
  }
  async function decidi(p: PropostaAgente, azione: "approva" | "rifiuta") {
    setInCorso(true); setErrore(null);
    try {
      if (azione === "approva") await admin.approvaEvoluzioneAgente(p.id);
      else await admin.rifiutaEvoluzioneAgente(p.id);
      await carica();
    } catch (e) { setErrore(e instanceof ErroreApi ? e.message : "Decisione non riuscita."); }
    finally { setInCorso(false); }
  }
  async function salvaLimite() {
    setInCorso(true); setErrore(null);
    try { await admin.salvaConfigurazioneAgente(limite); await carica(); }
    catch (e) { setErrore(e instanceof ErroreApi ? e.message : "Non riesco a salvare il limite."); }
    finally { setInCorso(false); }
  }

  return (
    <>
      <Card titolo="Evoluzione agente">
        <p className="mb-3 text-sm text-slate-600">Le nuove capacità restano proposte finché l'ufficio non le verifica e approva.</p>
        <textarea className="min-h-24 w-full rounded-lg border border-slate-300 p-2 text-sm" value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Cosa manca o cosa andrebbe migliorato?" />
        <div className="mt-2"><Bottone variante="primario" onClick={() => void proponi()} disabled={inCorso || !feedback.trim()}>{inCorso ? "Preparo…" : "Proponi un miglioramento"}</Bottone></div>
      </Card>
      <Card titolo="Memoria della conversazione">
        <label className="text-sm text-slate-600">Messaggi conservati (da 6 a 30)</label>
        <div className="mt-2 flex gap-2"><input type="number" min={6} max={30} className="w-20 rounded border border-slate-300 p-1" value={limite} onChange={(e) => setLimite(Number(e.target.value))} /><Bottone onClick={() => void salvaLimite()} disabled={inCorso}>Salva</Bottone></div>
      </Card>
      {errore ? <Errore>{errore}</Errore> : null}
      <Card titolo={`Copertura: ${dati?.tools.length ?? 0} tool disponibili`}>
        {dati ? <div className="space-y-2">{dati.tools.map((t) => <details key={t.name} className="rounded bg-sky-50 p-2 text-sm text-sky-900"><summary className="cursor-pointer"><b>{t.name}</b> · {t.description} · {(t.roles ?? []).join(", ")} · {t.scope}</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(t, null, 2)}</pre></details>)}</div> : <Stato>Carico…</Stato>}
      </Card>
      <Card titolo="Proposte">
        {!dati?.proposals.length ? <Stato>Nessuna lacuna segnalata o proposta in attesa.</Stato> : (
          <ul className="space-y-3">{dati.proposals.map((p) => <li key={p.id} className="border-b border-slate-100 pb-3 text-sm"><div className="flex gap-2"><b>{p.id}</b><span>{p.stato}</span></div><p>{p.analisi || p.feedback}</p><p className="text-slate-500">{p.motivazione}</p>{p.intenti?.length ? <p className="text-xs text-slate-500">Copre: {p.intenti.join(", ")}</p> : null}<p className="text-xs text-slate-500">Test mirato: {p.compilazione?.ok ? "verde" : p.compilazione?.errore || "non disponibile"}. Replay {p.replay.ok}/{p.replay.totale}</p><details className="mt-2 rounded bg-slate-50 p-2"><summary className="cursor-pointer text-xs">Dettaglio DSL, esempi e collaudo</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify({ intendi: p.intenti, parametri: p.parametri, esempi: p.esempi, risultato_atteso: p.risultato_atteso, tool: p.tool, skill: p.skill, compilazione: p.compilazione, replay: p.replay }, null, 2)}</pre></details>{p.stato === "proposta" ? <div className="mt-2 flex gap-2"><Bottone variante="primario" onClick={() => void decidi(p, "approva")} disabled={inCorso}>Approva</Bottone><Bottone variante="pericolo" onClick={() => void decidi(p, "rifiuta")} disabled={inCorso}>Rifiuta</Bottone></div> : null}</li>)}</ul>
        )}
      </Card>
    </>
  );
}

/** Conversazione semplice dell'operatore con l'agente dati. */

import { useEffect, useState } from "react";
import { ChatBubbleIcon } from "@radix-ui/react-icons";
import { api, type MessaggioAgente } from "../shared/api";
import { Input, Spinner } from "../ds";
import { TESTI } from "./testi";
import { BottonePieno, Card, Indietro, Titolo } from "./ui";

export default function Chiedi() {
  const [domanda, setDomanda] = useState("");
  const [attesa, setAttesa] = useState(false);
  const [messaggi, setMessaggi] = useState<MessaggioAgente[]>([]);
  const [limite, setLimite] = useState(20);

  useEffect(() => {
    void api.conversazioneAgente().then((r) => {
      setMessaggi(r.messages);
      setLimite(r.max_messages);
    });
  }, []);

  async function chiedi() {
    const testo = domanda.trim();
    if (!testo || attesa) return;
    setAttesa(true);
    try {
      const r = await api.messaggioAgente(testo);
      setMessaggi(r.messages);
      setLimite(r.max_messages);
      setDomanda("");
    } catch {
      setMessaggi((precedenti) => [...precedenti, { role: "assistant", content: TESTI.nonSoRispondere }]);
    } finally {
      setAttesa(false);
    }
  }

  async function nuovaConversazione() {
    const r = await api.resetConversazioneAgente();
    setMessaggi(r.messages);
    setLimite(r.max_messages);
  }

  return (
    <div>
      <Indietro a="/op" />
      <Titolo>{TESTI.titoloChiedi}</Titolo>
      <p style={{ marginTop: -8, marginBottom: 16, color: "var(--text-secondary)", fontSize: 15 }}>
        Contesto disponibile: {messaggi.length}/{limite} messaggi.
      </p>
      <form onSubmit={(e) => { e.preventDefault(); void chiedi(); }}>
        <div style={{ marginBottom: 16 }}>
          <Input
            value={domanda}
            onChange={(e) => setDomanda(e.target.value)}
            placeholder={TESTI.segnapostoDomanda}
            style={{ width: "100%", fontSize: 18, padding: "12px 14px" }}
            autoFocus
          />
        </div>
        <BottonePieno tipo="submit" icona={ChatBubbleIcon} disabled={!domanda.trim() || attesa}>
          {TESTI.chiedi}
        </BottonePieno>
      </form>

      <button
        type="button"
        onClick={() => void nuovaConversazione()}
        disabled={attesa}
        style={{ border: 0, background: "none", color: "var(--text-secondary)", marginTop: 14, padding: 0 }}
      >
        Nuova conversazione
      </button>

      {messaggi.map((m, i) => (
        <div key={`${m.role}-${i}`} style={{ marginTop: 12, textAlign: m.role === "user" ? "right" : "left" }}>
          <Card>{m.content}</Card>
        </div>
      ))}
      {attesa ? (
        <div style={{ marginTop: 16 }}><Card><div style={{ display: "flex", alignItems: "center", gap: 12 }}><Spinner size="sm" /><span>{TESTI.ciPenso}</span></div></Card></div>
      ) : null}
    </div>
  );
}

/** "Chiedi qualcosa": domanda libera → risposta in italiano semplice. Stop. */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChatBubbleIcon } from "@radix-ui/react-icons";
import { api } from "../shared/api";
import { Input, Spinner } from "../ds";
import { TESTI } from "./testi";
import { BottonePieno, Card, Indietro, Titolo } from "./ui";

export default function Chiedi() {
  const naviga = useNavigate();
  const [domanda, setDomanda] = useState("");
  const [attesa, setAttesa] = useState(false);
  const [risposta, setRisposta] = useState<string | null>(null);

  async function chiedi() {
    const testo = domanda.trim();
    if (!testo || attesa) return;
    setAttesa(true);
    setRisposta(null);
    try {
      setRisposta(await api.chiedi(testo));
    } catch {
      setRisposta(TESTI.nonSoRispondere);
    } finally {
      setAttesa(false);
    }
  }

  return (
    <div>
      <Indietro onClick={() => naviga("/op")} />
      <Titolo>{TESTI.titoloChiedi}</Titolo>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void chiedi();
        }}
      >
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

      {attesa ? (
        <div style={{ marginTop: 16 }}>
          <Card>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <Spinner size="sm" />
              <span>{TESTI.ciPenso}</span>
            </div>
          </Card>
        </div>
      ) : null}
      {risposta ? (
        <div style={{ marginTop: 16, textWrap: "pretty" }}>
          <Card>{risposta}</Card>
        </div>
      ) : null}
    </div>
  );
}

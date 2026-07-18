/** "Chiedi qualcosa": domanda libera → risposta in italiano semplice. Stop. */

import { useState } from "react";
import { api } from "../shared/api";
import { TESTI } from "./testi";
import { Card, Indietro, Titolo } from "./ui";

export default function Chiedi() {
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
      <Indietro a="/op" />
      <Titolo>{TESTI.titoloChiedi}</Titolo>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void chiedi();
        }}
      >
        <input
          className="mb-4 w-full rounded-2xl border-2 border-neutral-300 px-4 py-4 text-[18px] focus:border-neutral-900 focus:outline-none"
          value={domanda}
          onChange={(e) => setDomanda(e.target.value)}
          placeholder={TESTI.segnapostoDomanda}
          autoFocus
        />
        <button
          type="submit"
          className="flex min-h-[60px] w-full items-center justify-center gap-3 rounded-2xl border-2 border-green-700 bg-green-700 text-[19px] font-bold text-white disabled:opacity-40"
          disabled={!domanda.trim() || attesa}
        >
          {TESTI.chiedi} 🎤
        </button>
      </form>

      {attesa ? (
        <div className="mt-4">
          <Card>⏳ {TESTI.ciPenso}</Card>
        </div>
      ) : null}
      {risposta ? (
        <div className="mt-4">
          <Card>💬 {risposta}</Card>
        </div>
      ) : null}
    </div>
  );
}

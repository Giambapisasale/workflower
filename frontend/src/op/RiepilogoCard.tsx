/** Pezzi condivisi tra Carica e Dettaglio: le tre righe e il 👍/👎. */

import { useState } from "react";
import { api, type DocumentoVista, type Riepilogo, type RigaRiepilogo } from "../shared/api";
import { dataBreve, euro, percentuale, TESTI } from "./testi";

/** Le righe arrivano già scelte dal backend (una per entità): qui le mostriamo
 * e basta. Così SAL, rapportino e ogni entità futura parlano da sé. */
export function RigheRiepilogo({ riepilogo }: { riepilogo: Riepilogo }) {
  return (
    <div className="my-3 space-y-1">
      {riepilogo.righe.map((riga, i) => (
        <Riga key={i} etichetta={riga.etichetta} valore={mostra(riga)} />
      ))}
    </div>
  );
}

/** L'etichetta arriva dal backend; qui diamo forma al valore secondo il tipo. */
function mostra(riga: RigaRiepilogo): string {
  switch (riga.tipo) {
    case "euro":
      return euro(Number(riga.valore));
    case "percento":
      return percentuale(Number(riga.valore));
    case "data":
      return dataBreve(String(riga.valore));
    default:
      return String(riga.valore);
  }
}

function Riga({ etichetta, valore }: { etichetta: string; valore: string }) {
  return (
    <div>
      {etichetta}: <b>{valore}</b>
    </div>
  );
}

/**
 * "È tutto giusto?" → 👍 conferma / 👎 testo libero → segnalazione.
 * Una domanda alla volta; su rete assente, un avviso gentile e si riprova.
 */
export function PannelloVerdetto({
  doc,
  onGrazie,
}: {
  doc: DocumentoVista;
  onGrazie: () => void;
}) {
  const [fase, setFase] = useState<"domanda" | "scrivi">("domanda");
  const [testo, setTesto] = useState("");
  const [attesa, setAttesa] = useState(false);
  const [avviso, setAvviso] = useState<string | null>(null);

  async function prova(azione: () => Promise<void>) {
    if (attesa) return;
    setAttesa(true);
    setAvviso(null);
    try {
      await azione();
      onGrazie();
    } catch {
      setAvviso(TESTI.nonRiesco);
    } finally {
      setAttesa(false);
    }
  }

  if (fase === "scrivi") {
    return (
      <div className="mt-3">
        <b>{TESTI.dimmiCosa}</b>
        <textarea
          className="mt-2 min-h-[96px] w-full rounded-2xl border-2 border-neutral-300 p-3 focus:border-neutral-900 focus:outline-none"
          value={testo}
          onChange={(e) => setTesto(e.target.value)}
          placeholder={TESTI.scriviQui}
          autoFocus
        />
        {avviso ? <p className="my-2 font-bold text-red-700">{avviso}</p> : null}
        <button
          type="button"
          className="mt-2 min-h-[56px] w-full rounded-2xl border-2 border-green-700 bg-green-700 px-4 text-[18px] font-bold text-white disabled:opacity-40"
          disabled={!testo.trim() || attesa}
          onClick={() => void prova(() => api.segnala(doc.id, testo.trim()))}
        >
          {attesa ? TESTI.caricamento : TESTI.invia}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-3">
      <div className="text-[19px] font-bold">{TESTI.tuttoGiusto}</div>
      {avviso ? <p className="my-2 font-bold text-red-700">{avviso}</p> : null}
      <div className="mt-3 flex gap-3">
        <button
          type="button"
          className="min-h-[60px] flex-1 rounded-2xl border-2 border-green-700 bg-green-700 px-2 text-[18px] font-bold text-white disabled:opacity-40"
          disabled={attesa}
          onClick={() => void prova(() => api.conferma(doc.id))}
        >
          {TESTI.si}
        </button>
        <button
          type="button"
          className="min-h-[60px] flex-1 rounded-2xl border-2 border-neutral-900 bg-white px-2 text-[18px] font-bold disabled:opacity-40"
          disabled={attesa}
          onClick={() => setFase("scrivi")}
        >
          {TESTI.nonTorna}
        </button>
      </div>
    </div>
  );
}

export function CardGrazie({ onHome }: { onHome?: () => void }) {
  return (
    <div className="rounded-2xl border-2 border-neutral-300 p-4">
      <b>{TESTI.grazie}</b>
      <p className="mt-1 text-neutral-600">{TESTI.sottoGrazie}</p>
      {onHome ? (
        <button
          type="button"
          className="mt-4 flex min-h-[56px] w-full items-center gap-3 rounded-2xl border-2 border-neutral-900 px-4 text-[18px] font-bold"
          onClick={onHome}
        >
          <span className="text-2xl">🏠</span> {TESTI.tornaHome}
        </button>
      ) : null}
    </div>
  );
}

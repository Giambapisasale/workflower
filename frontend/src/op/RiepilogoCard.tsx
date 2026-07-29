/** Pezzi condivisi tra Carica e Dettaglio: le righe lette e il "È tutto giusto?". */

import { useState } from "react";
import { CheckIcon, Cross1Icon, HomeIcon } from "@radix-ui/react-icons";
import { api, type DocumentoVista, type Riepilogo, type RigaRiepilogo } from "../shared/api";
import { TextArea } from "../ds";
import { dataBreve, euro, percentuale, TESTI } from "./testi";
import { Avviso, BottoneGrande, BottoneMezzo, BottonePieno } from "./ui";

/** Le righe arrivano già scelte dal backend (una per entità): qui le mostriamo
 * e basta. Così SAL, rapportino e ogni entità futura parlano da sé. */
export function RigheRiepilogo({ riepilogo }: { riepilogo: Riepilogo }) {
  return (
    <div style={{ margin: "14px 0", display: "flex", flexDirection: "column", gap: 4 }}>
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
 * "È tutto giusto?" → Sì conferma / "Non torna" apre il testo libero.
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
      <div style={{ marginTop: 12 }}>
        <b>{TESTI.dimmiCosa}</b>
        <div style={{ marginTop: 8 }}>
          <TextArea
            type="inputForm"
            value={testo}
            onChange={(e) => setTesto(e.target.value)}
            placeholder={TESTI.scriviQui}
            style={{ width: "100%", minHeight: 96, fontSize: 18 }}
            autoFocus
          />
        </div>
        {avviso ? <Avviso>{avviso}</Avviso> : null}
        <div style={{ marginTop: 12 }}>
          <BottonePieno
            disabled={!testo.trim() || attesa}
            onClick={() => void prova(() => api.segnala(doc.id, testo.trim()))}
          >
            {attesa ? TESTI.caricamento : TESTI.invia}
          </BottonePieno>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ fontSize: 19, fontWeight: 700, marginTop: 14 }}>{TESTI.tuttoGiusto}</div>
      {avviso ? (
        <div style={{ marginTop: 12 }}>
          <Avviso>{avviso}</Avviso>
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
        <BottoneMezzo
          primario
          icona={CheckIcon}
          disabled={attesa}
          onClick={() => void prova(() => api.conferma(doc.id))}
        >
          {TESTI.si}
        </BottoneMezzo>
        <BottoneMezzo icona={Cross1Icon} disabled={attesa} onClick={() => setFase("scrivi")}>
          {TESTI.nonTorna}
        </BottoneMezzo>
      </div>
    </div>
  );
}

export function CardGrazie({ onHome }: { onHome?: () => void }) {
  return (
    <div
      style={{
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius)",
        padding: 16,
      }}
    >
      <b>{TESTI.grazie}</b>
      <p style={{ margin: "6px 0 0", color: "var(--text-secondary)" }}>{TESTI.sottoGrazie}</p>
      {onHome ? (
        <div style={{ marginTop: 16 }}>
          <BottoneGrande icona={HomeIcon} onClick={onHome}>
            {TESTI.tornaHome}
          </BottoneGrande>
        </div>
      ) : null}
    </div>
  );
}

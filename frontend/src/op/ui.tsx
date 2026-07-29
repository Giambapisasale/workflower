/**
 * Mattoni della UI Operatore, disegnati sul design system Aitho.
 * Bottoni giganti (touch ≥ 48px, qui 56/64px), card a bordo sottile, semaforo
 * a pallino colorato. Nessuna emoji: le icone sono quelle del design system.
 */

import type { ReactNode } from "react";
import { useRef } from "react";
import { ArrowLeftIcon } from "@radix-ui/react-icons";
import { Button } from "../ds";
import type { Icona } from "../ds";
import type { Semaforo } from "../shared/api";
import { TESTI } from "./testi";

/* Tutti i bottoni qui dichiarano `type="button"`: l'Operatore ha due form (il
   login a due passi, la domanda libera) e un bottone senza `type` dentro un
   form è un invio travestito. L'invio lo chiede solo `BottonePieno tipo="submit"`. */

/** I bottoni dell'Operatore portano l'icona dentro il contenuto, come nel
 *  design: la `icon` del design system userebbe una griglia più stretta. */
function Contenuto({ icona, children }: { icona?: Icona; children: ReactNode }) {
  const Icona = icona;
  if (!Icona) return <>{children}</>;
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <Icona width={22} height={22} />
      {children}
    </span>
  );
}

const STILE_GRANDE = {
  width: "100%",
  minHeight: 64,
  justifyContent: "flex-start",
  fontSize: 19,
  textAlign: "left",
} as const;

const STILE_PIENO = {
  width: "100%",
  minHeight: 56,
  justifyContent: "center",
  fontSize: 18,
} as const;

/** Bottone a tutta larghezza, allineato a sinistra: la scelta principale. */
export function BottoneGrande({
  icona,
  primario = false,
  disabled,
  onClick,
  children,
}: {
  icona?: Icona;
  primario?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      variant={primario ? "primary" : "outline"}
      size="lg"
      type="button"
      className="aitho-btn wf-btn-largo"
      style={STILE_GRANDE}
      disabled={disabled}
      onClick={onClick}
    >
      <Contenuto icona={icona}>{children}</Contenuto>
    </Button>
  );
}

/** Bottone a tutta larghezza, testo centrato: "Avanti", "Entra", "Invia". */
export function BottonePieno({
  primario = true,
  tipo = "button",
  icona,
  disabled,
  onClick,
  children,
}: {
  primario?: boolean;
  tipo?: "button" | "submit";
  icona?: Icona;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      variant={primario ? "primary" : "outline"}
      size="lg"
      type={tipo}
      style={STILE_PIENO}
      disabled={disabled}
      onClick={onClick}
    >
      <Contenuto icona={icona}>{children}</Contenuto>
    </Button>
  );
}

/** Due bottoni affiancati: "Sì" / "Non torna". */
export function BottoneMezzo({
  primario = false,
  icona,
  disabled,
  onClick,
  children,
}: {
  primario?: boolean;
  icona?: Icona;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      variant={primario ? "primary" : "outline"}
      size="lg"
      type="button"
      style={{ flex: 1, minHeight: 56, justifyContent: "center", fontSize: 18 }}
      disabled={disabled}
      onClick={onClick}
    >
      <Contenuto icona={icona}>{children}</Contenuto>
    </Button>
  );
}

/** Come BottoneGrande, ma apre la fotocamera o i file del telefono. */
export function BottoneFile({
  icona,
  primario = false,
  accept,
  capture,
  onFile,
  children,
}: {
  icona?: Icona;
  primario?: boolean;
  accept: string;
  capture?: boolean | "user" | "environment";
  onFile: (file: File | null) => void;
  children: ReactNode;
}) {
  const campo = useRef<HTMLInputElement>(null);
  return (
    <>
      <BottoneGrande icona={icona} primario={primario} onClick={() => campo.current?.click()}>
        {children}
      </BottoneGrande>
      <input
        ref={campo}
        type="file"
        style={{ display: "none" }}
        accept={accept}
        capture={capture}
        onChange={(e) => {
          onFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
    </>
  );
}

export function Card({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius)",
        padding: 16,
      }}
    >
      {children}
    </div>
  );
}

export function Indietro({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="transparent"
      size="sm"
      type="button"
      compact
      icon={{ data: ArrowLeftIcon }}
      onClick={onClick}
      style={{ minHeight: 32 }}
    >
      {TESTI.indietro}
    </Button>
  );
}

export function Titolo({ children }: { children: ReactNode }) {
  return <h1 style={{ fontSize: 23, fontWeight: 700, margin: "12px 0 20px" }}>{children}</h1>;
}

/** La domanda del passo corrente: una sola per schermata. */
export function Domanda({ children }: { children: ReactNode }) {
  return <p style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>{children}</p>;
}

export function Spiegazione({ children }: { children: ReactNode }) {
  return <p style={{ color: "var(--text-secondary)", margin: 0 }}>{children}</p>;
}

export function Avviso({ children }: { children: ReactNode }) {
  return (
    <p style={{ color: "var(--color-error)", fontWeight: 700, margin: "0 0 16px" }}>{children}</p>
  );
}

export const COLORE_SEMAFORO: Record<Semaforo, string> = {
  verde: "var(--color-success)",
  giallo: "var(--color-warning)",
  rosso: "var(--color-error)",
};

/** Il semaforo del documento: un pallino, senza parole tecniche accanto. */
export function Pallino({ semaforo, alto = false }: { semaforo: Semaforo; alto?: boolean }) {
  return (
    <span
      style={{
        width: 14,
        height: 14,
        borderRadius: 999,
        flexShrink: 0,
        marginTop: alto ? 5 : 0,
        background: COLORE_SEMAFORO[semaforo],
      }}
    />
  );
}

/** Colonna con spazio uniforme: il ritmo verticale di tutte le schermate. */
export function Colonna({ gap = 16, children }: { gap?: number; children: ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap }}>{children}</div>;
}

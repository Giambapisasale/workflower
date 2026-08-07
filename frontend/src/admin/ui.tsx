/**
 * Mattoni della console Admin, disegnati sul design system Aitho.
 * (Le formattazioni di numeri e date stanno in formato.ts.)
 *
 * L'idioma del design è regolare: intestazione di pagina, card a bordo
 * sottile con titolo in maiuscoletto, riquadri KPI, pillole di stato. Tenendo
 * questi pezzi in un posto solo, tutte le pagine cambiano pelle insieme.
 */

import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeftIcon } from "@radix-ui/react-icons";
import { Button, Table } from "../ds";
import type { TableColumn, TableRow } from "../ds";
import { etichettaPercorso, usePercorsoCorrente, useProvenienza } from "./provenienza";

/* ---------- superfici ---------- */

const SUPERFICIE = {
  background: "var(--background-primary)",
  border: "1px solid var(--border-color)",
  borderRadius: "var(--radius-lg)",
} as const;

const TITOLETTO = {
  margin: 0,
  fontSize: 13,
  fontWeight: 700,
  letterSpacing: ".06em",
  textTransform: "uppercase",
  color: "var(--text-secondary)",
} as const;

/** Card con titolo in maiuscoletto e azioni a destra. Il corpo ha il suo
 *  respiro; chi vuole il bordo a filo passa `senzaPadding`. */
export function Card({
  titolo,
  azioni,
  senzaPadding = false,
  children,
}: {
  titolo?: ReactNode;
  azioni?: ReactNode;
  senzaPadding?: boolean;
  children: ReactNode;
}) {
  return (
    <section style={{ ...SUPERFICIE, marginBottom: 24 }}>
      {titolo || azioni ? (
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "12px 20px",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <h2 style={TITOLETTO}>{titolo}</h2>
          {azioni}
        </header>
      ) : null}
      <div style={{ padding: senzaPadding ? 0 : 20 }}>{children}</div>
    </section>
  );
}

/** Il numero che conta, con la sua etichetta e una nota sotto. */
export function Kpi({
  etichetta,
  valore,
  nota,
}: {
  etichetta: string;
  valore: ReactNode;
  nota?: ReactNode;
}) {
  return (
    <div style={{ ...SUPERFICIE, padding: 16 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: ".06em",
          textTransform: "uppercase",
          color: "var(--text-secondary)",
        }}
      >
        {etichetta}
      </div>
      <div style={{ marginTop: 6, fontSize: 26, fontWeight: 700 }}>{valore}</div>
      {nota ? (
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--text-secondary)" }}>{nota}</div>
      ) : null}
    </div>
  );
}

/** Griglia di KPI o di riquadri: quante colonne, e a capo da sole. */
export function Griglia({ colonne, children }: { colonne: number; children: ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${colonne}, minmax(0, 1fr))`,
        gap: 16,
        marginBottom: 16,
      }}
    >
      {children}
    </div>
  );
}

/* ---------- stato ---------- */

const TONI: Record<string, [string, string]> = {
  verde: ["var(--color-success)", "#ffffff"],
  giallo: ["var(--color-warning)", "var(--dark)"],
  rosso: ["var(--color-error)", "#ffffff"],
  blu: ["var(--color-info)", "#ffffff"],
  arancio: ["var(--color-attention)", "#ffffff"],
  grigio: ["var(--background-tertiary)", "var(--dark)"],
};

/** La pillola di stato: colore pieno, testo corto, mai una frase. */
export function Badge({ tono = "grigio", children }: { tono?: string; children: ReactNode }) {
  const [sfondo, colore] = TONI[tono] ?? TONI.grigio;
  return (
    <span
      style={{
        display: "inline-block",
        borderRadius: "var(--radius-full)",
        padding: "1px 9px",
        fontSize: 12,
        fontWeight: 700,
        background: sfondo,
        color: colore,
      }}
    >
      {children}
    </span>
  );
}

/** Quanto del budget è stato consumato: barra + pillola. Verde fin che c'è
 *  margine, gialla dall'80%, rossa quando si sfonda. */
export function BarraConsumo({ quota }: { quota: number | null | undefined }) {
  if (quota === null || quota === undefined) return <span>—</span>;
  const perc = Math.min(100, Math.round(quota * 100));
  const tono = quota > 1 ? "rosso" : quota >= 0.8 ? "giallo" : "verde";
  const colore = TONI[tono][0];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          height: 8,
          width: 110,
          borderRadius: 999,
          background: "var(--background-secondary)",
          border: "1px solid var(--border-color)",
          overflow: "hidden",
          flexShrink: 0,
        }}
      >
        <div style={{ height: "100%", width: `${perc}%`, background: colore }} />
      </div>
      <Badge tono={tono}>
        {new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1 }).format(perc)}%
      </Badge>
    </div>
  );
}

export function Stato({ children }: { children: ReactNode }) {
  return (
    <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-secondary)" }}>
      {children}
    </div>
  );
}

export function Errore({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        border: "1px solid var(--color-error)",
        borderRadius: "var(--radius)",
        padding: "12px 16px",
        fontSize: 14,
        color: "var(--color-error)",
        fontWeight: 700,
      }}
    >
      {children}
    </div>
  );
}

/* ---------- azioni ---------- */

type VarianteBottone = "primario" | "normale" | "pericolo";

const VARIANTE_DS = {
  primario: "primary",
  normale: "outline",
  pericolo: "outlineError",
} as const;

/** Il bottone dell'Admin. `type="button"` è il default e non un dettaglio: molti
 *  di questi bottoni vivono dentro un `<form>` (EntitaForm, le righe di
 *  CampiSchema) e senza di esso il browser li tratterebbe come invio. Chi vuole
 *  l'invio lo chiede a voce alta con `type="submit"`. */
export function Bottone({
  variante = "normale",
  type = "button",
  children,
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: VarianteBottone }) {
  return (
    <Button variant={VARIANTE_DS[variante]} size="sm" type={type} {...resto}>
      {children}
    </Button>
  );
}

/** Un bottone che porta in un'altra pagina. Un `<Link>` con dentro un `<button>`
 *  non è HTML valido (e il click resta ambiguo): qui la navigazione è l'azione
 *  del bottone, non il contorno. */
export function BottoneVerso({
  a,
  variante = "normale",
  children,
}: {
  a: string;
  variante?: VarianteBottone;
  children: ReactNode;
}) {
  const naviga = useNavigate();
  const da = usePercorsoCorrente();
  return (
    <Bottone variante={variante} onClick={() => naviga(a, { state: { da } })}>
      {children}
    </Bottone>
  );
}

/** Un `<Link>` che lascia la provenienza, come `BottoneVerso`: la pagina di
 *  arrivo può così tornare qui e non alla sua rotta di ripiego. */
export function LinkVerso({
  a,
  className,
  style,
  children,
}: {
  a: string;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const da = usePercorsoCorrente();
  return (
    <Link to={a} state={{ da }} className={className} style={style}>
      {children}
    </Link>
  );
}

/** Il ritorno alla pagina di sopra: un bottone con la freccia, non un link di
 *  testo. Sta in cima alla pagina, dentro `IntestazionePagina`.
 *
 *  Se c'è una provenienza torna indietro *nella history* (`-1`) invece di
 *  spingere una voce nuova: altrimenti la pila cresce (elenco → dettaglio →
 *  elenco) e il tasto Indietro del browser riporta dentro il dettaglio appena
 *  lasciato. Senza provenienza — URL aperto a mano, ricarica in una scheda
 *  nuova — non c'è nulla da cui tornare e si spinge il ripiego `a`. */
export function BottoneIndietro({ a, etichetta }: { a: string; etichetta?: string }) {
  const naviga = useNavigate();
  const da = useProvenienza();
  // Quando si torna dove porterebbe comunque il ripiego, l'etichetta passata
  // dalla pagina è più precisa di quella dedotta dalla rotta ("Fatture" invece
  // del generico "Dati"): si deduce solo per una provenienza diversa.
  const altrove = da !== null && da.split("?")[0] !== a;
  return (
    <Button
      variant="transparent"
      size="sm"
      type="button"
      icon={{ data: ArrowLeftIcon }}
      onClick={() => (da !== null ? naviga(-1) : naviga(a))}
    >
      {altrove ? etichettaPercorso(da) : etichetta ?? "Indietro"}
    </Button>
  );
}

/* ---------- impaginazione ---------- */

/** Intestazione di pagina: titolo, eventuale ritorno, azioni a destra. */
export function IntestazionePagina({
  titolo,
  indietro,
  etichettaIndietro,
  accanto,
  sotto,
  azioni,
}: {
  titolo: ReactNode;
  indietro?: string;
  etichettaIndietro?: string;
  accanto?: ReactNode;
  sotto?: ReactNode;
  azioni?: ReactNode;
}) {
  return (
    <div style={{ marginBottom: sotto ? 12 : 24 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
        {indietro ? <BottoneIndietro a={indietro} etichetta={etichettaIndietro} /> : null}
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>{titolo}</h1>
        {accanto ? (
          <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>{accanto}</span>
        ) : null}
        {azioni ? (
          <div
            style={{
              marginLeft: "auto",
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: 8,
            }}
          >
            {azioni}
          </div>
        ) : null}
      </div>
      {sotto ? (
        <p style={{ margin: "4px 0 0", fontSize: 14, color: "var(--text-secondary)" }}>{sotto}</p>
      ) : null}
    </div>
  );
}

/** Riga di un elenco dentro una card: cosa a sinistra, quando a destra. */
export function RigaElenco({
  ultima = false,
  children,
}: {
  ultima?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        padding: "12px 0",
        borderBottom: ultima ? undefined : "1px solid var(--border-color)",
      }}
    >
      {children}
    </div>
  );
}

/** Riquadro cliccabile: usato dove si scelgono tipi di dato o entità. */
export function Riquadro({
  titolo,
  sotto,
  badge,
  onClick,
  a,
}: {
  titolo: ReactNode;
  sotto?: ReactNode;
  badge?: ReactNode;
  onClick?: () => void;
  a?: string;
}) {
  const contenuto = (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 16, fontWeight: 700 }}>
        {titolo}
        {badge}
      </div>
      {sotto ? (
        <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-secondary)" }}>{sotto}</div>
      ) : null}
    </>
  );
  const stile = {
    display: "block",
    textAlign: "left",
    cursor: "pointer",
    font: "inherit",
    color: "inherit",
    textDecoration: "none",
    background: "var(--background-primary)",
    border: "1px solid var(--border-color)",
    borderRadius: "var(--radius)",
    padding: 16,
  } as const;

  if (a) {
    return (
      <LinkVerso a={a} className="wf-riquadro" style={stile}>
        {contenuto}
      </LinkVerso>
    );
  }
  return (
    <button type="button" className="wf-riquadro" style={stile} onClick={onClick}>
      {contenuto}
    </button>
  );
}

/** Tabella del design system, con le righe a bande. */
export function Tabella<R extends TableRow>({
  colonne,
  righe,
  righePerPagina,
}: {
  colonne: TableColumn<R>[];
  righe: R[];
  righePerPagina?: number;
}) {
  return (
    <Table<R>
      columns={colonne}
      data={righe}
      striped
      showPagination={righePerPagina !== undefined && righe.length > righePerPagina}
      rowsPerPage={righePerPagina}
    />
  );
}

/** Numeri in colonna: sempre allineati, cifre della stessa larghezza. */
export const NUMERI = { fontVariantNumeric: "tabular-nums" } as const;

/** Identificativi e frammenti di codice: carattere monospaziato del brand. */
export const MONO = { fontFamily: "var(--font-mono), monospace" } as const;

/** L'etichetta di un campo di form, in maiuscoletto, con l'asterisco se serve. */
export function EtichettaCampo({
  children,
  obbligatorio = false,
}: {
  children: ReactNode;
  obbligatorio?: boolean;
}) {
  return (
    <div
      style={{
        marginBottom: 6,
        fontSize: 12,
        fontWeight: 700,
        letterSpacing: ".06em",
        textTransform: "uppercase",
        color: "var(--text-secondary)",
      }}
    >
      {children} {obbligatorio ? <span style={{ color: "var(--color-error)" }}>*</span> : null}
    </div>
  );
}

/** Un blocco di codice: JSON o messaggi di errore tecnici. */
export function Codice({ children }: { children: ReactNode }) {
  return (
    <pre
      style={{
        margin: 0,
        overflow: "auto",
        borderRadius: "var(--radius)",
        background: "var(--dark)",
        padding: 12,
        fontFamily: "var(--font-mono), monospace",
        fontSize: 12,
        color: "#e6e6e6",
      }}
    >
      {children}
    </pre>
  );
}

/** Suggerimento cliccabile a pillola: gli esempi di domanda, i filtri. */
export function Chip({
  attivo = false,
  onClick,
  children,
}: {
  attivo?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className="wf-chip"
      onClick={onClick}
      style={{
        cursor: "pointer",
        font: "inherit",
        fontSize: 12,
        color: attivo ? "var(--text-on-primary)" : "var(--text-secondary)",
        background: attivo ? "var(--color-primary)" : "var(--background-primary)",
        border: `1px solid ${attivo ? "var(--color-primary)" : "var(--border-color)"}`,
        borderRadius: "var(--radius-full)",
        padding: "5px 12px",
      }}
    >
      {children}
    </button>
  );
}

/** La targhetta del tipo di documento davanti a un identificativo. */
export function Targhetta({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        display: "inline-block",
        marginRight: 8,
        borderRadius: "var(--radius-sm)",
        background: "var(--background-secondary)",
        border: "1px solid var(--border-color)",
        padding: "1px 6px",
        fontSize: 10,
        fontWeight: 700,
        textTransform: "uppercase",
        color: "var(--text-secondary)",
      }}
    >
      {children}
    </span>
  );
}

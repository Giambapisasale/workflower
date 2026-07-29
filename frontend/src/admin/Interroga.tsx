import { type FormEvent, useState } from "react";
import { ErroreApi } from "../shared/api";
import { admin, type EsitoAsk } from "./api";
import { Input } from "../ds";
import type { TableColumn, TableRow } from "../ds";
import { Bottone, Card, Chip, Codice, Errore, NUMERI, Stato, Tabella } from "./ui";

const ESEMPI = [
  "Quanto abbiamo speso per ogni cantiere?",
  "Quali fatture hanno una ritenuta d'acconto?",
  "Totale IVA di tutte le fatture",
];

function cella(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return new Intl.NumberFormat("it-IT").format(v);
  return String(v);
}

export default function Interroga() {
  const [domanda, setDomanda] = useState("");
  const [esito, setEsito] = useState<EsitoAsk | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(false);

  async function chiedi(testo: string) {
    if (!testo.trim()) return;
    setInCorso(true);
    setErrore(null);
    setEsito(null);
    try {
      setEsito(await admin.chiediSql(testo.trim()));
    } catch (err) {
      setErrore(err instanceof ErroreApi ? err.message : "Non sono riuscito a rispondere");
    } finally {
      setInCorso(false);
    }
  }

  function invia(e: FormEvent) {
    e.preventDefault();
    chiedi(domanda);
  }

  const nomiColonne = esito && esito.rows.length ? Object.keys(esito.rows[0]) : [];
  const colonne: TableColumn<TableRow>[] = nomiColonne.map((c) => ({
    title: c,
    dataIndex: c,
    render: (_v, r) => <span style={NUMERI}>{cella(r[c])}</span>,
  }));
  const righe: TableRow[] = (esito?.rows ?? []).map((r, i) => ({ ...r, id: i }));

  return (
    <>
      <Card titolo="Interroga i dati">
        <form onSubmit={invia} style={{ display: "flex", gap: 8 }}>
          <Input
            placeholder="Fai una domanda sui costi, in italiano…"
            value={domanda}
            onChange={(e) => setDomanda(e.target.value)}
          />
          <Bottone variante="primario" type="submit" disabled={inCorso}>
            {inCorso ? "Interrogo…" : "Chiedi"}
          </Bottone>
        </form>
        <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
          {ESEMPI.map((e) => (
            <Chip
              key={e}
              onClick={() => {
                setDomanda(e);
                chiedi(e);
              }}
            >
              {e}
            </Chip>
          ))}
        </div>
      </Card>

      {errore ? <Errore>{errore}</Errore> : null}

      {esito ? (
        <>
          <Card titolo="SQL generato">
            <Codice>{esito.sql}</Codice>
          </Card>
          <Card titolo={`Risultato (${esito.rows.length} righe)`}>
            {esito.rows.length === 0 ? (
              <Stato>Nessun risultato.</Stato>
            ) : (
              <Tabella colonne={colonne} righe={righe} righePerPagina={25} />
            )}
          </Card>
        </>
      ) : null}
    </>
  );
}

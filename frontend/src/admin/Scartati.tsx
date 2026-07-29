/** Gli inserimenti scartati: l'archivio da cui si ripristina.
 *
 * Uno scarto non cancella niente — sposta il documento fuori dai conti. Questa
 * pagina è la prova che sia vero: qui si vede *cosa* è stato scartato, *perché* e
 * da chi, e da qui si torna indietro. */

import { useState } from "react";
import { admin } from "./api";
import { ErroreApi } from "../shared/api";
import { dataBreve, useCarica } from "./formato";
import {
  Badge,
  Bottone,
  Card,
  Errore,
  IntestazionePagina,
  MONO,
  Stato,
  Tabella,
} from "./ui";
import type { TableColumn, TableRow } from "../ds";

type RigaScarto = TableRow & {
  etichetta: string;
  titolo: string | null;
  motivo: string | null;
  scartato_da: string | null;
  scartato_il: string | null;
  era_validato: boolean;
  erp_id: string | null;
};

export default function Scartati() {
  const { dati, errore, inCorso, ricarica } = useCarica(() => admin.scartati());
  const [inAzione, setInAzione] = useState<string | null>(null);
  const [erroreAzione, setErroreAzione] = useState<string | null>(null);

  async function ripristina(id: string) {
    setInAzione(id);
    setErroreAzione(null);
    try {
      await admin.ripristina(id);
      ricarica();
    } catch (e) {
      setErroreAzione(e instanceof ErroreApi ? e.message : "Ripristino non riuscito.");
    } finally {
      setInAzione(null);
    }
  }

  if (inCorso) return <Stato>Carico gli scartati…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const scartati = dati ?? [];

  const colonne: TableColumn<RigaScarto>[] = [
    {
      title: "Documento",
      dataIndex: "id",
      render: (_v, r) => (
        <div>
          <div style={{ ...MONO, fontSize: 12 }}>{r.id}</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {r.etichetta}
            {r.titolo ? ` · ${r.titolo}` : ""}
          </div>
          {r.era_validato || r.erp_id ? (
            <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
              {r.era_validato ? <Badge tono="giallo">era validato</Badge> : null}
              {r.erp_id ? <Badge tono="grigio">era in contabilità</Badge> : null}
            </div>
          ) : null}
        </div>
      ),
    },
    { title: "Motivo", dataIndex: "motivo", render: (_v, r) => r.motivo ?? "—" },
    {
      title: "Scartato da",
      dataIndex: "scartato_da",
      render: (_v, r) => (
        <span style={{ color: "var(--text-secondary)" }}>{r.scartato_da ?? "—"}</span>
      ),
    },
    {
      title: "Quando",
      dataIndex: "scartato_il",
      render: (_v, r) => (
        <span style={{ whiteSpace: "nowrap", color: "var(--text-secondary)" }}>
          {dataBreve(r.scartato_il)}
        </span>
      ),
    },
    {
      title: "",
      dataIndex: "azione",
      render: (_v, r) => {
        const id = String(r.id);
        return (
          <Bottone onClick={() => ripristina(id)} disabled={inAzione === id}>
            {inAzione === id ? "Ripristino…" : "Ripristina"}
          </Bottone>
        );
      },
    },
  ];

  return (
    <>
      <IntestazionePagina titolo="Scartati" indietro="/admin/dati" etichettaIndietro="Dati" />

      <Card titolo="Inserimenti scartati">
        <p
          style={{
            margin: "0 0 16px",
            fontSize: 14,
            color: "var(--text-secondary)",
            textWrap: "pretty",
          }}
        >
          Documenti che l'ufficio ha ripudiato: non contano nei costi, non sono in revisione e
          non arrivano in contabilità. <strong>Non sono cancellati</strong> — <em>Ripristina</em>{" "}
          li rimette dov'erano. Ogni scarto e ogni ripristino è un commit nel repo dati.
        </p>

        {scartati.length === 0 ? (
          <Stato>Nessun inserimento scartato.</Stato>
        ) : (
          <Tabella
            colonne={colonne}
            righe={scartati.map((s) => ({ ...s }) as RigaScarto)}
            righePerPagina={20}
          />
        )}

        {erroreAzione ? (
          <div style={{ marginTop: 16 }}>
            <Errore>{erroreAzione}</Errore>
          </div>
        ) : null}
      </Card>
    </>
  );
}

/** Confronto computo/consuntivo (M9): previsto vs speso, per cantiere e per voce. */

import { useMemo, useState } from "react";
import { admin, type ScostamentoVoce } from "./api";
import { euro, percento, useCarica } from "./formato";
import {
  BarraConsumo,
  Card,
  Errore,
  Griglia,
  IntestazionePagina,
  Kpi,
  MONO,
  NUMERI,
  Stato,
  Tabella,
} from "./ui";
import type { TableColumn, TableRow } from "../ds";

type RigaVoce = TableRow & ScostamentoVoce;

const COLONNE: TableColumn<RigaVoce>[] = [
  {
    title: "Voce",
    dataIndex: "descrizione",
    render: (_v, r) => (
      <span>
        <span style={{ ...MONO, fontSize: 12, color: "var(--text-secondary)" }}>
          {r.codice ?? r.voce_id}
        </span>{" "}
        {r.descrizione}
      </span>
    ),
  },
  {
    title: "Categoria",
    dataIndex: "categoria",
    render: (_v, r) => (
      <span style={{ color: "var(--text-secondary)" }}>{r.categoria ?? "—"}</span>
    ),
  },
  {
    title: "Previsto",
    dataIndex: "previsto",
    render: (_v, r) => <span style={NUMERI}>{euro(r.previsto)}</span>,
  },
  {
    title: "Speso",
    dataIndex: "consuntivo",
    render: (_v, r) => <span style={NUMERI}>{euro(r.consuntivo)}</span>,
  },
  { title: "Consumo", dataIndex: "quota", render: (_v, r) => <BarraConsumo quota={r.quota} /> },
];

export default function Scostamenti() {
  const { dati, errore, inCorso } = useCarica(() => admin.scostamenti());
  const [scelto, setScelto] = useState<string | null>(null);

  const cantieri = dati?.per_cantiere ?? [];
  const attivo = scelto ?? cantieri[0]?.cantiere_id ?? null;
  const voci: ScostamentoVoce[] = useMemo(
    () => (dati?.voci ?? []).filter((v) => v.cantiere_id === attivo),
    [dati, attivo],
  );

  if (inCorso) return <Stato>Carico gli scostamenti…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  if (cantieri.length === 0)
    return <Stato>Nessun computo caricato: non c'è ancora un preventivo con cui confrontare.</Stato>;

  return (
    <>
      <IntestazionePagina titolo="Scostamenti" />

      <Griglia colonne={3}>
        {cantieri.map((c) => (
          <button
            key={c.cantiere_id}
            type="button"
            onClick={() => setScelto(c.cantiere_id)}
            style={{
              textAlign: "left",
              cursor: "pointer",
              font: "inherit",
              color: "inherit",
              background: "var(--background-primary)",
              borderRadius: "var(--radius-lg)",
              padding: 16,
              border:
                c.cantiere_id === attivo
                  ? "2px solid var(--color-primary)"
                  : "1px solid var(--border-color)",
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                letterSpacing: ".06em",
                textTransform: "uppercase",
                color: "var(--text-secondary)",
              }}
            >
              {c.cantiere ?? c.cantiere_id}
            </div>
            <div style={{ marginTop: 6, fontSize: 20, fontWeight: 700 }}>{euro(c.consuntivo)}</div>
            <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-secondary)" }}>
              abbinato su {euro(c.previsto)} previsti ·{" "}
              {percento(c.previsto ? c.consuntivo / c.previsto : null)}
            </div>
          </button>
        ))}
      </Griglia>

      <div style={{ marginBottom: 8 }}>
        <Griglia colonne={3}>
          <Kpi
            etichetta="Previsto (computo)"
            valore={euro(voci.reduce((s, v) => s + v.previsto, 0))}
          />
          <Kpi
            etichetta="Consuntivo abbinato"
            valore={euro(voci.reduce((s, v) => s + v.consuntivo, 0))}
          />
          <Kpi
            etichetta="Voci sopra soglia"
            valore={voci.filter((v) => v.quota !== null && v.quota >= 0.8).length}
            nota="consumo ≥ 80% del previsto"
          />
        </Griglia>
      </div>

      <Card titolo="Voci di computo — previsto vs speso">
        {voci.length === 0 ? (
          <Stato>Questo cantiere non ha voci di computo.</Stato>
        ) : (
          <Tabella
            colonne={COLONNE}
            righe={voci.map((v) => ({ ...v, id: v.voce_id }) as RigaVoce)}
            righePerPagina={25}
          />
        )}
      </Card>
    </>
  );
}

/** Registro di cantiere (M10): il fascicolo consolidato — spesa, ore, avanzamento. */

import { Link, useParams } from "react-router-dom";
import { admin } from "./api";
import { dataBreve, euro, percento, useCarica } from "./formato";
import {
  Badge,
  Bottone,
  Card,
  Errore,
  Griglia,
  IntestazionePagina,
  Kpi,
  NUMERI,
  RigaElenco,
  Stato,
  Tabella,
} from "./ui";
import type { TableColumn, TableRow } from "../ds";

function statoBadge(stato: string) {
  const tono = stato === "validato" ? "verde" : stato === "errore" ? "rosso" : "giallo";
  return <Badge tono={tono}>{stato}</Badge>;
}

type RigaFattura = TableRow & {
  numero: string | null;
  fornitore: string | null;
  data: string | null;
  totale: number | null;
  stato: string;
};

const COL_FATTURE: TableColumn<RigaFattura>[] = [
  {
    title: "Numero",
    dataIndex: "numero",
    render: (_v, r) => <Link to={`/admin/revisione/${r.id}`}>{r.numero ?? r.id}</Link>,
  },
  { title: "Fornitore", dataIndex: "fornitore", render: (_v, r) => r.fornitore ?? "—" },
  {
    title: "Data",
    dataIndex: "data",
    render: (_v, r) => <span style={{ color: "var(--text-secondary)" }}>{dataBreve(r.data)}</span>,
  },
  {
    title: "Totale",
    dataIndex: "totale",
    render: (_v, r) => <span style={NUMERI}>{euro(r.totale)}</span>,
  },
  { title: "Stato", dataIndex: "stato", render: (_v, r) => statoBadge(r.stato) },
];

export default function Cantiere() {
  const { id = "" } = useParams();
  const { dati, errore, inCorso } = useCarica(() => admin.registro(id), [id]);
  if (inCorso) return <Stato>Carico il registro…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Cantiere non trovato"}</Errore>;

  const c = dati.cantiere as Record<string, unknown>;
  const t = dati.totali;
  const scost = t.scostamento;

  return (
    <>
      <IntestazionePagina
        titolo={String(c.nome ?? id)}
        indietro="/admin"
        etichettaIndietro="Cruscotto"
        accanto={String(c.comune ?? "")}
        azioni={<Bottone onClick={() => admin.scaricaReport(id)}>Scarica Excel</Bottone>}
        sotto={
          <>
            Committente: <b style={{ color: "var(--text-primary)" }}>{String(c.committente ?? "—")}</b>{" "}
            · Capocantiere:{" "}
            <b style={{ color: "var(--text-primary)" }}>{String(c.capocantiere ?? "—")}</b>
          </>
        }
      />

      <div style={{ marginTop: 24, marginBottom: 8 }}>
        <Griglia colonne={5}>
          <Kpi
            etichetta="Speso (fatture)"
            valore={euro(t.speso_fatture)}
            nota={`su ${euro(t.budget)} · ${percento(t.quota_budget)}`}
          />
          <Kpi
            etichetta="Ore manodopera"
            valore={t.ore_totali ?? 0}
            nota={`${euro(t.costo_manodopera)} · ${t.giornate} giornate`}
          />
          <Kpi etichetta="Costo mezzi / noli" valore={euro(t.costo_mezzi ?? 0)} />
          <Kpi
            etichetta="Avanzamento (SAL)"
            valore={t.avanzamento !== null ? `${t.avanzamento}%` : "—"}
          />
          <Kpi
            etichetta="Scostamento computo"
            valore={scost ? euro(scost.consuntivo_abbinato) : "—"}
            nota={scost ? `previsto ${euro(scost.previsto)}` : "nessun computo"}
          />
        </Griglia>
      </div>

      <Card titolo={`Fatture (${dati.fatture.length})`}>
        {dati.fatture.length === 0 ? (
          <Stato>Nessuna fattura su questo cantiere.</Stato>
        ) : (
          <Tabella
            colonne={COL_FATTURE}
            righe={dati.fatture.map((f) => ({ ...f }) as RigaFattura)}
            righePerPagina={25}
          />
        )}
      </Card>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: 24,
        }}
      >
        <Card titolo={`DDT (${dati.ddt.length})`}>
          {dati.ddt.length === 0 ? (
            <Stato>Nessun DDT.</Stato>
          ) : (
            <div style={{ fontSize: 14 }}>
              {dati.ddt.map((d, i) => (
                <RigaElenco key={d.id} ultima={i === dati.ddt.length - 1}>
                  <span>
                    {d.numero ?? d.id} · {d.fornitore ?? "—"}
                  </span>
                  <span style={{ color: "var(--text-secondary)" }}>
                    {dataBreve(d.data)} · {d.n_righe} righe
                  </span>
                </RigaElenco>
              ))}
            </div>
          )}
        </Card>

        <Card titolo={`SAL (${dati.sal.length})`}>
          {dati.sal.length === 0 ? (
            <Stato>Nessuno stato avanzamento.</Stato>
          ) : (
            <div style={{ fontSize: 14 }}>
              {dati.sal.map((s, i) => (
                <RigaElenco key={s.id} ultima={i === dati.sal.length - 1}>
                  <span>SAL n. {s.numero ?? s.id}</span>
                  <span style={{ color: "var(--text-secondary)" }}>
                    {dataBreve(s.data)} · {s.percentuale_avanzamento}% ·{" "}
                    {euro(s.importo_progressivo)}
                  </span>
                </RigaElenco>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

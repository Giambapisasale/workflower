import { Link } from "react-router-dom";
import { admin } from "./api";
import { euro, useCarica } from "./formato";
import {
  BarraConsumo,
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

type RigaCantiere = TableRow & {
  cantiere: string;
  cantiere_id: string;
  n_fatture: number;
  speso: number;
  budget: number | null;
  quota_budget: number | null;
};

type RigaFornitore = TableRow & {
  fornitore: string;
  fornitore_id: string | null;
  n_fatture: number;
  speso: number;
};

const COL_CANTIERI: TableColumn<RigaCantiere>[] = [
  {
    title: "Cantiere",
    dataIndex: "cantiere",
    render: (_v, r) => (
      <Link to={`/admin/cantiere/${r.cantiere_id}`} style={{ fontWeight: 700 }}>
        {r.cantiere}
      </Link>
    ),
  },
  { title: "Fatture", dataIndex: "n_fatture", render: (_v, r) => <span style={NUMERI}>{r.n_fatture}</span> },
  { title: "Speso", dataIndex: "speso", render: (_v, r) => <span style={NUMERI}>{euro(r.speso)}</span> },
  {
    title: "Budget",
    dataIndex: "budget",
    render: (_v, r) => (
      <span style={{ ...NUMERI, color: "var(--text-secondary)" }}>{euro(r.budget)}</span>
    ),
  },
  {
    title: "Consumo",
    dataIndex: "quota_budget",
    render: (_v, r) => <BarraConsumo quota={r.quota_budget} />,
  },
  {
    title: "Gestisci",
    dataIndex: "gestisci",
    render: (_v, r) => (
      <Link to={`/admin/dati/cantiere/${r.cantiere_id}`} style={{ fontSize: 12 }}>
        modifica
      </Link>
    ),
  },
];

const COL_FORNITORI: TableColumn<RigaFornitore>[] = [
  { title: "Fornitore", dataIndex: "fornitore" },
  { title: "Fatture", dataIndex: "n_fatture", render: (_v, r) => <span style={NUMERI}>{r.n_fatture}</span> },
  { title: "Speso", dataIndex: "speso", render: (_v, r) => <span style={NUMERI}>{euro(r.speso)}</span> },
  {
    title: "Gestisci",
    dataIndex: "gestisci",
    render: (_v, r) =>
      r.fornitore_id ? (
        <Link to={`/admin/dati/fornitore/${r.fornitore_id}`} style={{ fontSize: 12 }}>
          modifica
        </Link>
      ) : null,
  },
];

export default function Cruscotto() {
  const { dati, errore, inCorso } = useCarica(() => admin.cruscotto());
  if (inCorso) return <Stato>Carico il cruscotto…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const t = dati.totali;
  const a = dati.attivita;

  const righeCantieri: RigaCantiere[] = dati.per_cantiere.map((c) => ({
    id: c.cantiere_id,
    cantiere_id: c.cantiere_id,
    cantiere: c.cantiere ?? c.cantiere_id,
    n_fatture: c.n_fatture,
    speso: c.speso,
    budget: c.budget,
    quota_budget: c.quota_budget,
  }));

  const righeFornitori: RigaFornitore[] = dati.per_fornitore.map((f, i) => ({
    id: f.fornitore_id ?? `f-${i}`,
    fornitore_id: f.fornitore_id,
    fornitore: f.fornitore ?? f.fornitore_id ?? "—",
    n_fatture: f.n_fatture,
    speso: f.speso,
  }));

  return (
    <>
      <IntestazionePagina
        titolo="Cruscotto"
        azioni={
          <>
            <Link to="/admin/dati/cantiere/nuovo"><Bottone>+ Cantiere</Bottone></Link>
            <Link to="/admin/dati/fornitore/nuovo"><Bottone>+ Fornitore</Bottone></Link>
            <Link to="/admin/dati/fattura/nuovo"><Bottone>+ Fattura a mano</Bottone></Link>
            <Link to="/admin/dati"><Bottone variante="primario">Gestione dati →</Bottone></Link>
          </>
        }
      />

      <Griglia colonne={4}>
        <Kpi
          etichetta="Fatture"
          valore={t.n_fatture}
          nota={<Link to="/admin/revisione">{t.da_validare} da validare →</Link>}
        />
        <Kpi
          etichetta="Totale documenti"
          valore={euro(t.totale)}
          nota={`imponibile ${euro(t.imponibile)}`}
        />
        <Kpi etichetta="IVA" valore={euro(t.iva)} />
        <Kpi etichetta="Ritenute d'acconto" valore={euro(t.ritenute)} />
      </Griglia>

      <div style={{ marginBottom: 8 }}>
        <Griglia colonne={5}>
          <Kpi etichetta="DDT" valore={a.n_ddt} nota="documenti di trasporto" />
          <Kpi etichetta="SAL" valore={a.n_sal} nota="stati avanzamento" />
          <Kpi etichetta="Ore manodopera" valore={a.ore_totali} nota="da rapportini" />
          <Kpi etichetta="Costo manodopera" valore={euro(a.costo_manodopera)} />
          <Kpi etichetta="Costo mezzi" valore={euro(a.costo_mezzi)} nota="noli e costi da fatture" />
        </Griglia>
      </div>

      {dati.scadenze.length > 0 ? (
        <Card titolo="Scadenze">
          {dati.scadenze.map((s, i) => (
            <RigaElenco key={s.id} ultima={i === dati.scadenze.length - 1}>
              <div style={{ minWidth: 0 }}>
                <b>{s.descrizione}</b>
                {s.mezzo ?? s.cantiere ? (
                  <span
                    style={{ marginLeft: 8, fontSize: 12, color: "var(--text-secondary)" }}
                  >
                    {s.mezzo ?? s.cantiere}
                  </span>
                ) : null}
              </div>
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ ...NUMERI, color: "var(--text-secondary)" }}>{s.data_scadenza}</div>
                <div
                  style={{
                    fontSize: 12,
                    color: s.giorni < 0 ? "var(--color-error)" : "var(--color-attention)",
                  }}
                >
                  {s.giorni < 0 ? `scaduta da ${-s.giorni} gg` : `tra ${s.giorni} gg`}
                </div>
              </div>
            </RigaElenco>
          ))}
        </Card>
      ) : null}

      <Card
        titolo="Costi per cantiere"
        azioni={<Bottone onClick={() => admin.scaricaReport()}>Scarica report Excel</Bottone>}
      >
        <Tabella colonne={COL_CANTIERI} righe={righeCantieri} />
      </Card>

      <Card titolo="Fornitori principali">
        <Tabella colonne={COL_FORNITORI} righe={righeFornitori} righePerPagina={10} />
      </Card>
    </>
  );
}

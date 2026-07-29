import { admin, ETICHETTA_TIPO } from "./api";
import { dataBreve, euro, percento, useCarica } from "./formato";
import {
  Badge,
  BottoneVerso,
  Card,
  Errore,
  MONO,
  NUMERI,
  Stato,
  Tabella,
  Targhetta,
} from "./ui";
import type { TableColumn, TableRow } from "../ds";

function tono(c: number | null): string {
  if (c === null) return "grigio";
  return c >= 0.9 ? "verde" : c >= 0.75 ? "giallo" : "rosso";
}

type RigaCoda = TableRow & {
  tipo: string;
  fornitore: string | null;
  cantiere: string | null;
  totale: number | null;
  data: string | null;
  confidence_min: number | null;
};

const COLONNE: TableColumn<RigaCoda>[] = [
  {
    title: "Documento",
    dataIndex: "id",
    render: (_v, r) => (
      <span>
        <Targhetta>{ETICHETTA_TIPO[r.tipo] ?? r.tipo}</Targhetta>
        <span style={{ ...MONO, fontSize: 12, color: "var(--text-secondary)" }}>{r.id}</span>
      </span>
    ),
  },
  { title: "Fornitore", dataIndex: "fornitore", render: (_v, r) => r.fornitore ?? "—" },
  { title: "Cantiere", dataIndex: "cantiere", render: (_v, r) => r.cantiere ?? "—" },
  {
    title: "Totale",
    dataIndex: "totale",
    render: (_v, r) => <span style={NUMERI}>{euro(r.totale)}</span>,
  },
  { title: "Data", dataIndex: "data", render: (_v, r) => dataBreve(r.data) },
  {
    title: "Confidenza",
    dataIndex: "confidence_min",
    render: (_v, r) => <Badge tono={tono(r.confidence_min)}>{percento(r.confidence_min)}</Badge>,
  },
  {
    title: "",
    dataIndex: "azione",
    render: (_v, r) => (
      <BottoneVerso a={`/admin/revisione/${r.id}`} variante="primario">
        Rivedi
      </BottoneVerso>
    ),
  },
];

export default function Revisione() {
  const { dati, errore, inCorso } = useCarica(() => admin.codaRevisione());
  if (inCorso) return <Stato>Carico la coda…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const coda = dati ?? [];

  return (
    <Card titolo={`Bozze da rivedere (${coda.length})`}>
      {coda.length === 0 ? (
        <Stato>Niente da rivedere: tutte le bozze sono validate.</Stato>
      ) : (
        <Tabella
          colonne={COLONNE}
          righe={coda.map((r) => ({ ...r }) as RigaCoda)}
          righePerPagina={20}
        />
      )}
    </Card>
  );
}

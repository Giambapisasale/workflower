/** Guscio della modalità Admin: sidebar, gate di ruolo, routing delle pagine. */

import { useCallback, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowUpIcon,
  BellIcon,
  CalendarIcon,
  CheckCircledIcon,
  ClipboardCopyIcon,
  DotsHorizontalIcon,
  FileIcon,
  GearIcon,
  HomeIcon,
  InfoCircledIcon,
  Link2Icon,
  MagnifyingGlassIcon,
  TriangleRightIcon,
} from "@radix-ui/react-icons";
import {
  chiudiSessione,
  salvaSessione,
  sessioneCorrente,
  type Sessione,
} from "../shared/api";
import { Button, Sidebar } from "../ds";
import type { Icona } from "../ds";
import AdminLogin from "./AdminLogin";
import Cantiere from "./Cantiere";
import Cruscotto from "./Cruscotto";
import Dataset from "./Dataset";
import Dati from "./Dati";
import Diagnosi from "./Diagnosi";
import EntitaForm from "./EntitaForm";
import EntitaLista from "./EntitaLista";
import Erp from "./Erp";
import Interroga from "./Interroga";
import Log from "./Log";
import Revisione from "./Revisione";
import RevisioneDettaglio from "./RevisioneDettaglio";
import Run from "./Run";
import Scartati from "./Scartati";
import Scostamenti from "./Scostamenti";
import Segnalazioni from "./Segnalazioni";
import SkillsTools from "./SkillsTools";
import Workflows from "./Workflows";

type Voce = {
  chiave: string;
  a: string;
  etichetta: string;
  icona: Icona;
  /** Altre rotte che devono tenere accesa questa voce. */
  anche?: string[];
};

type Sezione = {
  titolo: string;
  voci: Voce[];
};

/** Due menu separati: il lavoro quotidiano sui dati del cantiere sopra, la
 *  manutenzione tecnica del sistema sotto — chi entra per validare fatture non
 *  deve attraversare workflow, log e diagnosi per orientarsi. */
const SEZIONI: Sezione[] = [
  {
    titolo: "Operatività",
    voci: [
      { chiave: "cruscotto", a: "/admin", etichetta: "Cruscotto", icona: HomeIcon, anche: ["/admin/cantiere"] },
      { chiave: "dati", a: "/admin/dati", etichetta: "Dati", icona: FileIcon },
      { chiave: "scostamenti", a: "/admin/scostamenti", etichetta: "Scostamenti", icona: ArrowUpIcon },
      { chiave: "revisione", a: "/admin/revisione", etichetta: "Revisione", icona: CheckCircledIcon },
      { chiave: "segnalazioni", a: "/admin/segnalazioni", etichetta: "Segnalazioni", icona: BellIcon },
      { chiave: "interroga", a: "/admin/interroga", etichetta: "Interroga", icona: MagnifyingGlassIcon },
      { chiave: "erp", a: "/admin/erp", etichetta: "Contabilità", icona: Link2Icon },
    ],
  },
  {
    titolo: "Sistema",
    voci: [
      { chiave: "workflows", a: "/admin/workflows", etichetta: "Workflows", icona: GearIcon },
      { chiave: "run", a: "/admin/run", etichetta: "Run", icona: TriangleRightIcon },
      { chiave: "tools", a: "/admin/tools", etichetta: "Skills & Tools", icona: ClipboardCopyIcon },
      { chiave: "dataset", a: "/admin/dataset", etichetta: "Dataset", icona: DotsHorizontalIcon },
      { chiave: "log", a: "/admin/log", etichetta: "Log", icona: CalendarIcon },
      { chiave: "diagnosi", a: "/admin/diagnosi", etichetta: "Diagnosi", icona: InfoCircledIcon },
    ],
  },
];

/** "/admin" è acceso solo su se stesso; le altre voci anche sui figli. */
function vociAccese(percorso: string, voce: Voce): boolean {
  const rotte = [voce.a, ...(voce.anche ?? [])];
  return rotte.some((r) =>
    r === "/admin" ? percorso === "/admin" || percorso === "/admin/" : percorso.startsWith(r),
  );
}

export default function AdminApp() {
  const [sessione, setSessione] = useState<Sessione | null>(sessioneCorrente);
  const naviga = useNavigate();
  const { pathname } = useLocation();
  const esci = useCallback(() => {
    chiudiSessione();
    setSessione(null);
  }, []);

  if (sessione === null) {
    return (
      <AdminLogin
        onEntra={(nuova) => {
          salvaSessione(nuova);
          setSessione(nuova);
        }}
      />
    );
  }

  if (sessione.utente.ruolo !== "admin") {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 16,
          background: "var(--background-secondary)",
          padding: 24,
          textAlign: "center",
        }}
      >
        <p style={{ margin: 0, fontSize: 18 }}>
          Questa è l'area dell'ufficio. Il tuo accesso è da operatore.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Button
            variant="primary"
            size="md"
            type="button"
            onClick={() => {
              window.location.href = "/op";
            }}
          >
            Vai alla tua area
          </Button>
          <Button variant="outline" size="md" type="button" onClick={esci}>
            Esci
          </Button>
        </div>
      </div>
    );
  }

  const voci = SEZIONI.flatMap((sezione) => [
    { key: `sezione-${sezione.titolo}`, text: sezione.titolo, heading: true },
    ...sezione.voci.map((v) => {
      const Icona = v.icona;
      return {
        key: v.chiave,
        text: v.etichetta,
        icon: <Icona width={18} height={18} />,
        selected: vociAccese(pathname, v),
        onClick: () => naviga(v.a),
      };
    }),
  ]);

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        minWidth: 1360,
        background: "var(--background-secondary)",
      }}
    >
      {/* Sempre aperta: la navigazione dell'ufficio è la mappa del lavoro, non
          un cassetto da riaprire ogni volta. `sticky` perché il guscio scorre
          e la sidebar è alta una schermata. */}
      <Sidebar
        behaviour="permanent"
        open
        variant="primary"
        position="static"
        items={voci}
        style={{ position: "sticky", top: 0, alignSelf: "flex-start" }}
        header={<span style={{ fontSize: 17, fontWeight: 700, whiteSpace: "nowrap" }}>Workflower</span>}
        footer={
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
              fontSize: 13,
              color: "var(--text-secondary)",
            }}
          >
            <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
              {sessione.utente.nome}
            </span>
            <Button variant="outline" size="sm" type="button" onClick={esci}>
              Esci
            </Button>
          </div>
        }
      />

      <main style={{ flex: 1, minWidth: 0, padding: "24px 28px 48px" }}>
        <Routes>
          <Route index element={<Cruscotto />} />
          <Route path="dati" element={<Dati />} />
          {/* prima di dati/:tipo, altrimenti "scartati" sarebbe letto come un tipo */}
          <Route path="dati/scartati" element={<Scartati />} />
          <Route path="dati/:tipo" element={<EntitaLista />} />
          <Route path="dati/:tipo/nuovo" element={<EntitaForm />} />
          <Route path="dati/:tipo/:id" element={<EntitaForm />} />
          <Route path="cantiere/:id" element={<Cantiere />} />
          <Route path="scostamenti" element={<Scostamenti />} />
          <Route path="revisione" element={<Revisione />} />
          <Route path="revisione/:id" element={<RevisioneDettaglio />} />
          <Route path="segnalazioni" element={<Segnalazioni />} />
          <Route path="interroga" element={<Interroga />} />
          <Route path="workflows" element={<Workflows />} />
          <Route path="run" element={<Run />} />
          <Route path="tools" element={<SkillsTools />} />
          <Route path="dataset" element={<Dataset />} />
          <Route path="erp" element={<Erp />} />
          <Route path="log" element={<Log />} />
          <Route path="diagnosi" element={<Diagnosi />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </main>
    </div>
  );
}

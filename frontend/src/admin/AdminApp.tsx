/** Guscio della modalità Admin: nav, gate di ruolo, routing delle pagine. */

import { useCallback, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import {
  chiudiSessione,
  salvaSessione,
  sessioneCorrente,
  type Sessione,
} from "../shared/api";
import AdminLogin from "./AdminLogin";
import Cruscotto from "./Cruscotto";
import Interroga from "./Interroga";
import Revisione from "./Revisione";
import RevisioneDettaglio from "./RevisioneDettaglio";
import Segnalazioni from "./Segnalazioni";
import { Bottone } from "./ui";
import Workflows from "./Workflows";

const VOCI = [
  { a: "/admin", etichetta: "Cruscotto", fine: true },
  { a: "/admin/revisione", etichetta: "Revisione", fine: false },
  { a: "/admin/segnalazioni", etichetta: "Segnalazioni", fine: false },
  { a: "/admin/interroga", etichetta: "Interroga", fine: false },
  { a: "/admin/workflows", etichetta: "Workflows", fine: false },
];

export default function AdminApp() {
  const [sessione, setSessione] = useState<Sessione | null>(sessioneCorrente);
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
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-100 p-6 text-center">
        <p className="text-lg text-slate-700">
          Questa è l'area dell'ufficio. Il tuo accesso è da operatore.
        </p>
        <a className="text-sky-700 underline" href="/op">Vai alla tua area →</a>
        <Bottone onClick={esci}>Esci</Bottone>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-6">
            <span className="font-bold">Workflower</span>
            <nav className="flex gap-1">
              {VOCI.map((v) => (
                <NavLink
                  key={v.a}
                  to={v.a}
                  end={v.fine}
                  className={({ isActive }) =>
                    `rounded-lg px-3 py-1.5 text-sm font-medium ${
                      isActive ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-100"
                    }`
                  }
                >
                  {v.etichetta}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-500">{sessione.utente.nome}</span>
            <button onClick={esci} className="text-slate-400 hover:text-slate-700">esci</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-6">
        <Routes>
          <Route index element={<Cruscotto />} />
          <Route path="revisione" element={<Revisione />} />
          <Route path="revisione/:id" element={<RevisioneDettaglio />} />
          <Route path="segnalazioni" element={<Segnalazioni />} />
          <Route path="interroga" element={<Interroga />} />
          <Route path="workflows" element={<Workflows />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </main>
    </div>
  );
}

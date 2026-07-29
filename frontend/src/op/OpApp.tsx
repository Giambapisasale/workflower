/** Guscio della modalità Operatore: mobile-first, una colonna, tutto grande. */

import { useCallback, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import {
  chiudiSessione,
  salvaSessione,
  sessioneCorrente,
  type Sessione,
} from "../shared/api";
import Carica from "./Carica";
import Chiedi from "./Chiedi";
import ConsuntivoOre from "./ConsuntivoOre";
import Dettaglio from "./Dettaglio";
import Documenti from "./Documenti";
import Home from "./Home";
import Login from "./Login";
import { SessioneContext } from "./sessione";

export default function OpApp() {
  const [sessione, setSessione] = useState<Sessione | null>(sessioneCorrente);
  const esci = useCallback(() => {
    chiudiSessione();
    setSessione(null);
  }, []);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        background: "var(--background-secondary)",
        padding: "24px 0",
        /* Vincolo M3 "a prova di cantiere": il corpo del testo non scende
           sotto i 17px. Vive qui, sul guscio dell'Operatore. */
        fontSize: 17,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 430,
          background: "var(--background-primary)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg)",
          padding: "24px 20px",
          minHeight: 780,
          height: "fit-content",
        }}
      >
        {sessione === null ? (
          <Login
            onEntra={(nuova) => {
              salvaSessione(nuova);
              setSessione(nuova);
            }}
          />
        ) : (
          <SessioneContext.Provider value={{ sessione, esci }}>
            <Routes>
              <Route index element={<Home />} />
              <Route path="carica" element={<Carica />} />
              <Route path="ore" element={<ConsuntivoOre />} />
              <Route path="documenti" element={<Documenti />} />
              <Route path="documenti/:id" element={<Dettaglio />} />
              <Route path="chiedi" element={<Chiedi />} />
              <Route path="*" element={<Navigate to="/op" replace />} />
            </Routes>
          </SessioneContext.Provider>
        )}
      </div>
    </div>
  );
}

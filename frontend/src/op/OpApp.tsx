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
    <div className="flex min-h-screen justify-center bg-neutral-200 sm:py-6">
      <div className="w-full max-w-[430px] bg-white px-5 py-6 sm:h-fit sm:min-h-[780px] sm:rounded-[26px] sm:border sm:border-neutral-300 sm:shadow-xl">
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

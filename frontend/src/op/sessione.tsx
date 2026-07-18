/** Contesto di sessione della modalità Operatore. */

import { createContext, useContext } from "react";
import type { Sessione } from "../shared/api";

export type ContestoSessione = { sessione: Sessione; esci: () => void };

export const SessioneContext = createContext<ContestoSessione | null>(null);

export function useSessione(): ContestoSessione {
  const contesto = useContext(SessioneContext);
  if (!contesto) throw new Error("sessione mancante");
  return contesto;
}

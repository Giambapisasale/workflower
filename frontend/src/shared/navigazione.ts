/**
 * Provenienza di navigazione, condivisa fra le due console.
 *
 * Un "indietro" con rotta fissa riporta sempre alla stessa pagina, non a quella
 * da cui si è partiti: alle pagine di dettaglio si arriva da più punti. Chi
 * naviga lascia la propria rotta nello state del router (`da`) e chi torna la
 * usa per due cose: mostrare dove si sta tornando e, soprattutto, tornare
 * *indietro nella history* invece di spingere una voce nuova.
 *
 * Quest'ultimo punto è il motivo per cui il tasto Indietro del browser sembrava
 * non funzionare: con una spinta la pila diventa elenco → dettaglio → elenco, e
 * premere Indietro riportava dentro il dettaglio appena lasciato.
 */

import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/** Il percorso corrente completo di query, da lasciare come provenienza. */
export function usePercorsoCorrente(): string {
  const { pathname, search } = useLocation();
  return pathname + search;
}

/** La provenienza nello state, se c'è ed è una rotta della console `prefisso`. */
export function useProvenienza(prefisso: string): string | null {
  const { state } = useLocation();
  const da = (state as { da?: unknown } | null)?.da;
  return typeof da === "string" && da.startsWith(prefisso) ? da : null;
}

/** Naviga lasciando la provenienza, così la pagina di arrivo sa dove tornare. */
export function useVaiA(): (a: string) => void {
  const naviga = useNavigate();
  const da = usePercorsoCorrente();
  return useCallback((a: string) => naviga(a, { state: { da } }), [da, naviga]);
}

/** L'uscita da una pagina: torna alla pagina da cui si è arrivati.
 *
 *  Con una provenienza torna indietro nella history (`-1`), così la pila non
 *  cresce e il tasto Indietro del browser resta coerente. Senza provenienza —
 *  URL aperto a mano, scheda nuova — non c'è nulla da cui tornare e si spinge
 *  il `ripiego`. */
export function useRitorno(ripiego: string, prefisso: string): () => void {
  const naviga = useNavigate();
  const da = useProvenienza(prefisso);
  return useCallback(() => {
    if (da !== null) naviga(-1);
    else naviga(ripiego);
  }, [da, naviga, ripiego]);
}

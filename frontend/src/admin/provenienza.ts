/** Provenienza di navigazione, lato Admin: i generici stanno in
 *  shared/navigazione.ts, qui si fissa il prefisso e si nominano le sezioni. */

import {
  usePercorsoCorrente,
  useProvenienza as useProvenienzaGenerica,
  useRitorno as useRitornoGenerico,
} from "../shared/navigazione";

export { usePercorsoCorrente };

/** La provenienza lasciata nello state, se c'è ed è una rotta admin. */
export function useProvenienza(): string | null {
  return useProvenienzaGenerica("/admin");
}

/** L'uscita da una pagina di dettaglio: torna dove si era. */
export function useRitorno(ripiego: string): () => void {
  return useRitornoGenerico(ripiego, "/admin");
}

/** Etichetta della sezione per una rotta di provenienza (per il bottone indietro). */
export function etichettaPercorso(percorso: string): string {
  const p = percorso.split("?")[0];
  if (p === "/admin" || p === "/admin/") return "Cruscotto";
  if (p.startsWith("/admin/cantiere/")) return "Cantiere";
  if (p.startsWith("/admin/dati/scartati")) return "Scartati";
  if (p.startsWith("/admin/dati")) return "Dati";
  if (p.startsWith("/admin/scostamenti")) return "Scostamenti";
  if (p.startsWith("/admin/revisione")) return "Revisione";
  if (p.startsWith("/admin/segnalazioni")) return "Segnalazioni";
  if (p.startsWith("/admin/interroga")) return "Agente dati";
  if (p.startsWith("/admin/workflows")) return "Workflows";
  if (p.startsWith("/admin/run")) return "Run";
  if (p.startsWith("/admin/tools")) return "Skills & Tools";
  if (p.startsWith("/admin/dataset")) return "Dataset";
  if (p.startsWith("/admin/erp")) return "Contabilità";
  if (p.startsWith("/admin/log")) return "Log";
  if (p.startsWith("/admin/diagnosi")) return "Diagnosi";
  return "Indietro";
}

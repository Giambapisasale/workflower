/**
 * Tutte le frasi della modalità Operatore, in un posto solo.
 * Regola del piano (§M3): italiano semplice, mai termini tecnici.
 */

export const TESTI = {
  // home
  benvenuto: (nome: string) => `Ciao ${nome} 👷`,
  sottoBenvenuto: "Fotografa bolle, fatture, rapportini. Al resto ci pensiamo noi.",
  bottoneCarica: "Carica un documento",
  bottoneDocumenti: "I miei documenti",
  bottoneChiedi: "Chiedi qualcosa",
  esci: "esci",

  // login
  chiSei: "Ciao! Chi sei?",
  segnapostoNome: "Il tuo nome utente",
  avanti: "Avanti",
  ilTuoCodice: (nome: string) => `Ciao ${nome}! Il tuo codice?`,
  segnapostoCodice: "Il codice che ti ha dato l'ufficio",
  entra: "Entra",
  loginSbagliato: "Nome o codice non giusti. Riprova.",
  indietro: "← indietro",

  // carica
  titoloCarica: "Carica un documento",
  fotografa: "Fotografa",
  scegliFile: "Scegli dal telefono",
  diQualeCantiere: "Di quale cantiere è?",
  stoLeggendo: "Sto leggendo il documento…",
  puoiUscire: "Puoi anche uscire: lo trovi tra poco in “I miei documenti”.",
  hoLetto: (tipo: string) => `Ho letto: ${tipo.toLowerCase()}!`,
  tuttoGiusto: "È tutto giusto?",
  si: "👍 Sì",
  nonTorna: "👎 Qualcosa non torna",
  dimmiCosa: "Dimmi cosa non torna",
  scriviQui: "Scrivi qui, come lo diresti a voce",
  invia: "Invia",
  grazie: "🤝 Grazie! Ci pensiamo noi.",
  sottoGrazie: "L'ufficio controlla e ti avvisa qui. Non devi fare altro.",
  tornaHome: "Torna alla home",
  staAncoraLavorando:
    "Ci sto mettendo un po' più del solito. Lo trovi tra poco in “I miei documenti”.",
  nonRiesco: "Non riesco a riceverlo adesso. Riprova tra qualche minuto.",
  riprova: "Riprova",
  scaricaEsempioTitolo: "Non hai un documento? Scarica un esempio",
  scaricaEsempioSotto: "Scaricalo, poi caricalo qui sopra per provare.",

  // (le etichette del riepilogo arrivano dal backend, una per tipo di entità)

  // documenti
  titoloDocumenti: "I miei documenti",
  nessunDocumento: "Non hai ancora caricato niente. Inizia dalla home!",
  nonTrovato: "Questo documento non c'è più. Torna all'elenco.",

  // chiedi
  titoloChiedi: "Chiedi qualcosa",
  segnapostoDomanda: "Es. Quanto abbiamo speso questo mese?",
  chiedi: "Chiedi",
  ciPenso: "Ci penso…",
  nonSoRispondere: "Non riesco a rispondere adesso. Riprova tra un po'.",

  // generiche
  caricamento: "Un attimo…",
} as const;

export const PALLINO = {
  verde: "🟢",
  giallo: "🟡",
  rosso: "🔴",
} as const;

/** "2026-07-18T09:30:00+00:00" → "oggi", "ieri", "martedì", "5 luglio"… */
export function quandoLeggibile(iso: string | null): string {
  if (!iso) return "";
  const quando = new Date(iso);
  if (Number.isNaN(quando.getTime())) return "";
  const inizioGiorno = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const giorni = Math.round(
    (inizioGiorno(new Date()).getTime() - inizioGiorno(quando).getTime()) / 86_400_000,
  );
  if (giorni <= 0) return "oggi";
  if (giorni === 1) return "ieri";
  if (giorni < 7) return quando.toLocaleDateString("it-IT", { weekday: "long" });
  return quando.toLocaleDateString("it-IT", { day: "numeric", month: "long" });
}

export function euro(importo: number | null): string {
  if (importo === null || importo === undefined) return "—";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(importo);
}

/** 37.5 → "37,5%" (il valore è già una percentuale, non una frazione). */
export function percentuale(valore: number): string {
  return `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1 }).format(valore)}%`;
}

/** "2026-06-30" → "30/06/2026", senza spostamenti di fuso orario. */
export function dataBreve(iso: string | null): string {
  if (!iso) return "";
  const pezzi = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (pezzi) return `${pezzi[3]}/${pezzi[2]}/${pezzi[1]}`;
  const quando = new Date(iso);
  return Number.isNaN(quando.getTime()) ? iso : quando.toLocaleDateString("it-IT");
}

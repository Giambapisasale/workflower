/**
 * Client API del backend (proxy Vite in dev, stesso host in produzione).
 * Qui vivono anche la sessione (localStorage) e i tipi delle risposte.
 */

export const API_BASE = "/api";

export type Cantiere = { id: string; nome: string };

export type Utente = {
  username: string;
  nome: string;
  ruolo: "operatore" | "admin";
  cantieri: Cantiere[];
};

export type Sessione = { token: string; utente: Utente };

/** Una riga del riepilogo: l'etichetta e il valore arrivano dal backend, il
 * tipo dice alla UI come mostrarlo (importo, percentuale, data o testo). */
export type RigaRiepilogo = {
  etichetta: string;
  valore: string | number;
  tipo: "testo" | "euro" | "percento" | "data";
};

export type Riepilogo = {
  tipo: string;
  righe: RigaRiepilogo[];
};

export type Semaforo = "verde" | "giallo" | "rosso";

export type DocumentoVista = {
  id: string;
  quando: string | null;
  in_corso: boolean;
  chiuso: boolean;
  semaforo: Semaforo;
  messaggio: string;
  titolo: string;
  riepilogo: Riepilogo | null;
};

export type EsitoUpload = { doc_id?: string; run_id?: string; messaggio?: string };

export class ErroreApi extends Error {
  stato: number | undefined;
  constructor(messaggio: string, stato?: number) {
    super(messaggio);
    this.stato = stato;
  }
}

const CHIAVE_SESSIONE = "workflower.sessione";

export function sessioneCorrente(): Sessione | null {
  try {
    const grezzo = localStorage.getItem(CHIAVE_SESSIONE);
    return grezzo ? (JSON.parse(grezzo) as Sessione) : null;
  } catch {
    return null;
  }
}

export function salvaSessione(sessione: Sessione): void {
  localStorage.setItem(CHIAVE_SESSIONE, JSON.stringify(sessione));
}

export function chiudiSessione(): void {
  localStorage.removeItem(CHIAVE_SESSIONE);
}

export async function richiesta<T>(percorso: string, init: RequestInit = {}): Promise<T> {
  const sessione = sessioneCorrente();
  const headers = new Headers(init.headers);
  if (sessione) headers.set("Authorization", `Bearer ${sessione.token}`);
  const risposta = await fetch(`${API_BASE}${percorso}`, { ...init, headers });
  if (risposta.status === 401 && sessione) {
    // sessione scaduta: si riparte dal login (operatore o admin secondo il contesto)
    chiudiSessione();
    window.location.assign(window.location.pathname.startsWith("/admin") ? "/admin" : "/op");
  }
  if (!risposta.ok) {
    let dettaglio = `richiesta fallita (${risposta.status})`;
    try {
      const corpo = await risposta.json();
      if (corpo?.detail) dettaglio = String(corpo.detail);
    } catch {
      /* corpo non leggibile: resta il messaggio generico */
    }
    throw new ErroreApi(dettaglio, risposta.status);
  }
  return (await risposta.json()) as T;
}

const esegui = richiesta;

/** Scarica un blob (PDF/immagine) con l'autenticazione della sessione. */
export async function richiestaBlob(percorso: string): Promise<Blob> {
  const sessione = sessioneCorrente();
  const headers = new Headers();
  if (sessione) headers.set("Authorization", `Bearer ${sessione.token}`);
  const risposta = await fetch(`${API_BASE}${percorso}`, { headers });
  if (!risposta.ok) throw new ErroreApi(`richiesta fallita (${risposta.status})`, risposta.status);
  return risposta.blob();
}

/** Scarica un file dal backend e ne avvia il salvataggio nel browser. */
export async function scaricaFile(percorso: string, nomeFile: string): Promise<void> {
  const blob = await richiestaBlob(percorso);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nomeFile;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function corpoJson(dati: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dati),
  };
}

export const api = {
  login(username: string, pin: string): Promise<Sessione> {
    return esegui<Sessione>("/auth/login", corpoJson({ username, pin }));
  },

  documenti(): Promise<DocumentoVista[]> {
    return esegui<{ documenti: DocumentoVista[] }>("/documents?mine=1").then(
      (r) => r.documenti,
    );
  },

  documento(id: string): Promise<DocumentoVista> {
    return esegui<DocumentoVista>(`/documents/${id}`);
  },

  carica(file: File, cantiereId?: string | null): Promise<EsitoUpload> {
    const form = new FormData();
    form.append("file", file);
    if (cantiereId) form.append("cantiere_id", cantiereId);
    return esegui<EsitoUpload>("/documents", { method: "POST", body: form });
  },

  conferma(id: string): Promise<void> {
    return esegui(`/documents/${id}/confirm`, corpoJson({})).then(() => undefined);
  },

  segnala(id: string, testo: string): Promise<void> {
    return esegui(`/documents/${id}/issue`, corpoJson({ testo })).then(() => undefined);
  },

  chiedi(domanda: string): Promise<string> {
    return esegui<{ risposta: string }>(
      "/ask",
      corpoJson({ question: domanda, mode: "op" }),
    ).then((r) => r.risposta);
  },
};

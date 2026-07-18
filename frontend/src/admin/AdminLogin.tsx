import { type FormEvent, useState } from "react";
import { api, ErroreApi, type Sessione } from "../shared/api";
import { Bottone, Errore } from "./ui";

export default function AdminLogin({ onEntra }: { onEntra: (s: Sessione) => void }) {
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(false);

  async function entra(e: FormEvent) {
    e.preventDefault();
    setInCorso(true);
    setErrore(null);
    try {
      onEntra(await api.login(username.trim(), pin.trim()));
    } catch (err) {
      setErrore(err instanceof ErroreApi ? err.message : "Accesso non riuscito");
    } finally {
      setInCorso(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <form onSubmit={entra} className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-bold text-slate-800">Workflower · Ufficio</h1>
        <p className="mb-6 mt-1 text-sm text-slate-500">Console di amministrazione</p>
        <label className="mb-1 block text-sm font-medium text-slate-600">Nome utente</label>
        <input
          className="mb-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          value={username}
          autoFocus
          onChange={(e) => setUsername(e.target.value)}
        />
        <label className="mb-1 block text-sm font-medium text-slate-600">Codice</label>
        <input
          type="password"
          className="mb-5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
        />
        {errore ? <div className="mb-4"><Errore>{errore}</Errore></div> : null}
        <Bottone variante="primario" type="submit" disabled={inCorso} style={{ width: "100%" }}>
          {inCorso ? "Un attimo…" : "Entra"}
        </Bottone>
      </form>
    </div>
  );
}

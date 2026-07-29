import { type FormEvent, useState } from "react";
import { api, ErroreApi, type Sessione } from "../shared/api";
import { Button, Input } from "../ds";
import { Errore } from "./ui";

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
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--background-secondary)",
        padding: 24,
      }}
    >
      <form
        onSubmit={entra}
        style={{
          width: "100%",
          maxWidth: 380,
          background: "var(--background-primary)",
          border: "1px solid var(--border-color)",
          borderRadius: "var(--radius-lg)",
          padding: 32,
        }}
      >
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Workflower · Ufficio</h1>
        <p style={{ margin: "4px 0 24px", fontSize: 14, color: "var(--text-secondary)" }}>
          Console di amministrazione
        </p>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 16,
            marginBottom: 24,
          }}
        >
          <Input
            label="Nome utente"
            value={username}
            autoFocus
            onChange={(e) => setUsername(e.target.value)}
          />
          <Input
            label="Codice"
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
          />
        </div>
        {errore ? <div style={{ marginBottom: 16 }}><Errore>{errore}</Errore></div> : null}
        <Button variant="primary" size="md" type="submit" disabled={inCorso} style={{ width: "100%", justifyContent: "center" }}>
          {inCorso ? "Un attimo…" : "Entra"}
        </Button>
      </form>
    </div>
  );
}

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { admin } from "./api";
import { dataBreve, euro, useCarica } from "./formato";
import TracePanel from "./TracePanel";
import { Badge, Bottone, BottoneVerso, Card, Errore, MONO, Stato } from "./ui";

// v1: unico workflow d'ingresso documenti (vedi documents.WORKFLOW_UPLOAD)
const WORKFLOW_DOC = "carica-fattura";

export default function Segnalazioni() {
  const { dati, errore, inCorso, ricarica } = useCarica(() => admin.issues());
  const [azione, setAzione] = useState<string | null>(null);
  const [traceAperto, setTraceAperto] = useState<string | null>(null);
  const naviga = useNavigate();

  if (inCorso) return <Stato>Carico le segnalazioni…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const issues = dati ?? [];

  async function chiudi(id: string) {
    setAzione(id);
    try {
      await admin.chiudiIssue(id);
      ricarica();
    } finally {
      setAzione(null);
    }
  }

  async function migliora(issueId: string) {
    setAzione(`migliora:${issueId}`);
    try {
      await admin.migliora(WORKFLOW_DOC, { issue_id: issueId });
      naviga("/admin/workflows");
    } finally {
      setAzione(null);
    }
  }

  return (
    <Card titolo={`Segnalazioni (${issues.filter((i) => i.stato === "aperta").length} aperte)`}>
      {issues.length === 0 ? (
        <Stato>Nessuna segnalazione. Tutto tranquillo.</Stato>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {issues.map((i) => (
            <div
              key={i.id}
              style={{
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius)",
                padding: 16,
                opacity: i.stato === "aperta" ? 1 : 0.7,
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 8,
                  fontSize: 12,
                }}
              >
                <span style={{ ...MONO, whiteSpace: "nowrap", color: "var(--text-secondary)" }}>
                  {i.id}
                </span>
                <Badge tono={i.origine === "operatore" ? "blu" : "grigio"}>{i.origine}</Badge>
                <Badge tono={i.stato === "aperta" ? "giallo" : "verde"}>{i.stato}</Badge>
                <span style={{ color: "var(--text-secondary)" }}>{dataBreve(i.created)}</span>
              </div>
              <p style={{ margin: 0, fontSize: 14 }}>{i.testo}</p>
              {i.entita ? (
                <div style={{ marginTop: 6, fontSize: 12, color: "var(--text-secondary)" }}>
                  {i.entita.fornitore ? `${i.entita.fornitore} · ` : ""}
                  {i.entita.totale !== undefined ? euro(i.entita.totale) : ""}
                </div>
              ) : null}
              <div
                style={{
                  marginTop: 14,
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                {i.entity_id ? (
                  <BottoneVerso a={`/admin/revisione/${i.entity_id}`} variante="primario">
                    Rivedi
                  </BottoneVerso>
                ) : null}
                {i.run_id ? (
                  <Bottone
                    onClick={() => setTraceAperto(traceAperto === i.run_id ? null : i.run_id)}
                  >
                    {traceAperto === i.run_id ? "Nascondi trace" : "Mostra trace"}
                  </Bottone>
                ) : null}
                {i.stato === "aperta" && i.run_id ? (
                  <Bottone
                    variante="primario"
                    onClick={() => migliora(i.id)}
                    disabled={azione === `migliora:${i.id}`}
                  >
                    {azione === `migliora:${i.id}` ? "Analizzo…" : "Migliora il workflow"}
                  </Bottone>
                ) : null}
                {i.stato === "aperta" ? (
                  <Bottone onClick={() => chiudi(i.id)} disabled={azione === i.id}>
                    Segna risolta
                  </Bottone>
                ) : null}
              </div>
              {traceAperto === i.run_id && i.run_id ? (
                <div style={{ marginTop: 14 }}>
                  <TracePanel runId={i.run_id} />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

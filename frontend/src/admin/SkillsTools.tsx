/** Strumenti documentali e percorso governato per le capacità dati. */

import { admin } from "./api";
import { useCarica } from "./formato";
import Toolsmith from "./Toolsmith";
import { Badge, Card, Kpi, Stato, Errore } from "./ui";

export default function SkillsTools() {
  const { dati, errore, inCorso } = useCarica(() =>
    Promise.all([admin.skillsTools(), admin.datasetStats()]),
  );

  if (inCorso) return <Stato>Carico strumenti e dati…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const [registro, stats] = dati;

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3">
        <Kpi etichetta="Strumenti documentali" valore={registro.tools.length} />
        <Kpi etichetta="Chiamate registrate" valore={stats.toolcalls_dataset} />
        <Kpi etichetta="Esempi di addestramento" valore={stats.esempi_finetuning} />
      </div>
      <Card titolo="Capacità dell’agente dati">
        <p className="text-sm text-slate-600">
          Le nuove capacità dati seguono un percorso controllato: proposta, collaudo,
          replay e approvazione. I dettagli tecnici restano interni al servizio.
        </p>
        <a className="mt-2 inline-block text-sm text-sky-700 underline" href="/admin/agente/evoluzione">
          Apri Evoluzione agente
        </a>
      </Card>
      <Card titolo="Strumenti dei workflow documentali">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <th className="pb-2">Strumento</th>
              <th className="pb-2">Funzione</th>
              <th className="pb-2 text-right">Utilizzi</th>
            </tr>
          </thead>
          <tbody>
            {registro.tools.map((tool) => (
              <tr key={tool.name} className="border-b border-slate-50">
                <td className="py-2"><Badge tono="grigio">{tool.name}</Badge></td>
                <td className="py-2 text-slate-600">{tool.descrizione}</td>
                <td className="py-2 text-right tabular-nums">{tool.usi}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Toolsmith />
    </>
  );
}

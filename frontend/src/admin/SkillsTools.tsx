/** Skills & Tools (M12): registry dei tool, dataset di fine-tuning, candidati. */

import { admin } from "./api";
import { useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Kpi, Stato } from "./ui";

export default function SkillsTools() {
  const { dati, errore, inCorso } = useCarica(() =>
    Promise.all([admin.skillsTools(), admin.datasetStats()]),
  );
  if (inCorso) return <Stato>Carico tool e dataset…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const [reg, stats] = dati;

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi etichetta="Tool nativi" valore={reg.tools.length} />
        <Kpi etichetta="Tool call registrate" valore={stats.toolcalls_dataset} />
        <Kpi
          etichetta="Esempi fine-tuning"
          valore={stats.esempi_finetuning}
          nota="dai soli run validati"
        />
        <Kpi etichetta="Candidati a tool" valore={reg.candidati.length} />
      </div>

      <Card
        titolo="Dataset per il fine-tuning (FunctionGemma)"
        azioni={
          <Bottone onClick={() => admin.scaricaFinetuning()} disabled={stats.esempi_finetuning === 0}>
            ⬇ Scarica finetuning.jsonl
          </Bottone>
        }
      >
        <p className="text-sm text-slate-600">
          Solo le tool call dei documenti <b>validati dall'ufficio</b> diventano esempi di
          addestramento: {stats.esempi_finetuning} pronti. Serviranno a distillare i workflow
          consolidati su un modello locale (tier T3), portando il costo per documento verso zero.
        </p>
      </Card>

      <Card titolo="Registry dei tool">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <th className="pb-2">Tool</th>
              <th className="pb-2">Cosa fa</th>
              <th className="pb-2 text-right">Usi</th>
              <th className="pb-2">Ciclo di vita</th>
            </tr>
          </thead>
          <tbody>
            {reg.tools.map((t) => (
              <tr key={t.name} className="border-b border-slate-50">
                <td className="py-2 font-mono text-xs text-slate-700">{t.name}</td>
                <td className="py-2 text-slate-600">{t.descrizione}</td>
                <td className="py-2 text-right tabular-nums">{t.usi}</td>
                <td className="py-2">
                  <Badge tono="verde">{t.ciclo}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card titolo="Candidati al consolidamento">
        {reg.candidati.length === 0 ? (
          <Stato>Nessuna query ricorrente da consolidare: usa “Interroga” per generarne.</Stato>
        ) : (
          <ul className="space-y-2 text-sm">
            {reg.candidati.map((c) => (
              <li key={c.fingerprint} className="flex items-center gap-3 border-b border-slate-50 pb-2">
                <Badge tono={c.conteggio > 1 ? "giallo" : "grigio"}>×{c.conteggio}</Badge>
                <code className="truncate text-xs text-slate-500">{c.esempio}</code>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

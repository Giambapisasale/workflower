# Workflower
Sistema LLM-driven per controllo costi cantieri. Leggere: analisi-progettazione.md, piano-implementazione.md (v1, M0–M6), piano-implementazione-fase2.md (M7–M13), piano-implementazione-fase3.md (M14–M21: Toolsmith Python/sandbox, tier T3, entità/registri interni).
## Regole
- /data è la fonte di verità: mai stato applicativo fuori da /data. Ogni mutazione = git commit.
- Nessun DB server. DuckDB solo read-only per query. Scritture solo via dal.py.
- Modelli LLM mai hard-coded: tier T1/T2 da env via gateway.py.
- Prompt e skill vivono in data/workflows/*/skills/*.md, in italiano.
- UI Operatore: mai termini tecnici, zero form, una domanda alla volta.
- Aggiungere un'entità = dati, non codice: schema + riga in ENTITY_TYPES + vista + manifest. runtime.py/gateway.py/dal.py non cambiano.
- Codice generato (Toolsmith, F3) = dato in data/tools/: versionato, approvato dall'umano, eseguito SOLO in sandbox isolata; mai importato in-process. runtime/gateway/dal restano la cornice stabile.
- Test: pytest per ogni milestone; lo scenario "ritenuta d'acconto" (M5) non deve mai rompersi.
## Comandi
make dev | make test | make seed | make fixtures | make demo

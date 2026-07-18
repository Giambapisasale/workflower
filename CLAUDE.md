# Workflower
Sistema LLM-driven per controllo costi cantieri. Leggere: analisi-progettazione.md, piano-implementazione.md.
## Regole
- /data è la fonte di verità: mai stato applicativo fuori da /data. Ogni mutazione = git commit.
- Nessun DB server. DuckDB solo read-only per query. Scritture solo via dal.py.
- Modelli LLM mai hard-coded: tier T1/T2 da env via gateway.py.
- Prompt e skill vivono in data/workflows/*/skills/*.md, in italiano.
- UI Operatore: mai termini tecnici, zero form, una domanda alla volta.
- Test: pytest per ogni milestone; lo scenario "ritenuta d'acconto" (M5) non deve mai rompersi.
## Comandi
make dev | make test | make seed | make fixtures | make demo

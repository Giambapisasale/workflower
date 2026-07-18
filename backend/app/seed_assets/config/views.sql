-- Catalogo viste DuckDB sul repo dati (sola lettura).
-- ${DATA_DIR} è sostituito a runtime da app/core/views.py con il percorso assoluto.
-- Colonne esplicite: le viste sono il contratto stabile per query e cruscotti,
-- i campi JSON non elencati vengono ignorati.
-- Convenzione: niente punto e virgola nei literal, niente commenti in coda alle righe.

CREATE OR REPLACE VIEW v_cantieri AS
SELECT id,
       stato,
       dati.nome               AS nome,
       dati.indirizzo          AS indirizzo,
       dati.comune             AS comune,
       dati.provincia          AS provincia,
       dati.committente        AS committente,
       dati.budget             AS budget,
       dati.data_inizio        AS data_inizio,
       dati.data_fine_prevista AS data_fine_prevista,
       dati.capocantiere       AS capocantiere
FROM read_json(
    '${DATA_DIR}/entities/cantieri/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            nome VARCHAR, indirizzo VARCHAR, comune VARCHAR, provincia VARCHAR,
            committente VARCHAR, budget DOUBLE, data_inizio DATE,
            data_fine_prevista DATE, capocantiere VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_fornitori AS
SELECT id,
       stato,
       dati.ragione_sociale AS ragione_sociale,
       dati.partita_iva     AS partita_iva,
       dati.categoria       AS categoria,
       dati.comune          AS comune,
       dati.pec             AS pec,
       dati.telefono        AS telefono
FROM read_json(
    '${DATA_DIR}/entities/fornitori/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            ragione_sociale VARCHAR, partita_iva VARCHAR, categoria VARCHAR,
            comune VARCHAR, pec VARCHAR, telefono VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_fatture AS
SELECT id,
       stato,
       dati.numero           AS numero,
       dati.data             AS data,
       dati.fornitore_id     AS fornitore_id,
       dati.cantiere_id      AS cantiere_id,
       dati.imponibile       AS imponibile,
       dati.iva              AS iva,
       dati.totale           AS totale,
       dati.ritenuta_acconto AS ritenuta_acconto,
       len(dati.righe)       AS n_righe,
       meta.workflow         AS workflow,
       meta.validato_da      AS validato_da
FROM read_json(
    '${DATA_DIR}/entities/fatture/*/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            numero VARCHAR, data DATE, fornitore_id VARCHAR, cantiere_id VARCHAR,
            imponibile DOUBLE, iva DOUBLE, totale DOUBLE, ritenuta_acconto DOUBLE,
            righe STRUCT(
                descrizione VARCHAR, quantita DOUBLE, unita_misura VARCHAR,
                importo DOUBLE, voce_computo_id VARCHAR
            )[]
        )',
        meta: 'STRUCT(workflow VARCHAR, validato_da VARCHAR)'
    }
);

CREATE OR REPLACE VIEW v_fatture_righe AS
SELECT id                AS fattura_id,
       dati.cantiere_id  AS cantiere_id,
       dati.fornitore_id AS fornitore_id,
       dati.numero       AS numero,
       dati.data         AS data,
       unnest(dati.righe, recursive := true)
FROM read_json(
    '${DATA_DIR}/entities/fatture/*/*.json',
    columns = {
        id: 'VARCHAR',
        dati: 'STRUCT(
            numero VARCHAR, data DATE, fornitore_id VARCHAR, cantiere_id VARCHAR,
            righe STRUCT(
                descrizione VARCHAR, quantita DOUBLE, unita_misura VARCHAR,
                importo DOUBLE, voce_computo_id VARCHAR
            )[]
        )'
    }
);

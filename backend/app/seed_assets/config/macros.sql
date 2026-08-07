-- Implementazione interna approvata del primo tool dati migrato.
CREATE OR REPLACE MACRO t_costi_cantiere(nome_cantiere) AS TABLE (
  SELECT * FROM v_cantiere_costi
  WHERE cantiere ILIKE '%' || nome_cantiere || '%'
);

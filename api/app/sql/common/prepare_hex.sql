BEGIN;

ALTER TABLE "{h_schema}"."{h}"
ADD COLUMN {nombre_resultado}_id_comp VARCHAR,
ADD COLUMN {nombre_resultado}_comp_intersect VARCHAR,
ADD COLUMN {nombre_resultado}_comp_total VARCHAR,
ADD COLUMN {nombre_resultado}_comp_ci VARCHAR,
ADD COLUMN {nombre_resultado}_ci_total VARCHAR,
ADD COLUMN {nombre_resultado}_Fantom VARCHAR,
ADD COLUMN {nombre_resultado}_project_1 VARCHAR,
ADD COLUMN {nombre_resultado}_project_2 VARCHAR,
ADD COLUMN {nombre_resultado}_ci_B VARCHAR,
ADD COLUMN {nombre_resultado}_ci_M VARCHAR,
ADD COLUMN {nombre_resultado}_cr_B VARCHAR,
ADD COLUMN {nombre_resultado}_cr_M VARCHAR,
ADD COLUMN {nombre_resultado}_ci_N_B VARCHAR,
ADD COLUMN {nombre_resultado}_ci_N_M VARCHAR,
ADD COLUMN {nombre_resultado}_metros_OSM VARCHAR;

COMMIT;

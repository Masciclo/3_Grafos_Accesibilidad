library(here)

CICLO_SHP_PATH = here("data/raw/Ciclovias_base.shp")
OSM_SHP_PATH = here("data/raw/Red_open_street_map.shp")

OUTPUT_PATH = here('output')
LOCAL_CUTOFF = 500 # Distancia en metros

selected_setting = 'setting_1_base'

settings_list = list(
  setting_1_base = list(
    filter_non_existent = expression(pull(., 'phanto') == 1 | pull(., 'proyect') == 1),
    filter_inoperative = FALSE,
    filter_projected = FALSE
  ),
  setting_2_operatividad_nivel_1 = list(
    filter_non_existent = expression(pull(., 'phanto') == 1 | pull(., 'proyect') == 1),
    filter_inoperative = expression(pull(., 'op_ci') == 1 | pull(., 'op_cr') == 1),
    filter_projected = FALSE
  ),
  setting_3_operatividad_nivel_2 = list(
    filter_non_existent = expression(pull(., 'phanto') == 1 | pull(., 'proyect') == 1),
    filter_inoperative = expression(pull(., 'op_ci') == 1),
    filter_projected = FALSE
  ),
  setting_4_operatividad_nivel_3 = list(
    filter_non_existent = expression(pull(., 'phanto') == 1 | pull(., 'proyect') == 1),
    filter_inoperative = expression(pull(., 'tip_op') == 1),
    filter_projected = FALSE
  ),
  setting_5_proyectado = list(
    filter_non_existent = expression(pull(., 'phanto') == 1 | pull(., 'op_ci') == 0),
    filter_inoperative = FALSE,
    filter_projected = expression(pull(., 'proyect') == 1)
  )
)

compulsory_fields = c('id_2', 'phanto', 'proyect', 'op_ci', 'op_cr', 'tip_op')

to_h3 = function(x, red, tipo, escenario, data_list ) {
  
  print('Intersectando líneas con H3')
  names(red) = tolower(names(red))
  names(x) = tolower(names(x))
  int = st_intersection(red,x)
  print('Calculando largo')
  int$len = st_length(int)/1000 #Medida en km

  #Kilometros totales
  #Kilometros por topología
  #Kilometros de cruce
  #Razón de cruces de cicl ovías
  if (tipo == 'descriptive') {
    
    print('Calculando largo por tipología')
    int$len_ca = ifelse(int$ci_ca == 1, int$len,0)
    int$len_vd = ifelse(int$ci_vd == 1, int$len,0)
    int$len_plat = ifelse(int$ci_plat == 1, int$len,0)
    int$len_band = ifelse(int$ci_band == 1, int$len,0)
    int$len_par = ifelse(int$ci_par == 1, int$len,0)
    int$len_div = ifelse(int$otros_ci == "2", int$len,0)
    int$len_zig = ifelse(int$otros_ci == "3", int$len,0)
    int$len_intra = ifelse(int$otros_ci == "4", int$len,0)
    int$len_lm = ifelse(int$otros_ci == "5", int$len,0)
    
    print('Calculando largo de cruces')
    int$len_cru = ifelse(int$ci_o_cr == 0, int$len,0)
    
    x$n_id = 1:nrow(x)
    
    join = st_join(x,int)
    
    print('Asignando largo a H3')
    out = group_by(join, n_id) %>%
      summarize(km_total = sum(len),
                km_ca = sum(len_ca),
                km_vd = sum(len_vd),
                km_plat = sum(len_plat),
                km_band = sum(len_band),
                km_par = sum(len_par),
                km_div = sum(len_div),
                km_zig = sum(len_zig),
                km_intra= sum(len_intra),
                km_lm = sum(len_lm),
                km_cru = sum(len_cru)) %>% mutate( .,km_total = ifelse(is.na(km_total),0,km_total) ) %>% st_drop_geometry()
    
    numeric_variables = c('km_ca',
                          'km_vd',
                          'km_plat',
                          'km_band',
                          'km_par',
                          'km_div',
                          'km_zig',
                          'km_intra',
                          'km_lm',
                          'km_cru')
    out[numeric_variables][is.na(out[numeric_variables])] = 0
  
    print('Calculando razón de cruces/ciclovias [km]')
    out$r_cru_ci = out$km_cru/out$km_total
    
    
    
    
    result = merge(x, out, by = 'n_id')
    
    
  }
  #Kilometros de ciclováis buenas
  #% de ciclovías buenas
  #Kilometros de ciclovías malas
  #% de ciclovías malas
  if (tipo == 'quality') {
    
    int$len_ci_b = ifelse(op_ci == 1, int$len, 0)
    int$len_ci_m = ifelse(op_ci == 0, int$len, 0)
    int$len_cr_b = ifelse(op_cr == 1, int$len, 0)
    int$len_cr_m = ifelse(op_cr == 0, int$len, 0)

    int$per_ci_b = int$len_ci_b/int$len 
    int$per_ci_m = int$len_ci_m/int$len
    int$per_cr_b = int$len_cr_b/int$len
    int$per_cr_m = int$len_cr_m/int$len

    print('Asignando indicadores de calidad a H3')

  }
  
  #Max Betweenes (arcos)
  #Promedio Straightness (arcos)
  #Promedio Clossennes (arcos)
  #Kilometros del componente más grande -> km del componente más grande 
  #Número de componentes ->  cantidad de compoinentes distintos que intersectan con h3
  
  #Por desarrollar
  #Kilometros del cluster más grande??
  #Número de clusters??
  
  #Establecer conectividad para cada caso? operativo, inoperativo y proyectado? 
  if (tipo == 'connectivity') {
    
    if (escenario == 'op') {}
    if (escenario == 'inop') {}
    if (escenario == 'pro') {}
    
    int$max_bet = 
    int$mean_str =
    
    int$km_comp = 
    int$n_comp =
    int$km_clus =
    int$n_clus
    
    x$n_id = 1:nrow(x)
    
    join = st_join(x,int)
    
    print('Asignando largo a H3')
    out = group_by(join, n_id) %>%
      summarize(max_bet = max(eb_sub_op),
                mean_str = mean(es_sub_op),
                )
  }
  
  if (tipo == 'geometry') {
    
  }
  return(result)
}
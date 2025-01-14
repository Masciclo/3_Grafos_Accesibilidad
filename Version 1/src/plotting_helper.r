install.packages(c('ggplot2','ggspatial','viridis'))
library(ggplot2)
library(ggspatial)
library(RColorBrewer)
library(viridis)

plotting_h3 = function(x,title,field_fill,leyend_title,xaxis,yaxis) {

  ggplot( ) +
    geom_sf( data = x[,`field_fill`] , aes(fill = `field_fill`)) +
    xlab( xaxis ) + ylab( yaxis ) +
    ggtitle(title) +
    +
    annotation_scale(location = 'bl', width_hint = 0.5) +
    annotation_north_arrow(location = 'bl', which_north = "true",
                           pad_x = unit(0.75, 'in'), pad_y = unit(0.5, 'in'),
                           style = north_arrow_fancy_orienteering)
  print('Guardando mapa')
  ggsave('output/map.pdf')
}



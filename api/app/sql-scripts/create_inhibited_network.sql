DROP TABLE IF EXISTS {result_name};

create table {result_name} as
	select
	network.id,
	(st_dump(st_difference(network.geometry,buffer.geometry))).geom as geometry
	from 
		{network_name} network, -- deberia ir un where
		buffers.{buffer_name} buffer;
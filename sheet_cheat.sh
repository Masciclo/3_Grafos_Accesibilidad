# build docker image
cd db && docker build -t pgrouting/pgrouting . && cd ..

# run docker container using docker image
docker run -p 5298:5298 pgrouting/pgrouting

#show all containers
docker ps -a

#remove container
docker rm asd

#show all containers
docker images

#remove image
docker image asd

#see list of ports listening
sudo netstat -tulpn | grep LISTEN

# enter into docker container
docker exec -it grafos-accesibilidad_stationdb_1 /bin/bash
docker exec -it grafos-accesibilidad_ciclo-py_1 /bin/bash

# enter to database when u are in docker container
psql -h localhost -U USER -d DATABASE_NAME

# sheet cheat sql in cmd
https://gist.github.com/Kartones/dd3ff5ec5ea238d4c546

# stop/start postgres service 
systemctl stop postgresql

#execute script
docker exec -it grafos-accesibilidad_ciclo-py_1 python main.py \
--osm_input \
--ciclo_input \
--location \
--inhibit \
--inhibitor_input \
--buffer_inhibidores \
--disinhit \
--disinhitor_input \
--buffer_disinhibitor \

# execute inside the container
python main.py \
--osm_input='' \
--ciclo_input='data/calidad_cliped.geojson' \
--location='Santiago, Chile' \
--srid=32719 \
--inhibit=1 \
--inhibitor_input='' \
--buffer_inhibidores=15 \
--disinhit=1 \
--disinhitor_input='' \
--buffer_disinhibitor=25 \
--proye= \
--ci_o_cr= \
--op_ci= \


#restart database
docker-compose down
docker volume rm grafos-accesibilidad_stationdb_data



# get ip from docker container to connect to QGIS
# replace id container at the end of the line
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2118f53bf7c0

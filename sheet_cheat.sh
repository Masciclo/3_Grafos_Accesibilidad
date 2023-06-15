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

# stop/start postgres service 
systemctl stop postgresql

#execute script
docker exec -it [654dbc05bf63] python main.py --inhibidores 1 --desinhibidores 1 --ciclos_path /path/to/ciclos --osm_path /path/to/osm --location "location"

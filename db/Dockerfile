# Base image
FROM pgrouting/pgrouting:latest

# Copy initialization script
COPY ./init-queries/ /docker-entrypoint-initdb.d/

# Expose default PostgreSQL port
EXPOSE 5432
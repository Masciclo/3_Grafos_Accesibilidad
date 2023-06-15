CREATE DATABASE masciclo_db;

CREATE SCHEMA masciclo_schema;

CREATE TABLE masciclo_schema.masciclo_table (
    message_id VARCHAR(50) NOT NULL,
    type_message VARCHAR(50) NOT NULL,
    timestamp VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    sending_account_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL
);
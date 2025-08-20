-- Crear la base de datos
CREATE DATABASE webhookdb;

-- Crear el usuario
CREATE USER usuario WITH PASSWORD 'contraseña';

-- Otorgar privilegios al usuario sobre la base de datos
GRANT ALL PRIVILEGES ON DATABASE webhookdb TO usuario;

-- Conectarse a la base de datos para asignar permisos sobre futuras tablas
\c webhookdb

-- Permitir que el usuario cree tablas y acceda a ellas
ALTER SCHEMA public OWNER TO usuario;
GRANT ALL ON SCHEMA public TO usuario;

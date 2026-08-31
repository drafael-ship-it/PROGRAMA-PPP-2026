ALTER TABLE alumnos_snapshot
    ADD COLUMN password_hash VARCHAR(255) NULL AFTER fuente_datos;

-- Los alumnos existentes deberan registrarse una vez para crear su contrasena.

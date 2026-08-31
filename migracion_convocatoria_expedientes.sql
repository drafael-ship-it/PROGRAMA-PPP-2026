ALTER TABLE expedientes_practica
    ADD COLUMN id_convocatoria BIGINT UNSIGNED NULL AFTER id_departamento,
    ADD INDEX idx_expedientes_convocatoria (id_convocatoria),
    ADD INDEX idx_expedientes_alumno_convocatoria (id_alumno, id_convocatoria),
    ADD CONSTRAINT fk_expedientes_convocatoria
        FOREIGN KEY (id_convocatoria)
        REFERENCES convocatorias(id_convocatoria);

-- Opcional para datos antiguos:
-- Si quieres asociar expedientes existentes a una convocatoria ya creada,
-- cambia el 1 por el id_convocatoria correcto y ejecuta:
--
-- UPDATE expedientes_practica
-- SET id_convocatoria = 1
-- WHERE id_convocatoria IS NULL;

-- MySQL dump 10.13  Distrib 8.4.10, for Linux (x86_64)
--
-- Host: localhost    Database: fep_practicas
-- ------------------------------------------------------
-- Server version	8.4.10

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `alumnos_fuente_prueba`
--

DROP TABLE IF EXISTS `alumnos_fuente_prueba`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alumnos_fuente_prueba` (
  `id_fuente` bigint unsigned NOT NULL AUTO_INCREMENT,
  `codigo_alumno` varchar(30) NOT NULL,
  `apellido_paterno` varchar(100) NOT NULL,
  `apellido_materno` varchar(100) NOT NULL,
  `nombres` varchar(120) NOT NULL,
  `creditos_aprobados` int NOT NULL DEFAULT '0',
  `id_departamento` bigint unsigned NOT NULL,
  `estado_matricula` varchar(50) NOT NULL DEFAULT 'MATRICULADO',
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_fuente`),
  UNIQUE KEY `codigo_alumno` (`codigo_alumno`),
  KEY `fk_alumnos_fuente_departamento` (`id_departamento`),
  CONSTRAINT `fk_alumnos_fuente_departamento` FOREIGN KEY (`id_departamento`) REFERENCES `departamentos` (`id_departamento`),
  CONSTRAINT `chk_fuente_creditos` CHECK ((`creditos_aprobados` >= 0))
) ENGINE=InnoDB AUTO_INCREMENT=128 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `alumnos_fuente_prueba_tmp`
--

DROP TABLE IF EXISTS `alumnos_fuente_prueba_tmp`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alumnos_fuente_prueba_tmp` (
  `codigo` varchar(30) DEFAULT NULL,
  `apellido_paterno` varchar(100) DEFAULT NULL,
  `apellido_materno` varchar(100) DEFAULT NULL,
  `nombres` varchar(120) DEFAULT NULL,
  `credito` int DEFAULT NULL,
  `departamento` varchar(150) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `alumnos_snapshot`
--

DROP TABLE IF EXISTS `alumnos_snapshot`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alumnos_snapshot` (
  `id_alumno` bigint unsigned NOT NULL AUTO_INCREMENT,
  `codigo_alumno` varchar(30) NOT NULL,
  `nombres` varchar(120) NOT NULL,
  `apellidos` varchar(150) NOT NULL,
  `id_departamento` bigint unsigned NOT NULL,
  `creditos_aprobados` int NOT NULL DEFAULT '0',
  `estado_matricula` varchar(50) NOT NULL DEFAULT 'MATRICULADO',
  `cumple_requisitos` tinyint(1) NOT NULL DEFAULT '0',
  `fuente_datos` varchar(100) NOT NULL DEFAULT 'VISTA_EXTERNA',
  `password_hash` varchar(255) DEFAULT NULL,
  `fecha_validacion` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_alumno`),
  UNIQUE KEY `codigo_alumno` (`codigo_alumno`),
  KEY `idx_alumnos_codigo` (`codigo_alumno`),
  KEY `idx_alumnos_departamento` (`id_departamento`),
  CONSTRAINT `fk_alumnos_departamentos` FOREIGN KEY (`id_departamento`) REFERENCES `departamentos` (`id_departamento`),
  CONSTRAINT `chk_alumnos_creditos` CHECK ((`creditos_aprobados` >= 0))
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `auditoria_eventos`
--

DROP TABLE IF EXISTS `auditoria_eventos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auditoria_eventos` (
  `id_evento` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_usuario` bigint unsigned DEFAULT NULL,
  `evento` varchar(100) NOT NULL,
  `entidad` varchar(100) DEFAULT NULL,
  `id_entidad` bigint unsigned DEFAULT NULL,
  `detalle` json DEFAULT NULL,
  `ip_origen` varchar(45) DEFAULT NULL,
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_evento`),
  KEY `idx_auditoria_usuario` (`id_usuario`),
  CONSTRAINT `fk_auditoria_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `cronograma_fases`
--

DROP TABLE IF EXISTS `cronograma_fases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cronograma_fases` (
  `id_cronograma` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_fase` bigint unsigned NOT NULL,
  `fecha_inicio` datetime DEFAULT NULL,
  `fecha_fin` datetime DEFAULT NULL,
  `fecha_inicio_subsanacion` datetime DEFAULT NULL,
  `fecha_fin_subsanacion` datetime DEFAULT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_cronograma`),
  KEY `fk_cronograma_fase` (`id_fase`),
  CONSTRAINT `fk_cronograma_fase` FOREIGN KEY (`id_fase`) REFERENCES `fases` (`id_fase`),
  CONSTRAINT `chk_cronograma_fechas` CHECK (((`fecha_inicio` is null) or (`fecha_fin` is null) or (`fecha_inicio` <= `fecha_fin`)))
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `departamentos`
--

DROP TABLE IF EXISTS `departamentos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `departamentos` (
  `id_departamento` bigint unsigned NOT NULL AUTO_INCREMENT,
  `codigo` varchar(50) NOT NULL,
  `nombre` varchar(150) NOT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_departamento`),
  UNIQUE KEY `codigo` (`codigo`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `documentos_expediente`
--

DROP TABLE IF EXISTS `documentos_expediente`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `documentos_expediente` (
  `id_documento` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_expediente` bigint unsigned NOT NULL,
  `id_fase` bigint unsigned NOT NULL,
  `id_documento_requerido` bigint unsigned DEFAULT NULL,
  `nombre_original` varchar(255) NOT NULL,
  `nombre_guardado` varchar(255) NOT NULL,
  `ruta_archivo` varchar(500) NOT NULL,
  `mime_type` varchar(100) NOT NULL DEFAULT 'application/pdf',
  `tamanio_bytes` bigint unsigned DEFAULT NULL,
  `hash_archivo` char(64) DEFAULT NULL,
  `estado_documento` enum('SUBIDO','EN_REVISION','VALIDO','OBSERVADO','RECHAZADO','REEMPLAZADO') NOT NULL DEFAULT 'SUBIDO',
  `subido_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_documento`),
  KEY `fk_documentos_requerido` (`id_documento_requerido`),
  KEY `idx_documentos_expediente` (`id_expediente`),
  KEY `idx_documentos_fase` (`id_fase`),
  KEY `idx_documentos_estado` (`estado_documento`),
  CONSTRAINT `fk_documentos_expediente` FOREIGN KEY (`id_expediente`) REFERENCES `expedientes_practica` (`id_expediente`) ON DELETE CASCADE,
  CONSTRAINT `fk_documentos_fase` FOREIGN KEY (`id_fase`) REFERENCES `fases` (`id_fase`),
  CONSTRAINT `fk_documentos_requerido` FOREIGN KEY (`id_documento_requerido`) REFERENCES `documentos_requeridos_fase` (`id_documento_requerido`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `documentos_requeridos_fase`
--

DROP TABLE IF EXISTS `documentos_requeridos_fase`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `documentos_requeridos_fase` (
  `id_documento_requerido` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_fase` bigint unsigned NOT NULL,
  `nombre` varchar(150) NOT NULL,
  `descripcion` varchar(255) DEFAULT NULL,
  `obligatorio` tinyint(1) NOT NULL DEFAULT '1',
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_documento_requerido`),
  KEY `fk_documentos_requeridos_fase` (`id_fase`),
  CONSTRAINT `fk_documentos_requeridos_fase` FOREIGN KEY (`id_fase`) REFERENCES `fases` (`id_fase`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `expediente_fases`
--

DROP TABLE IF EXISTS `expediente_fases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `expediente_fases` (
  `id_expediente_fase` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_expediente` bigint unsigned NOT NULL,
  `id_fase` bigint unsigned NOT NULL,
  `estado_fase` enum('BLOQUEADA','DISPONIBLE','EN_CARGA','EN_REVISION','OBSERVADA','EN_SUBSANACION','APROBADA','RECHAZADA','VENCIDA','HABILITADA_POR_EXCEPCION') NOT NULL DEFAULT 'BLOQUEADA',
  `fecha_habilitada` datetime DEFAULT NULL,
  `fecha_envio` datetime DEFAULT NULL,
  `fecha_revision` datetime DEFAULT NULL,
  `fecha_aprobacion` datetime DEFAULT NULL,
  `id_usuario_revisor` bigint unsigned DEFAULT NULL,
  `comentario_final` text,
  PRIMARY KEY (`id_expediente_fase`),
  UNIQUE KEY `uq_expediente_fase` (`id_expediente`,`id_fase`),
  KEY `fk_expediente_fases_fase` (`id_fase`),
  KEY `fk_expediente_fases_revisor` (`id_usuario_revisor`),
  KEY `idx_expediente_fases_estado` (`estado_fase`),
  CONSTRAINT `fk_expediente_fases_expediente` FOREIGN KEY (`id_expediente`) REFERENCES `expedientes_practica` (`id_expediente`) ON DELETE CASCADE,
  CONSTRAINT `fk_expediente_fases_fase` FOREIGN KEY (`id_fase`) REFERENCES `fases` (`id_fase`),
  CONSTRAINT `fk_expediente_fases_revisor` FOREIGN KEY (`id_usuario_revisor`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `expedientes_practica`
--

DROP TABLE IF EXISTS `expedientes_practica`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `expedientes_practica` (
  `id_expediente` bigint unsigned NOT NULL AUTO_INCREMENT,
  `codigo_expediente` varchar(40) NOT NULL,
  `id_alumno` bigint unsigned NOT NULL,
  `id_departamento` bigint unsigned NOT NULL,
  `id_fase_actual` bigint unsigned NOT NULL,
  `estado_general` enum('INICIADO','EN_PROCESO','OBSERVADO','VENCIDO','FINALIZADO','RECHAZADO','CANCELADO') NOT NULL DEFAULT 'INICIADO',
  `creditos_al_inicio` int NOT NULL,
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_expediente`),
  UNIQUE KEY `codigo_expediente` (`codigo_expediente`),
  KEY `idx_expedientes_alumno` (`id_alumno`),
  KEY `idx_expedientes_departamento` (`id_departamento`),
  KEY `idx_expedientes_estado` (`estado_general`),
  KEY `idx_expedientes_fase_actual` (`id_fase_actual`),
  CONSTRAINT `fk_expedientes_alumno` FOREIGN KEY (`id_alumno`) REFERENCES `alumnos_snapshot` (`id_alumno`),
  CONSTRAINT `fk_expedientes_departamento` FOREIGN KEY (`id_departamento`) REFERENCES `departamentos` (`id_departamento`),
  CONSTRAINT `fk_expedientes_fase_actual` FOREIGN KEY (`id_fase_actual`) REFERENCES `fases` (`id_fase`),
  CONSTRAINT `chk_expedientes_creditos` CHECK ((`creditos_al_inicio` >= 0))
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `fases`
--

DROP TABLE IF EXISTS `fases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `fases` (
  `id_fase` bigint unsigned NOT NULL AUTO_INCREMENT,
  `nombre` varchar(80) NOT NULL,
  `numero_fase` int NOT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id_fase`),
  UNIQUE KEY `numero_fase` (`numero_fase`),
  CONSTRAINT `chk_fases_numero` CHECK ((`numero_fase` > 0))
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `formatos_fase`
--

DROP TABLE IF EXISTS `formatos_fase`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `formatos_fase` (
  `id_formato` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_fase` bigint unsigned NOT NULL,
  `nombre` varchar(150) NOT NULL,
  `descripcion` varchar(255) DEFAULT NULL,
  `ruta_archivo` varchar(500) NOT NULL,
  `version` varchar(30) DEFAULT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_formato`),
  KEY `fk_formatos_fase` (`id_fase`),
  CONSTRAINT `fk_formatos_fase` FOREIGN KEY (`id_fase`) REFERENCES `fases` (`id_fase`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `historial_expediente`
--

DROP TABLE IF EXISTS `historial_expediente`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `historial_expediente` (
  `id_historial` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_expediente` bigint unsigned NOT NULL,
  `id_usuario` bigint unsigned DEFAULT NULL,
  `accion` varchar(100) NOT NULL,
  `descripcion` text,
  `estado_anterior` varchar(80) DEFAULT NULL,
  `estado_nuevo` varchar(80) DEFAULT NULL,
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_historial`),
  KEY `fk_historial_usuario` (`id_usuario`),
  KEY `idx_historial_expediente` (`id_expediente`),
  CONSTRAINT `fk_historial_expediente` FOREIGN KEY (`id_expediente`) REFERENCES `expedientes_practica` (`id_expediente`) ON DELETE CASCADE,
  CONSTRAINT `fk_historial_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `observaciones_documento`
--

DROP TABLE IF EXISTS `observaciones_documento`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `observaciones_documento` (
  `id_observacion` bigint unsigned NOT NULL AUTO_INCREMENT,
  `id_documento` bigint unsigned NOT NULL,
  `id_expediente` bigint unsigned NOT NULL,
  `id_fase` bigint unsigned NOT NULL,
  `id_usuario` bigint unsigned NOT NULL,
  `mensaje` text NOT NULL,
  `estado_observacion` enum('ABIERTA','SUBSANADA','CERRADA','VENCIDA') NOT NULL DEFAULT 'ABIERTA',
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `cerrado_en` datetime DEFAULT NULL,
  PRIMARY KEY (`id_observacion`),
  KEY `fk_observaciones_expediente` (`id_expediente`),
  KEY `fk_observaciones_fase` (`id_fase`),
  KEY `fk_observaciones_usuario` (`id_usuario`),
  KEY `idx_observaciones_documento` (`id_documento`),
  CONSTRAINT `fk_observaciones_documento` FOREIGN KEY (`id_documento`) REFERENCES `documentos_expediente` (`id_documento`) ON DELETE CASCADE,
  CONSTRAINT `fk_observaciones_expediente` FOREIGN KEY (`id_expediente`) REFERENCES `expedientes_practica` (`id_expediente`) ON DELETE CASCADE,
  CONSTRAINT `fk_observaciones_fase` FOREIGN KEY (`id_fase`) REFERENCES `fases` (`id_fase`),
  CONSTRAINT `fk_observaciones_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id_rol` bigint unsigned NOT NULL AUTO_INCREMENT,
  `nombre` varchar(50) NOT NULL,
  `descripcion` varchar(255) DEFAULT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id_rol`),
  UNIQUE KEY `nombre` (`nombre`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `usuario_departamentos`
--

DROP TABLE IF EXISTS `usuario_departamentos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuario_departamentos` (
  `id_usuario` bigint unsigned NOT NULL,
  `id_departamento` bigint unsigned NOT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `asignado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_usuario`,`id_departamento`),
  KEY `fk_usuario_departamentos_departamento` (`id_departamento`),
  CONSTRAINT `fk_usuario_departamentos_departamento` FOREIGN KEY (`id_departamento`) REFERENCES `departamentos` (`id_departamento`),
  CONSTRAINT `fk_usuario_departamentos_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `usuario_roles`
--

DROP TABLE IF EXISTS `usuario_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuario_roles` (
  `id_usuario` bigint unsigned NOT NULL,
  `id_rol` bigint unsigned NOT NULL,
  `asignado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_usuario`,`id_rol`),
  KEY `fk_usuario_roles_rol` (`id_rol`),
  CONSTRAINT `fk_usuario_roles_rol` FOREIGN KEY (`id_rol`) REFERENCES `roles` (`id_rol`),
  CONSTRAINT `fk_usuario_roles_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `usuarios`
--

DROP TABLE IF EXISTS `usuarios`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuarios` (
  `id_usuario` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(80) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `nombres` varchar(120) NOT NULL,
  `apellidos` varchar(150) NOT NULL,
  `correo` varchar(150) DEFAULT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `creado_en` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_usuario`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `correo` (`correo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-06-24 15:56:22

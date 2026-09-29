-- Junior FC backend schema (MySQL 8.4). Idempotent: run by the jfc-db-migrate Lambda.
-- All times are UTC (RDS default); the store formats them in America/Bogota.

-- ─────────────────────────────── Personalización (Lambda) ───────────────────────────────

CREATE TABLE IF NOT EXISTS producto (
  sku            VARCHAR(20)  PRIMARY KEY,
  nombre         VARCHAR(120) NOT NULL,
  categoria      VARCHAR(40)  NOT NULL,
  precio         INT UNSIGNED NOT NULL,
  personalizable BOOLEAN      NOT NULL DEFAULT FALSE,
  color1         VARCHAR(20)  NOT NULL DEFAULT 'red',
  color2         VARCHAR(20)  NOT NULL DEFAULT 'white'
);

CREATE TABLE IF NOT EXISTS parche (
  codigo VARCHAR(20)  PRIMARY KEY,
  nombre VARCHAR(80)  NOT NULL,
  precio INT UNSIGNED NOT NULL,
  activo BOOLEAN      NOT NULL DEFAULT TRUE,
  orden  TINYINT      NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dorsal_reservado (
  numero TINYINT UNSIGNED PRIMARY KEY,
  motivo VARCHAR(120)     NOT NULL
);

CREATE TABLE IF NOT EXISTS palabra_bloqueada (
  palabra VARCHAR(40) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS personalizacion (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_sub     VARCHAR(64)      NOT NULL,
  email        VARCHAR(254)     NULL,
  sku          VARCHAR(20)      NOT NULL,
  nombre       VARCHAR(12)      NOT NULL,
  numero       TINYINT UNSIGNED NOT NULL,
  parche       VARCHAR(20)      NOT NULL DEFAULT 'NINGUNO',
  precio_final INT UNSIGNED     NOT NULL,
  creado       TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado  TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_personalizacion_usuario_sku (user_sub, sku),
  CONSTRAINT fk_personalizacion_producto FOREIGN KEY (sku)    REFERENCES producto (sku),
  CONSTRAINT fk_personalizacion_parche   FOREIGN KEY (parche) REFERENCES parche (codigo)
);

-- ─────────────────────────────── Boletería (OpenShift) ───────────────────────────────

CREATE TABLE IF NOT EXISTS partido (
  id          INT UNSIGNED PRIMARY KEY,
  rival       VARCHAR(80)  NOT NULL,
  competencia VARCHAR(80)  NOT NULL,
  fecha_hora  DATETIME     NOT NULL,
  estado      ENUM('EN_VENTA', 'CERRADO') NOT NULL DEFAULT 'EN_VENTA'
);

CREATE TABLE IF NOT EXISTS tribuna (
  codigo VARCHAR(12) PRIMARY KEY,
  nombre VARCHAR(40) NOT NULL,
  orden  TINYINT     NOT NULL
);

CREATE TABLE IF NOT EXISTS seccion (
  codigo  SMALLINT UNSIGNED PRIMARY KEY,
  tribuna VARCHAR(12)       NOT NULL,
  orden   TINYINT UNSIGNED  NOT NULL,
  CONSTRAINT fk_seccion_tribuna FOREIGN KEY (tribuna) REFERENCES tribuna (codigo)
);

CREATE TABLE IF NOT EXISTS precio_tribuna (
  partido_id INT UNSIGNED NOT NULL,
  tribuna    VARCHAR(12)  NOT NULL,
  precio     INT UNSIGNED NOT NULL,
  PRIMARY KEY (partido_id, tribuna),
  CONSTRAINT fk_precio_partido FOREIGN KEY (partido_id) REFERENCES partido (id),
  CONSTRAINT fk_precio_tribuna FOREIGN KEY (tribuna)    REFERENCES tribuna (codigo)
);

-- id = seccion * 10000 + fila * 100 + numero (e.g. 1041407 = sección 104, fila 14, silla 7),
-- so a seat id is readable in logs and stable across re-seeds.
CREATE TABLE IF NOT EXISTS silla (
  id            INT UNSIGNED      PRIMARY KEY,
  tribuna       VARCHAR(12)       NOT NULL,
  seccion       SMALLINT UNSIGNED NOT NULL,
  fila          TINYINT UNSIGNED  NOT NULL,
  numero        TINYINT UNSIGNED  NOT NULL,
  puntaje_vista TINYINT UNSIGNED  NOT NULL,
  UNIQUE KEY uq_silla_ubicacion (seccion, fila, numero),
  KEY ix_silla_tribuna (tribuna),
  CONSTRAINT fk_silla_seccion FOREIGN KEY (seccion) REFERENCES seccion (codigo)
);

CREATE TABLE IF NOT EXISTS reserva (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  codigo          CHAR(8)          NOT NULL,
  partido_id      INT UNSIGNED     NOT NULL,
  user_sub        VARCHAR(64)      NOT NULL,
  email           VARCHAR(254)     NULL,
  tribuna         VARCHAR(12)      NOT NULL,
  cantidad        TINYINT UNSIGNED NOT NULL,
  precio_unitario INT UNSIGNED     NOT NULL,
  total           INT UNSIGNED     NOT NULL,
  estado          ENUM('RETENIDA', 'CONFIRMADA', 'EXPIRADA', 'CANCELADA') NOT NULL DEFAULT 'RETENIDA',
  creada          DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expira_en       DATETIME         NOT NULL,
  confirmada      DATETIME         NULL,
  UNIQUE KEY uq_reserva_codigo (codigo),
  KEY ix_reserva_usuario (user_sub, partido_id, estado),
  KEY ix_reserva_vencimiento (estado, expira_en),
  CONSTRAINT fk_reserva_partido FOREIGN KEY (partido_id) REFERENCES partido (id)
);

-- One row per seat that is held or sold for a match. The primary key is what makes selling
-- the same seat twice impossible: a second INSERT for (partido, silla) fails, whichever pod sends it.
CREATE TABLE IF NOT EXISTS silla_partido (
  partido_id INT UNSIGNED NOT NULL,
  silla_id   INT UNSIGNED NOT NULL,
  estado     ENUM('RETENIDA', 'VENDIDA') NOT NULL,
  reserva_id INT UNSIGNED NOT NULL,
  expira_en  DATETIME     NULL,
  PRIMARY KEY (partido_id, silla_id),
  KEY ix_silla_partido_vencimiento (estado, expira_en),
  KEY ix_silla_partido_reserva (reserva_id),
  CONSTRAINT fk_silla_partido_silla FOREIGN KEY (silla_id) REFERENCES silla (id)
);

CREATE TABLE IF NOT EXISTS boleta (
  id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  codigo     CHAR(10)     NOT NULL,
  reserva_id INT UNSIGNED NOT NULL,
  partido_id INT UNSIGNED NOT NULL,
  silla_id   INT UNSIGNED NOT NULL,
  qr_payload VARCHAR(200) NOT NULL,
  usada_en   DATETIME     NULL,
  creada     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_boleta_codigo (codigo),
  UNIQUE KEY uq_boleta_silla (partido_id, silla_id),
  KEY ix_boleta_reserva (reserva_id),
  CONSTRAINT fk_boleta_reserva FOREIGN KEY (reserva_id) REFERENCES reserva (id)
);

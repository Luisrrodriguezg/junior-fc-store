-- Reference data. INSERT IGNORE keeps re-runs harmless; the seat map and pre-sold seats are
-- generated in Python (jfc/estadio.py) because they are ~46,000 + ~60,000 rows.

-- The 5 SKUs published in Contentful (space y5240smrcxdb). Only jerseys can be personalized.
INSERT IGNORE INTO producto (sku, nombre, categoria, precio, personalizable, color1, color2) VALUES
  ('JFC-001', 'Camiseta Local 2026',        'camisetas',     279900, TRUE,  'red',   'white'),
  ('JFC-002', 'Chaqueta de Presentación',   'entrenamiento', 349900, FALSE, 'black', 'red'),
  ('JFC-003', 'Guayos Terreno Firme',       'calzado',       459900, FALSE, 'red',   'black'),
  ('JFC-004', 'Gorra Oficial de Hinchada',  'accesorios',     69900, FALSE, 'blue',  'yellow'),
  ('JFC-005', 'Camiseta Visitante – Niño',  'camisetas',     199900, TRUE,  'white', 'red');

INSERT IGNORE INTO parche (codigo, nombre, precio, activo, orden) VALUES
  ('NINGUNO', 'Sin parche',                   0,     TRUE, 0),
  ('LIGA',    'Parche Liga Colombiana',       25000, TRUE, 1),
  ('COPA',    'Parche Copa Internacional',    30000, TRUE, 2),
  ('ESTRELLA','Parche de estrellas del club', 20000, TRUE, 3);

INSERT IGNORE INTO dorsal_reservado (numero, motivo) VALUES
  (12, 'El 12 es de la hinchada: está reservado para la edición especial.');

-- Compared against the name after removing accents, spaces, punctuation and leetspeak (4→A, 3→E, 1→I, 0→O, 5→S).
INSERT IGNORE INTO palabra_bloqueada (palabra) VALUES
  ('PUTA'), ('PUTO'), ('MIERDA'), ('GONORREA'), ('MALPARIDO'), ('HIJUEPUTA'), ('HPTA'),
  ('CAREMONDA'), ('MARICA'), ('PERRA'), ('NAZI'), ('HITLER'), ('VERGA'), ('CULO');

INSERT IGNORE INTO tribuna (codigo, nombre, orden) VALUES
  ('OCCIDENTAL', 'Occidental', 1),
  ('ORIENTAL',   'Oriental',   2),
  ('NORTE',      'Norte',      3),
  ('SUR',        'Sur',        4);

-- fecha_hora is UTC: 00:30 UTC = 19:30 in Barranquilla (UTC-5).
INSERT IGNORE INTO partido (id, rival, competencia, fecha_hora, estado) VALUES
  (1, 'Atlético Nacional', 'Liga Colombiana 2026-II · Fecha 14', '2026-10-05 00:30:00', 'EN_VENTA'),
  (2, 'América de Cali',   'Liga Colombiana 2026-II · Fecha 16', '2026-10-19 01:00:00', 'EN_VENTA'),
  (3, 'Millonarios',       'Copa Colombia 2026 · Cuartos de final', '2026-11-01 22:00:00', 'EN_VENTA');

INSERT IGNORE INTO precio_tribuna (partido_id, tribuna, precio) VALUES
  (1, 'OCCIDENTAL', 180000), (1, 'ORIENTAL', 110000), (1, 'NORTE', 55000), (1, 'SUR', 55000),
  (2, 'OCCIDENTAL', 150000), (2, 'ORIENTAL',  90000), (2, 'NORTE', 45000), (2, 'SUR', 45000),
  (3, 'OCCIDENTAL', 120000), (3, 'ORIENTAL',  75000), (3, 'NORTE', 40000), (3, 'SUR', 40000);

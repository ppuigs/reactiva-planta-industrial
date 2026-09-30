-- Exporta a CSV las tablas que usa el dashboard de Power BI.
-- Formato estándar: separador "," y decimales con ".".
-- Ejecutar DESPUÉS de crear_tablas.sql.
COPY (SELECT * FROM factura_mensual ORDER BY mes, periodo) TO 'datos/factura_mensual.csv' (HEADER, DELIMITER ',');
COPY (SELECT * FROM consumo_15min   ORDER BY inicio)       TO 'datos/consumo_15min.csv'   (HEADER, DELIMITER ',');

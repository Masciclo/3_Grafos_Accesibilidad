CREATE OR REPLACE FUNCTION delete_line_segments_in_polygon(
    line_table text,
    polygon_table text
) RETURNS void AS $$
BEGIN
    EXECUTE format(
        'WITH polys AS (
            SELECT ST_Union(geom) AS geom 
            FROM %I
        ),
        lines AS (
            SELECT a.id, ST_Difference(a.geom, b.geom) AS geom
            FROM %I AS a, polys AS b
        )
        UPDATE %I AS l
        SET geom = lines.geom
        FROM lines
        WHERE l.id = lines.id AND ST_Within(lines.geom, polys.geom)', 
        polygon_table, line_table, line_table
    );
END;
$$ LANGUAGE plpgsql;

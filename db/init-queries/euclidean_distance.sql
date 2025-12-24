CREATE OR REPLACE FUNCTION euclidean_distance(_node1 INTEGER, _node2 INTEGER)
RETURNS DOUBLE PRECISION AS $$
DECLARE
    coord1 RECORD;
    coord2 RECORD;
    distance DOUBLE PRECISION;
BEGIN
    SELECT x, y INTO coord1 FROM node_coordinates WHERE node_id = _node1;
    SELECT x, y INTO coord2 FROM node_coordinates WHERE node_id = _node2;

    distance := SQRT(POWER(coord1.x - coord2.x, 2) + POWER(coord1.y - coord2.y, 2));

    RETURN distance;
END;
$$ LANGUAGE plpgsql;
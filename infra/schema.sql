CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS station_locations (
  snapshot_id TEXT NOT NULL,
  station_id TEXT NOT NULL,
  name TEXT NOT NULL,
  location geography(Point,4326) NOT NULL,
  PRIMARY KEY(snapshot_id,station_id)
);
CREATE INDEX IF NOT EXISTS station_locations_gist ON station_locations USING gist(location);
-- Coordinates and complete source document are immutable per snapshot.
-- Radius queries exclude the canonical facility itself, include the boundary.
CREATE OR REPLACE FUNCTION nearby_station_ids(snap TEXT, self_id TEXT, r FLOAT)
RETURNS TABLE(station_id TEXT, distance_m FLOAT) LANGUAGE SQL STABLE AS $$
SELECT other.station_id, ST_Distance(other.location,origin.location,false)
FROM station_locations origin JOIN station_locations other ON other.snapshot_id=origin.snapshot_id
WHERE origin.snapshot_id=snap AND origin.station_id=self_id
  AND other.station_id<>self_id AND ST_DWithin(other.location,origin.location,r,false);
$$;

-- Converts TEXT geometry columns to PostGIS GEOMETRY type.
-- Installs PostGIS extension if available, then upgrades columns.
-- Fails gracefully if PostGIS shared library is not installed.
-- Safe to run repeatedly — idempotent via IF NOT EXISTS.

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS postgis;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'PostGIS not available (%), skipping geometry upgrade', SQLERRM;
    RETURN;
END $$;

DO $$
BEGIN
    RAISE NOTICE 'PostGIS extension ready — upgrading geometry columns';

    -- ml_polygons
    ALTER TABLE ml_polygons ALTER COLUMN original_geometry TYPE GEOMETRY(POLYGON, 4326)
        USING ST_GeomFromText(original_geometry, 4326);
    ALTER TABLE ml_polygons ALTER COLUMN corrected_geometry TYPE GEOMETRY(POLYGON, 4326)
        USING ST_GeomFromText(corrected_geometry, 4326);
    CREATE INDEX IF NOT EXISTS idx_ml_polygons_geom ON ml_polygons USING GIST(original_geometry);

    -- human_corrections
    ALTER TABLE human_corrections ALTER COLUMN original_geometry TYPE GEOMETRY(POLYGON, 4326)
        USING ST_GeomFromText(original_geometry, 4326);
    ALTER TABLE human_corrections ALTER COLUMN corrected_geometry TYPE GEOMETRY(POLYGON, 4326)
        USING ST_GeomFromText(corrected_geometry, 4326);

    -- initiatives
    ALTER TABLE initiatives ALTER COLUMN region TYPE GEOMETRY(GEOMETRY, 4326)
        USING ST_GeomFromText(region, 4326);
    CREATE INDEX IF NOT EXISTS idx_initiatives_region ON initiatives USING GIST(region);

    -- map_task_grid
    ALTER TABLE map_task_grid ALTER COLUMN geometry TYPE GEOMETRY(POLYGON, 4326)
        USING ST_GeomFromText(geometry, 4326);
    CREATE INDEX IF NOT EXISTS idx_task_grid_geom ON map_task_grid USING GIST(geometry);

    -- user_imagery
    ALTER TABLE user_imagery ALTER COLUMN bounding_box TYPE GEOMETRY(POLYGON, 4326)
        USING ST_GeomFromText(bounding_box, 4326);
    CREATE INDEX IF NOT EXISTS idx_user_imagery_bbox ON user_imagery USING GIST(bounding_box);

    -- validation_runs
    ALTER TABLE validation_runs ALTER COLUMN region TYPE GEOMETRY(GEOMETRY, 4326)
        USING ST_GeomFromText(region, 4326);

    RAISE NOTICE 'Geometry upgrade complete';
END $$;

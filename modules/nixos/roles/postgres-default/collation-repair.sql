\set ON_ERROR_STOP on
SELECT pg_advisory_lock(734019263);
SELECT datcollversion IS DISTINCT FROM pg_database_collation_actual_version(oid)
       AND datcollversion IS NOT NULL AS repair_needed
FROM pg_database WHERE datname = current_database()
\gset
\if :repair_needed
-- Reindexing cannot repair collation-dependent partition placement or
-- materialized query results. Require explicit review for those databases.
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_partitioned_table WHERE 0 <> ANY(partcollation))
     OR EXISTS (SELECT FROM pg_class WHERE relkind = 'm') THEN
    RAISE EXCEPTION 'Collation repair requires review of partitions/materialized views';
  END IF;
END $$;
SELECT format('REINDEX DATABASE %I', current_database())
\gexec
SELECT format('REINDEX SYSTEM %I', current_database())
\gexec
-- Separate commands: REINDEX DATABASE cannot run inside a transaction.
-- ON_ERROR_STOP ensures any failed rebuild leaves the old version recorded.
SELECT format('ALTER DATABASE %I REFRESH COLLATION VERSION', current_database())
\gexec
\endif
SELECT pg_advisory_unlock(734019263);

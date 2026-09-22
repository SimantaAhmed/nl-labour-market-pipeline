-- STAGING layer: views only, no storage.

CREATE SCHEMA IF NOT EXISTS staging;

-- The most recently landed version of each (series, month), with a hash of
-- the fields that matter. A changed hash means StatCan revised the point.
-- NULL is spelled out before hashing so a value becoming suppressed (or
-- un-suppressed) still counts as a change.
CREATE OR REPLACE VIEW staging.observation AS
SELECT
    vector_id,
    ref_period,
    value,
    status_code,
    symbol_code,
    release_time,
    md5(concat_ws('|',
        coalesce(CAST(value AS VARCHAR), 'null'),
        coalesce(CAST(status_code AS VARCHAR), 'null'),
        coalesce(CAST(symbol_code AS VARCHAR), 'null'))) AS row_hash
FROM raw.observation
QUALIFY row_number() OVER (
    PARTITION BY vector_id, ref_period ORDER BY batch_id DESC) = 1;

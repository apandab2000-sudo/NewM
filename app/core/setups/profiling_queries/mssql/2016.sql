WITH PKColumns AS
(
    SELECT
        ic.object_id,
        ic.column_id,
        1 AS is_primary_key
    FROM sys.key_constraints kc
    JOIN sys.index_columns ic
        ON kc.parent_object_id = ic.object_id
        AND kc.unique_index_id = ic.index_id
    WHERE kc.type = 'PK'
),

FKColumns AS
(
    SELECT
        fkc.parent_object_id AS object_id,
        fkc.parent_column_id AS column_id,

        OBJECT_SCHEMA_NAME(pt.object_id)+'.'+pt.name AS parent_table,
        pc.name AS parent_column,

        OBJECT_SCHEMA_NAME(rt.object_id)+'.'+rt.name AS referenced_table,
        rc.name AS referenced_column
    FROM sys.foreign_key_columns fkc
    JOIN sys.tables pt
        ON pt.object_id = fkc.parent_object_id
    JOIN sys.columns pc
        ON pc.object_id = fkc.parent_object_id
        AND pc.column_id = fkc.parent_column_id
    JOIN sys.tables rt
        ON rt.object_id = fkc.referenced_object_id
    JOIN sys.columns rc
        ON rc.object_id = fkc.referenced_object_id
        AND rc.column_id = fkc.referenced_column_id
),

StatsData AS
(
    SELECT
        OBJECT_SCHEMA_NAME(s.object_id)+'.'+OBJECT_NAME(s.object_id) AS table_name,
        c.name AS name,
        t.name AS type,

        CAST(ISNULL(pk.is_primary_key,0) AS BIT) AS is_primary_key,

        CAST(
			(
			    SELECT
			        fk.parent_table,
			        fk.parent_column,
			        fk.referenced_table,
			        fk.referenced_column
			    FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
			)
		AS NVARCHAR(4000)) AS foreign_key,

        CONVERT(NVARCHAR(200), h.range_high_key) AS RawValue,
		CONVERT(NVARCHAR(200), h.range_high_key) AS Value,
        h.equal_rows

    FROM sys.stats s

    JOIN sys.stats_columns sc
        ON s.object_id=sc.object_id
        AND s.stats_id=sc.stats_id

    JOIN sys.columns c
        ON sc.object_id=c.object_id
        AND sc.column_id=c.column_id

    JOIN sys.types t
        ON c.user_type_id=t.user_type_id

    CROSS APPLY sys.dm_db_stats_histogram(s.object_id,s.stats_id) h

    LEFT JOIN PKColumns pk
        ON pk.object_id = c.object_id
        AND pk.column_id = c.column_id

    LEFT JOIN FKColumns fk
        ON fk.object_id = c.object_id
        AND fk.column_id = c.column_id

    WHERE s.object_id = OBJECT_ID('{table_name}')
),

ColumnStats AS
(
SELECT
    table_name,
    name,
    type,
    is_primary_key,
    foreign_key,

    MIN(CASE 
        WHEN type IN ('int','bigint','smallint','tinyint',
                           'float','real','decimal','numeric',
                           'date','datetime','datetime2','smalldatetime')
        THEN RawValue END) AS min_value,

    MAX(CASE 
        WHEN type IN ('int','bigint','smallint','tinyint',
                           'float','real','decimal','numeric',
                           'date','datetime','datetime2','smalldatetime')
        THEN RawValue END) AS max_value,

    COUNT(Value) AS distinct_values,
    SUM(equal_rows) AS total_rows

FROM StatsData
GROUP BY table_name, name, type, is_primary_key, foreign_key
),

CardinalityClass AS
(
SELECT
    *,
    CASE
        WHEN distinct_values >= 100
             OR (distinct_values*1.0/NULLIF(total_rows,0)) >= 0.3
        THEN 1
        ELSE 0
    END AS is_high_cardinality

FROM ColumnStats
),

TopValues AS
(
SELECT
    name,
    type,
    Value,

    CAST(equal_rows*100.0/
        SUM(equal_rows) OVER(PARTITION BY name)
    AS DECIMAL(10,2)) AS DistributionPercent,

    ROW_NUMBER() OVER
    (
        PARTITION BY name
        ORDER BY equal_rows DESC
    ) rn

FROM StatsData
),

DistributionJSON AS
(
SELECT
    t1.name,

    JSON_QUERY(
		(
		    SELECT
		        t2.Value AS value,
		        t2.DistributionPercent AS pct
		    FROM TopValues t2
		    WHERE t2.name = t1.name
		    AND t2.type IN ('varchar','nvarchar','nchar','object', 'bit')
        	AND t2.Value <> '' 
        	AND t2.Value IS NOT NULL
            AND rn<=3
            AND t2.name NOT IN {cols_to_ignore}
		    FOR JSON PATH
		)
	) AS distribution_mappings

FROM TopValues t1
GROUP BY t1.name
),

UniqueValuesJSON AS
(
SELECT
    t1.name,
    
    JSON_QUERY(
        (
		    SELECT
		        t2.Value AS value
		    FROM TopValues t2
		    WHERE t2.name = t1.name
		    AND t2.type IN ('varchar','nvarchar','nchar','object')
        	AND t2.Value <> '' 
        	AND t2.Value IS NOT NULL
            AND rn<=500
            AND t2.name NOT IN {cols_to_ignore}
		    FOR JSON PATH
		)
    ) as unique_values

FROM TopValues t1
GROUP BY t1.name
)

SELECT
    c.table_name,
    c.name,
    c.type,
    c.is_primary_key, 
    c.foreign_key,
    c.min_value,
    c.max_value,
    u.unique_values,
    
    CASE
        WHEN c.is_high_cardinality = 1 AND c.type in ('varchar','nvarchar','nchar','object', 'bit')
        THEN c.distinct_values
    END AS num_unqiue_values,

    CASE
        WHEN c.is_high_cardinality = 0
        THEN d.distribution_mappings
    END AS distribution_mappings

FROM CardinalityClass c

JOIN DistributionJSON d
ON c.name=d.name

JOIN UniqueValuesJSON u
ON c.name=u.name
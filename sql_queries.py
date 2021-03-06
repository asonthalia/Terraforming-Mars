import configparser

# CONFIG
config = configparser.ConfigParser()
config.read('AWS_CONFIG.cfg')

# DROP TABLES
drop_all_tables = '''
    DROP TABLE IF EXISTS STAGING_ATMOSPHERE;
    DROP TABLE IF EXISTS STAGING_SCHEDULE;
    DROP TABLE IF EXISTS DIM_ACTIVITIES;
    DROP TABLE IF EXISTS DIM_ORGANISATIONS;
    DROP TABLE IF EXISTS DIM_MARS_ATLAS;
    DROP TABLE IF EXISTS DIM_MARS_TIME;
    DROP TABLE IF EXISTS DIM_EARTH_TIME;
    DROP TABLE IF EXISTS FACT_TERRAFORMANCE;
'''

# CREATE TABLES
create_staging_tables = '''
    CREATE TABLE STAGING_ATMOSPHERE (
          MARTIAN_SOL INT NOT NULL
        , MARS_SUN_ANGLE FLOAT NOT NULL
        , DEFAULT_MIN_TEMP FLOAT NOT NULL
        , DEFAULT_AVG_TEMP FLOAT NOT NULL
        , DEFAULT_MAX_TEMP FLOAT NOT NULL
        , TERRAFORMED_MIN_TEMP FLOAT NOT NULL
        , TERRAFORMED_AVG_TEMP FLOAT NOT NULL
        , TERRAFORMED_MAX_TEMP FLOAT NOT NULL
        , DEFAULT_ATM_PRESSURE_PASCAL FLOAT NOT NULL
        , TERRAFORMED_ATM_PRESSURE_PASCAL FLOAT NOT NULL
    );

    CREATE TABLE STAGING_SCHEDULE (
          ACTIVITY VARCHAR(100)
        , ACTIVITY_HANDLER VARCHAR(100)
        , ACTIVITY_TYPE VARCHAR(100)
        , MARTIAN_ACTIVITY_LOCATION VARCHAR(100)
        , SOL INT
        , EXECUTION_DATETIME BIGINT
    );
'''

create_fact_table = '''
    CREATE TABLE FACT_TERRAFORMANCE (
          TERRAFORMING_STEP_ID INT IDENTITY(0,1)
        , ACTIVITY_ID INT
        , ORGANISATION_ID INT
        , LOC_ID INT
        , SOL INT NOT NULL
        , ACTIVITY_EXECUTION_TIME DATETIME
        , MARS_SUN_ANGLE FLOAT NOT NULL
        , DEFAULT_MIN_TEMP FLOAT NOT NULL
        , DEFAULT_AVG_TEMP FLOAT NOT NULL
        , DEFAULT_MAX_TEMP FLOAT NOT NULL
        , TERRAFORMED_MIN_TEMP FLOAT NOT NULL
        , TERRAFORMED_AVG_TEMP FLOAT NOT NULL
        , TERRAFORMED_MAX_TEMP FLOAT NOT NULL
        , DEFAULT_ATM_PRESSURE_PASCAL FLOAT NOT NULL
        , TERRAFORMED_ATM_PRESSURE_PASCAL FLOAT NOT NULL
        , PRIMARY KEY (TERRAFORMING_STEP_ID)
    );
'''

create_dimension_tables = '''
    CREATE TABLE DIM_ACTIVITIES (
          ACTIVITY_ID INT IDENTITY(0,1)
        , ACTIVITY_NAME VARCHAR(100) NOT NULL
        , ACTIVITY_TYPE VARCHAR(10) NOT NULL
        , PRIMARY KEY(ACTIVITY_ID)
    );

    CREATE TABLE DIM_ORGANISATIONS (
          ORG_ID INT IDENTITY(0,1)
        , NAME VARCHAR(100) NOT NULL
        , PRIMARY KEY(ORG_ID)
    );

    CREATE TABLE DIM_MARS_ATLAS (
          LOC_ID INT IDENTITY(0,1)
        , NAME VARCHAR(100) NOT NULL
        , PRIMARY KEY(LOC_ID)
    );

    CREATE TABLE DIM_MARS_TIME (
          SOL INT
        , PRIMARY KEY(SOL)
    );

    CREATE TABLE DIM_EARTH_TIME (
          START_TIME DATETIME
        , HOUR INT NOT NULL
        , DAY INT NOT NULL
        , MONTH INT NOT NULL
        , YEAR INT NOT NULL
        , PRIMARY KEY(START_TIME)
    );
'''



# STAGING TABLES
copy_staging_atmosphere = '''
    COPY STAGING_ATMOSPHERE
    FROM '{}atmosphere-data/atmosphere-forecast.csv'
    REGION '{}'
    ACCESS_KEY_ID '{}'
    SECRET_ACCESS_KEY '{}'
    FORMAT AS CSV;
'''.format('s3:' + (config['S3']['OUTPUT_BUCKET']).split(':')[1], config['S3']['INPUT_BUCKET_REGION'], config['AWS']['KEY'], config['AWS']['SECRET'])

copy_staging_schedule = '''
    COPY STAGING_SCHEDULE
    FROM '{}schedule-data/schedule.csv'
    REGION '{}'
    ACCESS_KEY_ID '{}'
    SECRET_ACCESS_KEY '{}'
    FORMAT AS CSV;
'''.format('s3:' + (config['S3']['OUTPUT_BUCKET']).split(':')[1], config['S3']['INPUT_BUCKET_REGION'], config['AWS']['KEY'], config['AWS']['SECRET'])

# FINAL TABLES
insert_dim_tables = '''

    -- ACTIVITIES
    INSERT INTO DIM_ACTIVITIES (ACTIVITY_NAME, ACTIVITY_TYPE)
    SELECT DISTINCT
          ACTIVITY AS ACTIVITY_NAME
        , ACTIVITY_TYPE
    FROM STAGING_SCHEDULE;


    -- ORGANISATIONS
    INSERT INTO DIM_ORGANISATIONS(NAME)
    SELECT DISTINCT
          ACTIVITY_HANDLER AS NAME
    FROM STAGING_SCHEDULE;


    -- MARS LOCATION
    INSERT INTO DIM_MARS_ATLAS(NAME)
    SELECT DISTINCT
          MARTIAN_ACTIVITY_LOCATION AS NAME
    FROM STAGING_SCHEDULE;

    -- MARS TIME
    INSERT INTO DIM_MARS_TIME(SOL)
    SELECT DISTINCT
          MARTIAN_SOL AS SOL
    FROM STAGING_ATMOSPHERE;

    -- EARTH TIME
    CREATE OR REPLACE FUNCTION from_unixtime(epoch NUMERIC)
        RETURNS TIMESTAMP  AS
'import datetime
return datetime.datetime.fromtimestamp(epoch)'
    LANGUAGE plpythonu IMMUTABLE;

    INSERT INTO DIM_EARTH_TIME(START_TIME, HOUR, DAY, MONTH, YEAR)
    SELECT DISTINCT
          from_unixtime(EXECUTION_DATETIME) AS START_TIME
        , 0
        , 0
        , 0
        , 0
    FROM STAGING_SCHEDULE;

    UPDATE DIM_EARTH_TIME
    SET 
          HOUR = CAST(EXTRACT(HOUR FROM START_TIME) AS INTEGER)
        , DAY = CAST(EXTRACT(DAY FROM START_TIME) AS INTEGER)
        , MONTH = CAST(EXTRACT(MONTH FROM START_TIME) AS INTEGER)
        , YEAR = CAST(EXTRACT(YEAR FROM START_TIME) AS INTEGER)
'''

insert_fact_table = '''
        CREATE OR REPLACE FUNCTION from_unixtime(epoch NUMERIC)
        RETURNS TIMESTAMP  AS
'import datetime
return datetime.datetime.fromtimestamp(epoch)'
        LANGUAGE plpythonu IMMUTABLE;


        INSERT INTO FACT_TERRAFORMANCE (
          ACTIVITY_ID
        , ORGANISATION_ID
        , LOC_ID
        , SOL
        , ACTIVITY_EXECUTION_TIME
        , MARS_SUN_ANGLE
        , DEFAULT_MIN_TEMP
        , DEFAULT_AVG_TEMP
        , DEFAULT_MAX_TEMP
        , TERRAFORMED_MIN_TEMP
        , TERRAFORMED_AVG_TEMP
        , TERRAFORMED_MAX_TEMP
        , DEFAULT_ATM_PRESSURE_PASCAL
        , TERRAFORMED_ATM_PRESSURE_PASCAL
    )

    SELECT
          A.ACTIVITY_ID
        , O.ORG_ID
        , L.LOC_ID
        , ATM.MARTIAN_SOL AS SOL
        , CASE WHEN SCH.EXECUTION_DATETIME IS NULL
                THEN NULL
               ELSE from_unixtime(SCH.EXECUTION_DATETIME) END AS ACTIVITY_EXECUTION_TIME
        , ATM.MARS_SUN_ANGLE
        , ATM.DEFAULT_MIN_TEMP
        , ATM.DEFAULT_AVG_TEMP
        , ATM.DEFAULT_MAX_TEMP
        , ATM.TERRAFORMED_MIN_TEMP
        , ATM.TERRAFORMED_AVG_TEMP
        , ATM.TERRAFORMED_MAX_TEMP
        , ATM.DEFAULT_ATM_PRESSURE_PASCAL
        , ATM.TERRAFORMED_ATM_PRESSURE_PASCAL
    FROM
          STAGING_ATMOSPHERE ATM
            LEFT JOIN STAGING_SCHEDULE SCH ON ATM.MARTIAN_SOL = SCH.SOL
            LEFT JOIN DIM_ACTIVITIES A ON SCH.ACTIVITY = A.ACTIVITY_NAME AND SCH.ACTIVITY_TYPE = A.ACTIVITY_TYPE 
            LEFT JOIN DIM_ORGANISATIONS O ON SCH.ACTIVITY_HANDLER = O.NAME
            LEFT JOIN DIM_MARS_ATLAS L ON SCH.MARTIAN_ACTIVITY_LOCATION = L.NAME
'''

# QUERY LISTS

create_table_queries = [create_staging_tables, create_fact_table, create_dimension_tables]
drop_table_queries = [drop_all_tables]
copy_table_queries = [copy_staging_atmosphere, copy_staging_schedule]
insert_table_queries = [insert_dim_tables, insert_fact_table]

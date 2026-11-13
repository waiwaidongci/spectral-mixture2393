"""Upgrade an existing database to blank-calibration joint noise.

New databases are created from SQLAlchemy metadata, so this script only needs to
run for databases created before this feature. It is idempotent and checks
``information_schema`` rather than relying on MySQL-only ``IF NOT EXISTS`` syntax.
"""
from sqlalchemy import text
from ..config.database import engine

CREATE_TABLE = (
    "CREATE TABLE blank_calibrations ("
    "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,"
    "library_id INT NOT NULL,"
    "name VARCHAR(120) NOT NULL,"
    "source VARCHAR(160) NOT NULL DEFAULT '',"
    "readings JSON NOT NULL,"
    "band_count INT NOT NULL,"
    "rule_version VARCHAR(64) NOT NULL,"
    "source_hash VARCHAR(64) NOT NULL,"
    "calibration_hash VARCHAR(64) NOT NULL UNIQUE,"
    "estimate JSON NOT NULL,"
    "effective_measurements INT NOT NULL,"
    "degrees_of_freedom INT NOT NULL,"
    "noise_rms DOUBLE NOT NULL,"
    "condition_number DOUBLE NOT NULL,"
    "derived_from_id INT NULL,"
    "owner VARCHAR(100) NOT NULL,"
    "created_at VARCHAR(64) NOT NULL,"
    "UNIQUE KEY blank_calibration_library_name (library_id,name),"
    "CONSTRAINT blank_calibration_library FOREIGN KEY (library_id) REFERENCES spectral_libraries(id),"
    "CONSTRAINT blank_calibration_derived FOREIGN KEY (derived_from_id) REFERENCES blank_calibrations(id)"
    ") CHARACTER SET utf8mb4"
)

def _columns(connection, table):
    rows = connection.execute(text(
        "SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:table"
    ), {"table": table}).scalars().all()
    return set(rows)

def upgrade():
    with engine.begin() as connection:
        tables = connection.execute(text(
            "SELECT TABLE_NAME FROM information_schema.tables WHERE table_schema=DATABASE()"
        )).scalars().all()
        if "blank_calibrations" not in tables:
            connection.execute(text(CREATE_TABLE))
        columns = _columns(connection, "unmix_runs")
        if "noise_sigma" in columns:
            # Joint-noise runs have no independent sigma; old rows keep their value.
            connection.execute(text("ALTER TABLE unmix_runs MODIFY noise_sigma DOUBLE NULL"))
        if "calibration_id" not in columns:
            connection.execute(text("ALTER TABLE unmix_runs ADD COLUMN calibration_id INT NULL"))
            connection.execute(text(
                "ALTER TABLE unmix_runs ADD CONSTRAINT unmix_run_calibration "
                "FOREIGN KEY (calibration_id) REFERENCES blank_calibrations(id)"
            ))
        if "calibration_library_idx" not in {i["Key_name"] for i in connection.execute(text("SHOW INDEX FROM blank_calibrations")).mappings()}:
            connection.execute(text("CREATE INDEX calibration_library_idx ON blank_calibrations (library_id)"))

if __name__ == "__main__":
    upgrade()

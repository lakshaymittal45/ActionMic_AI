"""
Database migration utilities for ActionMic AI.
Auto-runs migrations on app startup to ensure schema is in sync.
"""
import logging
import os

logger = logging.getLogger(__name__)


def ensure_tables_exist(connection):
    """
    Run all pending migrations and table setups.
    Safe to call multiple times — skips if already created.
    """
    cursor = None
    try:
        cursor = connection.cursor()

        # 1. Migration for audio_records (if it exists)
        try:
            cursor.execute("""
                ALTER TABLE audio_records
                ADD COLUMN transcript_corrected_encrypted TEXT DEFAULT NULL
                AFTER transcript_encrypted
            """)
            connection.commit()
            logger.info("✅ Migration: added transcript_corrected_encrypted column")
        except Exception as e:
            error_msg = str(e)
            if "Duplicate column" in error_msg or "already exists" in error_msg or "Table" in error_msg:
                pass
            else:
                logger.warning(f"Column check notice: {error_msg}")

        # 2. Ensure ActionMic tables exist
        current_dir = os.path.dirname(__file__)
        schema_path = os.path.join(current_dir, "actionmic_schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                sql_content = f.read()

            for statement in sql_content.split(";"):
                stmt = statement.strip()
                if stmt and not stmt.upper().startswith("USE "):
                    try:
                        cursor.execute(stmt)
                    except Exception as ex:
                        err_str = str(ex).lower()
                        if "already exists" not in err_str and "duplicate" not in err_str:
                            logger.debug(f"Schema statement warning: {ex}")
            connection.commit()
            logger.info("✅ ActionMic schema tables verified / applied.")

    finally:
        if cursor:
            cursor.close()


def run_startup_migrations():
    """
    Entry point for startup migrations.
    Called by app.main on server startup.
    """
    from app.db.mysql_connection import get_mysql_connection

    conn = None
    try:
        logger.info("🔧 Running startup migrations...")
        conn = get_mysql_connection()
        ensure_tables_exist(conn)
        logger.info("✅ All migrations completed successfully")
    except Exception as e:
        logger.error(f"❌ Startup migrations failed: {e}")
        # Non-fatal if DB is temporarily busy, but log clearly
    finally:
        if conn:
            conn.close()

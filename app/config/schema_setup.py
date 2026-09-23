from sqlalchemy import text

from app.config.logging_config import get_logger

logger = get_logger(class_name=__name__)

# Database-level append-only guard. The API already exposes no update/delete,
# and the hash chain detects tampering after the fact; these triggers also stop
# an accidental UPDATE/DELETE from a SQL console. Creating triggers needs the
# TRIGGER privilege (and SUPER or log_bin_trust_function_creators=1 when binary
# logging is on), so this is best effort: a failure is logged, not fatal.
_IMMUTABLE_TABLES = ("audit_logs", "audit_log_changes")


def _trigger_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        text("SELECT COUNT(*) FROM information_schema.TRIGGERS "
             "WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = :name"),
        {"name": name},
    ).scalar())


def install_immutability_triggers(engine) -> None:
    if engine.dialect.name != "mysql":
        return
    try:
        with engine.begin() as conn:
            for table in _IMMUTABLE_TABLES:
                for operation in ("UPDATE", "DELETE"):
                    name = f"trg_{table}_no_{operation.lower()}"
                    if _trigger_exists(conn, name):
                        continue
                    conn.execute(text(
                        f"CREATE TRIGGER {name} BEFORE {operation} ON {table} FOR EACH ROW "
                        f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{table} is append-only'"
                    ))
                    logger.info(f"Installed append-only trigger {name}")
    except Exception as e:
        logger.warning(f"Could not install append-only triggers (hash chain still applies): {e}")

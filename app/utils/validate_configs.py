from app.config import config


def validate_config_vars():
    required = list(config.REQUIRED_CONFIG)
    if not config.DATABASE_URL_OVERRIDE:
        required += ["MYSQL_USER", "MYSQL_DB", "MYSQL_HOST", "MYSQL_PORT"]
    missing_vars = [name for name in required if not getattr(config, name, None)]
    if missing_vars:
        raise ValueError(f"Missing required configuration variables: {', '.join(missing_vars)}")

import os
from dotenv import load_dotenv

load_dotenv('.env')

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG')

MYSQL_USER = os.environ.get('MYSQL_USER', '')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_DB = os.environ.get('MYSQL_DB', '')
MYSQL_HOST = os.environ.get('MYSQL_HOST', '')
MYSQL_PORT = os.environ.get('MYSQL_PORT', '')

# Full SQLAlchemy URL override. Only used by tests (sqlite); deployments build the
# MySQL URL from the MYSQL_* variables above.
DATABASE_URL_OVERRIDE = os.environ.get('AUDIT_DATABASE_URL', '')

# Validates caller tokens (GET /access/by-auth-header), exactly like the other services.
USER_MANAGER_URL = os.environ.get("USER_MANAGER_URL", '')

# Shared secret the orchestrator (and any other trusted service) sends in the
# X-Audit-Service-Key header to write audit events. Browsers never hold it, so an
# end user cannot forge or inject audit records.
AUDIT_SERVICE_KEY = os.environ.get("AUDIT_SERVICE_KEY", '')

# Upper bound on rows a single CSV export may contain.
AUDIT_EXPORT_MAX_ROWS = int(os.environ.get("AUDIT_EXPORT_MAX_ROWS", 50000))

# Required settings, checked on startup by validate_config_vars().
REQUIRED_CONFIG = ("USER_MANAGER_URL", "AUDIT_SERVICE_KEY")

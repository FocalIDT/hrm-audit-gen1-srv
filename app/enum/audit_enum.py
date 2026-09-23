from enum import Enum


class AuditModule(str, Enum):
    """Where in the HRM the action happened (the "Module" column / filter)."""
    EMPLOYEE = "Employee"
    PAYROLL = "Payroll"
    LEAVE = "Leave"
    WFH = "WFH"
    SPECIAL_REQUESTS = "Special Requests"
    ATTENDANCE = "Attendance"
    OVERTIME = "Overtime"
    DOCUMENTS = "Documents"
    LETTERS = "Letters"
    DEPARTMENTS = "Departments"
    HIERARCHY = "Hierarchy"
    USER_ACCESS = "User & Access"
    IMPORT_EXPORT = "Import/Export"
    SYSTEM_CONFIGURATION = "System Configuration"


class AuditCategory(str, Enum):
    """The 19 top-level audit categories from the requirements (section 23)."""
    EMPLOYEE = "Employee"
    PROMOTION = "Promotion"
    SALARY = "Salary"
    PAYROLL = "Payroll"
    EPF = "EPF"
    ETF = "ETF"
    PAYE = "PAYE"
    LEAVE = "Leave"
    WFH = "WFH"
    SPECIAL_REQUESTS = "Special Requests"
    ATTENDANCE = "Attendance"
    OVERTIME = "Overtime"
    DOCUMENTS = "Documents"
    LETTERS = "Letters"
    DEPARTMENTS = "Departments"
    HIERARCHY = "Hierarchy"
    USER_ACCESS = "User & Access"
    IMPORT_EXPORT = "Import/Export"
    SYSTEM_CONFIGURATION = "System Configuration"


class AuditStatus(str, Enum):
    SUCCESS = "Success"
    FAILED = "Failed"


class ChangeValueType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    CURRENCY = "currency"
    DATE = "date"
    BOOLEAN = "boolean"


# Event types that feed the employee history view (career timeline, salary
# growth, promotion registry). Emitters must use these exact codes.
EVENT_EMPLOYEE_CREATED = "EMPLOYEE_CREATED"
EVENT_EMPLOYEE_PROMOTED = "EMPLOYEE_PROMOTED"
EVENT_DESIGNATION_CHANGED = "DESIGNATION_CHANGED"
EVENT_SALARY_INCREMENT = "SALARY_INCREMENT"
EVENT_SALARY_DECREMENT = "SALARY_DECREMENT"
EVENT_SALARY_CREATED = "SALARY_CREATED"

CAREER_EVENT_TYPES = (EVENT_EMPLOYEE_CREATED, EVENT_EMPLOYEE_PROMOTED, EVENT_DESIGNATION_CHANGED)
SALARY_EVENT_TYPES = (EVENT_EMPLOYEE_CREATED, EVENT_EMPLOYEE_PROMOTED, EVENT_SALARY_INCREMENT,
                      EVENT_SALARY_DECREMENT, EVENT_SALARY_CREATED)

# Change-row field keys the history view reads.
FIELD_DESIGNATION = "designation"
FIELD_BASIC_SALARY = "basic_salary"
FIELD_DEPARTMENT = "department"

# Modules whose events represent an employee request (requirements section 14).
REQUEST_MODULES = (AuditModule.LEAVE.value, AuditModule.WFH.value, AuditModule.SPECIAL_REQUESTS.value)

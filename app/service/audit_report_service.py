"""PDF exports for the "Download Report" buttons (audit record and employee history)."""
import io
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils.formatters import format_audit_detail
from app.utils.hashing import utc_now

_INDIGO = colors.HexColor("#4F46E5")
_SLATE = colors.HexColor("#334155")
_MUTED = colors.HexColor("#64748B")
_BORDER = colors.HexColor("#E2E8F0")
_HEADER_BG = colors.HexColor("#F1F5F9")

_styles = getSampleStyleSheet()
_TITLE = ParagraphStyle("AuditTitle", parent=_styles["Title"], fontSize=16, textColor=_SLATE, alignment=0,
                        spaceAfter=2)
_SUBTITLE = ParagraphStyle("AuditSubtitle", parent=_styles["Normal"], fontSize=8, textColor=_MUTED,
                           spaceAfter=10)
_SECTION = ParagraphStyle("AuditSection", parent=_styles["Heading3"], fontSize=11, textColor=_INDIGO,
                          spaceBefore=10, spaceAfter=6)
_CELL = ParagraphStyle("AuditCell", parent=_styles["Normal"], fontSize=8, leading=10, textColor=_SLATE)
_CELL_BOLD = ParagraphStyle("AuditCellBold", parent=_CELL, fontName="Helvetica-Bold")


def _text(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _money(value: Optional[float]) -> str:
    return "-" if value is None else f"LKR {value:,.2f}"


def _pct(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:+.1f}%"


def _grid(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    data = [[Paragraph(_text(cell), _CELL_BOLD if header and row_index == 0 else _CELL) for cell in row]
            for row_index, row in enumerate(rows)]
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, _BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG))
    table.setStyle(TableStyle(style))
    return table


def _key_values(pairs: list[tuple[str, Any]], width: float) -> Table:
    rows = []
    for index in range(0, len(pairs), 2):
        left = pairs[index]
        right = pairs[index + 1] if index + 1 < len(pairs) else ("", "")
        rows.append([
            Paragraph(_text(left[0]), _CELL_BOLD), Paragraph(_text(left[1]), _CELL),
            Paragraph(_text(right[0]) if right[0] else "", _CELL_BOLD),
            Paragraph(_text(right[1]) if right[0] else "", _CELL),
        ])
    table = Table(rows, colWidths=[width * 0.17, width * 0.33, width * 0.17, width * 0.33])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, _BORDER),
    ]))
    return table


def _build(story: list, title: str) -> bytes:
    buffer = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_MUTED)
        canvas.drawString(doc.leftMargin, 10 * mm,
                          f"{title} - generated {utc_now():%d %b %Y %H:%M} UTC - Confidential")
        canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=18 * mm, title=title)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


class AuditReportService:

    @classmethod
    def audit_record_pdf(cls, record, related: list) -> bytes:
        detail = format_audit_detail(record, related)
        width = A4[0] - 30 * mm
        story = [
            Paragraph(f"Audit Record Details - {detail['audit_id']}", _TITLE),
            Paragraph("System activity history", _SUBTITLE),
            _key_values([
                ("Date & Time (UTC)", detail["occurred_at"]),
                ("Status", detail["status"]),
                ("Employee", detail["employee_name"]),
                ("Employee ID", detail["employee_code"]),
                ("Module", detail["module"]),
                ("Category", detail["category"]),
                ("Action", detail["action"]),
                ("Description", detail["description"]),
                ("Performed By", detail["performed_by_name"]),
                ("User Role", detail["performed_by_role"]),
                ("Reason", detail["reason"]),
                ("Remarks", detail["remarks"]),
                ("Reference Type", detail["reference_type"]),
                ("Reference ID", detail["reference_id"]),
                ("Request ID", detail["request_id"]),
                ("Effective Date", detail["effective_date"]),
                ("Payroll Period", detail["payroll_period"]),
                ("IP Address", detail["ip_address"]),
            ], width),
        ]
        if detail["changes"]:
            story += [Paragraph("Change Details", _SECTION),
                      _grid([["Field", "Previous Value", "New Value"]] +
                            [[c["field_label"], c["old_value"], c["new_value"]] for c in detail["changes"]],
                            [width * 0.3, width * 0.35, width * 0.35])]
        assigned = [e for e in detail["details"].get("assigned_employees") or [] if isinstance(e, dict)]
        if assigned:
            story += [Paragraph("Employee Details", _SECTION),
                      _grid([["Employee No.", "Employee Name"]] +
                            [[e.get("number"), e.get("name") or "Unknown employee"] for e in assigned],
                            [width * 0.25, width * 0.75])]
        other_details = {k: v for k, v in detail["details"].items() if k != "assigned_employees"}
        if other_details:
            story += [Paragraph("Additional Information", _SECTION),
                      _grid([["Item", "Value"]] + [[key.replace("_", " ").title(), value]
                                                   for key, value in other_details.items()],
                            [width * 0.35, width * 0.65])]
        if detail["related"]:
            story += [Paragraph("Related Events (same operation)", _SECTION),
                      _grid([["Audit ID", "Action", "Description"]] +
                            [[r["audit_id"], r["action"], r["description"]] for r in detail["related"]],
                            [width * 0.2, width * 0.3, width * 0.5])]
        story += [Spacer(1, 8), Paragraph(f"Record hash: {detail['record_hash']}", _SUBTITLE)]
        return _build(story, f"Audit record {detail['audit_id']}")

    @classmethod
    def employee_history_pdf(cls, history: dict) -> bytes:
        width = A4[0] - 30 * mm
        employee = history.get("employee") or {}
        summary = history.get("summary") or {}
        story = [
            Paragraph(f"Audit Log - Employee History: {_text(employee.get('employee_name'))}", _TITLE),
            Paragraph(_text(employee.get("employee_code")), _SUBTITLE),
            _key_values([
                ("Current Designation", employee.get("current_designation")),
                ("Department", employee.get("current_department")),
                ("Current Salary", _money(employee.get("current_salary"))),
                ("Overall Salary Increase", _pct(summary.get("overall_salary_increase_pct"))),
                ("Total Promotions", summary.get("total_promotions")),
                ("Recorded Events", summary.get("total_events")),
            ], width),
        ]
        timeline = history.get("career_timeline") or []
        if timeline:
            story += [Paragraph("Career Progression Timeline", _SECTION),
                      _grid([["Designation", "Department", "From", "To", "Salary", "Increment"]] +
                            [[t["designation"], t["department"], t["start_date"],
                              "Present" if t.get("is_current") else t["end_date"],
                              _money(t["salary"]), _pct(t.get("increment_pct"))] for t in timeline],
                            [width * 0.24, width * 0.18, width * 0.14, width * 0.14, width * 0.17, width * 0.13])]
        promotions = history.get("promotions") or []
        if promotions:
            story += [Paragraph("Detailed Promotion Registry", _SECTION),
                      _grid([["Effective Date", "Previous Role", "New Role", "Prev. Salary", "New Salary",
                              "Increment", "Approved By", "Ref ID"]] +
                            [[p["effective_date"], p["previous_role"], p["new_role"], _money(p["previous_salary"]),
                              _money(p["new_salary"]), _pct(p["increment_pct"]), p["approved_by"],
                              p["reference_id"]] for p in promotions],
                            [width * 0.11, width * 0.15, width * 0.15, width * 0.13, width * 0.13, width * 0.09,
                             width * 0.13, width * 0.11])]
        requests = history.get("requests") or []
        if requests:
            story += [Paragraph("Employee Request History", _SECTION),
                      _grid([["Type", "Request ID", "Requested", "Status", "Responsible", "Completed"]] +
                            [[r["request_type"], r["request_id"], r["requested_at"], r["status"],
                              r["responsible_person"], r["completed_at"]] for r in requests],
                            [width * 0.18, width * 0.12, width * 0.2, width * 0.16, width * 0.14, width * 0.2])]
        return _build(story, f"Employee history {_text(employee.get('employee_code'))}")


audit_report_service = AuditReportService()

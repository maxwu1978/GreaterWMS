"""
Server-side PDF generation for survey assessment reports.
Uses reportlab (lightweight, no system deps unlike weasyprint).
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_survey_pdf(data: dict) -> bytes:
    """Generate a professional multi-page PDF from survey data."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            fontSize=14,
            textColor=colors.HexColor("#1e40af"),
            spaceAfter=8,
            spaceBefore=16,
            fontName="Helvetica-Bold",
        )
    )
    styles.add(
        ParagraphStyle(
            name="FieldLabel",
            fontSize=9,
            textColor=colors.HexColor("#64748b"),
            fontName="Helvetica-Bold",
        )
    )
    styles.add(
        ParagraphStyle(
            name="FieldValue", fontSize=10, textColor=colors.HexColor("#0f172a"), spaceAfter=6
        )
    )
    styles.add(ParagraphStyle(name="SmallGray", fontSize=8, textColor=colors.HexColor("#94a3b8")))

    elements = []

    # ─── Header ───
    header_data = [
        [
            Paragraph(
                '<font size="18" color="#1e40af"><b>WMS Readiness Assessment</b></font>',
                styles["Normal"],
            ),
            Paragraph(
                f'<font size="9" color="#64748b">{datetime.now().strftime("%B %d, %Y")}<br/>Confidential</font>',
                styles["Normal"],
            ),
        ]
    ]
    header_table = Table(header_data, colWidths=[4 * inch, 2.5 * inch])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e40af")))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("GreenEcoPower Corp | WMS QuickStart", styles["SmallGray"]))
    elements.append(Spacer(1, 16))

    def section(title):
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(title, styles["SectionTitle"]))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
        elements.append(Spacer(1, 6))

    def field_row(label, value):
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        value = str(value) if value else "—"
        row_data = [
            [
                Paragraph(
                    f'<font size="9" color="#64748b"><b>{label}</b></font>', styles["Normal"]
                ),
                Paragraph(f'<font size="10">{value}</font>', styles["Normal"]),
            ]
        ]
        t = Table(row_data, colWidths=[2.2 * inch, 4.3 * inch])
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#f1f5f9")),
                ]
            )
        )
        elements.append(t)

    def pain_row(label, value):
        """Render a pain point with visual score bar."""
        val = int(value) if value else 0
        bar = ""
        for i in range(1, 6):
            if i <= val:
                if val <= 2:
                    c = "#22c55e"  # green
                elif val <= 3:
                    c = "#f59e0b"  # amber
                else:
                    c = "#ef4444"  # red
                bar += f'<font color="{c}">&#9632; </font>'
            else:
                bar += '<font color="#e2e8f0">&#9632; </font>'
        bar += f'  <font size="9" color="#64748b">{val}/5</font>'
        field_row(label, bar)

    # ─── Section 1 ───
    section("1. Company Profile")
    field_row("Company", data.get("company_name"))
    field_row("Contact", data.get("contact_name"))
    field_row("Email", data.get("email"))
    field_row("Phone", data.get("phone"))
    field_row("Business Type", data.get("business_type"))
    field_row("Location", data.get("location"))

    # ─── Section 2 ───
    section("2. Current Scale")
    field_row("Warehouse Size", data.get("warehouse_sqft"))
    field_row("Staff Count", data.get("staff_count"))
    field_row("Clients Served", data.get("client_count"))
    field_row("Daily Orders", data.get("daily_orders"))
    field_row("SKU Count", data.get("sku_count"))

    # ─── Section 3 ───
    section("3. Current Tools & Process")
    field_row("Tracking Method", data.get("current_tools"))
    field_row("Current Software", data.get("current_software"))
    field_row("Barcode Use", data.get("barcode_use"))
    field_row("Order Sources", data.get("order_sources"))

    # ─── Section 4 ───
    section("4. Pain Points")
    pain_row("Inventory Accuracy", data.get("pain_accuracy"))
    pain_row("Order Errors", data.get("pain_errors"))
    pain_row("Slow Fulfillment", data.get("pain_speed"))
    pain_row("Billing Headaches", data.get("pain_billing"))
    pain_row("Client Visibility", data.get("pain_visibility"))
    pain_row("Labor Dependency", data.get("pain_labor"))
    pain_row("Scaling Problems", data.get("pain_scaling"))
    if data.get("top_frustration"):
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b>Top Frustration:</b>", styles["FieldLabel"]))
        elements.append(Paragraph(f'<i>"{data["top_frustration"]}"</i>', styles["FieldValue"]))

    # ─── Section 5 ───
    section("5. Feature Priorities")
    pain_row("Barcode Scanning", data.get("feat_barcode"))
    pain_row("Multi-Client Support", data.get("feat_multiclient"))
    pain_row("Client Portal", data.get("feat_portal"))
    pain_row("Automated Billing", data.get("feat_billing"))
    pain_row("Shopify/Amazon", data.get("feat_ecommerce"))
    pain_row("Shipping Labels", data.get("feat_shipping"))
    pain_row("Lot/Expiry Tracking", data.get("feat_lot"))
    pain_row("Mobile Phone Scanning", data.get("feat_mobile"))

    # ─── Section 6 ───
    section("6. Automation & Future")
    field_row("AGV Awareness", data.get("agv_awareness"))
    field_row("AGV Interest", data.get("agv_interest"))
    field_row("Automation Triggers", data.get("agv_triggers"))

    # ─── Section 7: Open-ended ───
    section("7. Specific Needs & Requirements")

    open_fields = [
        ("product_types", "Product Types & Special Handling"),
        ("current_process", "Current Fulfillment Process"),
        ("wish_list", "Top 3 Wishes for a WMS"),
        ("compliance_needs", "Compliance & Reporting Requirements"),
        ("peak_season", "Peak Season Description"),
        ("one_problem", "The #1 Problem to Solve"),
        ("wms_trigger", "What Triggered the WMS Search"),
        ("past_wms_experience", "Past WMS Experience"),
    ]
    for key, label in open_fields:
        val = data.get(key)
        if val and str(val).strip():
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(f"<b>{label}:</b>", styles["FieldLabel"]))
            elements.append(Paragraph(f'<i>"{val}"</i>', styles["FieldValue"]))

    # ─── Section 8 ───
    section("8. Budget & Timeline")
    field_row("Timeline", data.get("timeline"))
    field_row("Budget", data.get("budget"))
    field_row("Vendor Priorities", data.get("vendor_priority"))
    if data.get("additional_notes"):
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b>Additional Notes:</b>", styles["FieldLabel"]))
        elements.append(Paragraph(data["additional_notes"], styles["FieldValue"]))

    # ─── Footer ───
    elements.append(Spacer(1, 24))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            "WMS QuickStart Assessment Report | GreenEcoPower Corp | Mansfield, TX 76063 | wuqxmark@gmail.com",
            styles["SmallGray"],
        )
    )

    doc.build(elements)
    return buf.getvalue()

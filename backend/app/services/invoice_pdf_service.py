"""
Invoice PDF generation using WeasyPrint.

Generates a professional invoice PDF from billing data.
In production, PDFs are stored to S3 and the path saved to Invoice.pdf_path.
"""

from datetime import date

from weasyprint import HTML


def generate_invoice_pdf(
    invoice_number: str,
    tenant_name: str,
    tenant_address: dict | None,
    tenant_tax_id: str | None,
    tenant_vat_id: str | None,
    tenant_billing_email: str | None,
    tenant_bank_name: str | None,
    tenant_bank_account: str | None,
    tenant_iban: str | None,
    tenant_swift: str | None,
    client_name: str,
    client_address: dict | None,
    client_tax_id: str | None,
    client_vat_id: str | None,
    client_billing_email: str | None,
    issued_date: date,
    due_date: date | None,
    service_period: str | None,
    payment_terms_label: str | None,
    tax_region: str | None,
    tax_label: str | None,
    tax_rate_pct: float | None,
    tax_legal_note: str | None,
    footer_legal_note: str | None,
    line_items: list[dict],
    subtotal: float,
    tax_amount: float,
    total_amount: float,
    currency: str = "USD",
    notes: str | None = None,
) -> bytes:
    """
    Generate invoice PDF and return as bytes.

    line_items: [{"description": "...", "quantity": 10, "unit_price": 0.50, "total_amount": 5.00}, ...]
    """
    # Build line items HTML
    items_html = ""
    for item in line_items:
        items_html += f"""
        <tr>
            <td>{item["description"]}</td>
            <td class="right">{item["quantity"]}</td>
            <td class="right">{_format_money(item["unit_price"], currency)}</td>
            <td class="right">{_format_money(item["total_amount"], currency)}</td>
        </tr>
        """

    tenant_addr = _format_address(tenant_address) if tenant_address else ""
    client_addr = _format_address(client_address) if client_address else ""
    tenant_meta = _format_meta_lines(
        [
            ("Tax ID", tenant_tax_id),
            ("VAT ID", tenant_vat_id),
            ("Billing email", tenant_billing_email),
            ("Bank", tenant_bank_name),
            ("Account", tenant_bank_account),
            ("IBAN", tenant_iban),
            ("SWIFT", tenant_swift),
        ]
    )
    client_meta = _format_meta_lines(
        [
            ("Tax ID", client_tax_id),
            ("VAT ID", client_vat_id),
            ("Billing email", client_billing_email),
        ]
    )
    period_label = service_period or "—"
    terms_label = payment_terms_label or ("Upon Receipt" if due_date is None else "Custom terms")
    normalized_tax_region = (tax_region or "eu").lower()
    tax_title = tax_label or ("Sales Tax" if normalized_tax_region == "us" else "VAT")
    tax_rate_label = f"{float(tax_rate_pct or 0):.2f}%"
    tax_region_label = "US tax profile" if normalized_tax_region == "us" else "EU VAT profile"
    tax_meta_label = f"{tax_title} · {tax_rate_label}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
            .header {{ display: flex; justify-content: space-between; margin-bottom: 40px; }}
            .header h1 {{ color: #2563eb; margin: 0; font-size: 28px; }}
            .invoice-number {{ font-size: 14px; color: #666; }}
            .addresses {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
            .address-block {{ width: 45%; }}
            .address-block h3 {{ color: #666; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th {{ background: #f8fafc; border-bottom: 2px solid #e2e8f0; padding: 10px 8px;
                 text-align: left; font-size: 12px; text-transform: uppercase; color: #666; }}
            td {{ padding: 10px 8px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }}
            .right {{ text-align: right; }}
            .totals {{ margin-top: 20px; margin-left: auto; width: 300px; }}
            .totals table {{ width: 100%; }}
            .totals td {{ border: none; padding: 5px 8px; }}
            .total-row {{ font-weight: bold; font-size: 16px; border-top: 2px solid #333 !important; }}
            .footer {{ margin-top: 40px; font-size: 11px; color: #999; text-align: center; }}
            .meta-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
            .meta-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; }}
            .meta-card h3 {{ color: #666; font-size: 11px; text-transform: uppercase; margin-bottom: 6px; }}
            .meta-card p {{ margin: 0; font-size: 12px; line-height: 1.6; }}
            .notes {{ margin-top: 24px; border-top: 1px dashed #cbd5e1; padding-top: 16px; }}
            .notes h3 {{ color: #666; font-size: 11px; text-transform: uppercase; margin-bottom: 6px; }}
            .notes p {{ margin: 0 0 8px; font-size: 12px; line-height: 1.65; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <h1>INVOICE</h1>
                <p class="invoice-number">{invoice_number}</p>
            </div>
            <div style="text-align: right;">
                <p><strong>Date:</strong> {issued_date.strftime("%B %d, %Y")}</p>
                <p><strong>Due:</strong> {
        due_date.strftime("%B %d, %Y") if due_date else "Upon Receipt"
    }</p>
            </div>
        </div>

        <div class="addresses">
            <div class="address-block">
                <h3>From</h3>
                <p><strong>{tenant_name}</strong></p>
                <p>{tenant_addr}</p>
                <p>{tenant_meta}</p>
            </div>
            <div class="address-block">
                <h3>Bill To</h3>
                <p><strong>{client_name}</strong></p>
                <p>{client_addr}</p>
                <p>{client_meta}</p>
            </div>
        </div>

        <div class="meta-grid">
            <div class="meta-card">
                <h3>Service Period</h3>
                <p>{period_label}</p>
            </div>
            <div class="meta-card">
                <h3>Payment Terms</h3>
                <p>{terms_label}</p>
            </div>
            <div class="meta-card">
                <h3>Currency</h3>
                <p>{currency}</p>
            </div>
            <div class="meta-card">
                <h3>Tax Treatment</h3>
                <p>{tax_meta_label}<br>{tax_region_label}</p>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Description</th>
                    <th class="right">Qty</th>
                    <th class="right">Unit Price</th>
                    <th class="right">Amount</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>

        <div class="totals">
            <table>
                <tr>
                    <td>Subtotal</td>
                    <td class="right">{_format_money(subtotal, currency)}</td>
                </tr>
                <tr>
                    <td>{tax_title} ({tax_rate_label})</td>
                    <td class="right">{_format_money(tax_amount, currency)}</td>
                </tr>
                <tr class="total-row">
                    <td>Total ({currency})</td>
                    <td class="right">{_format_money(total_amount, currency)}</td>
                </tr>
            </table>
        </div>

        {
        f'''
        <div class="notes">
            <h3>Notes</h3>
            <p>{notes}</p>
            {f"<p><strong>Tax note:</strong> {tax_legal_note}</p>" if tax_legal_note else ""}
            {f"<p><strong>Legal footer:</strong> {footer_legal_note}</p>" if footer_legal_note else ""}
        </div>
        '''
        if notes or tax_legal_note or footer_legal_note
        else ""
    }

        <div class="footer">
            <p>Generated by WMS QuickStart | Thank you for your business</p>
        </div>
    </body>
    </html>
    """

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes


def _format_address(addr: dict) -> str:
    parts = []
    if addr.get("street"):
        parts.append(addr["street"])
    city_state = ""
    if addr.get("city"):
        city_state = addr["city"]
    if addr.get("state"):
        city_state += f", {addr['state']}"
    if addr.get("zip"):
        city_state += f" {addr['zip']}"
    if city_state:
        parts.append(city_state)
    if addr.get("country"):
        parts.append(addr["country"])
    return "<br>".join(parts)


def _format_meta_lines(items: list[tuple[str, str | None]]) -> str:
    lines: list[str] = []
    for label, value in items:
        if value:
            lines.append(f"<strong>{label}:</strong> {value}")
    return "<br>".join(lines)


def _format_money(amount: float, currency: str) -> str:
    return f"{currency} {float(amount):,.2f}"

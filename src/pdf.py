"""Render an order packing slip as PDF."""

from __future__ import annotations

from src.models import Order


def packing_slip_pdf_bytes(html: str, base_url: str) -> bytes:
    """Turn packing-slip HTML into a PDF. Requires WeasyPrint plus system cairo/pango."""
    from weasyprint import HTML

    pdf = HTML(string=html, base_url=base_url).write_pdf()
    if not pdf:
        raise RuntimeError("Could not render packing slip PDF")
    return pdf


def packing_slip_filename(order: Order) -> str:
    return f"order-{order.id}-packing-slip.pdf"

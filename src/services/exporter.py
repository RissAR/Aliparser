"""Excel (.xlsx) export service for scraped AliExpress products."""

import io
import re
import zipfile
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.db.models import Product

EXCEL_HEADERS = [
    "Item ID",
    "Product Title",
    "Price",
    "Original Price",
    "Currency",
    "Rating",
    "Orders",
    "Store",
    "Category / Query",
    "Product URL",
    "Image URL",
    "Scraped At (UTC)",
]

_XML_ILLEGAL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]")


def _clean_xml_string(value: Optional[str]) -> str:
    """Remove illegal XML control characters from a string."""
    if not value:
        return ""
    return _XML_ILLEGAL_CHARS_RE.sub("", str(value)).strip()


def _normalize_xlsx_zip(raw_bytes: bytes) -> bytes:
    """Normalize OOXML relationship paths in xl/_rels/workbook.xml.rels for strict compatibility."""
    in_buf = io.BytesIO(raw_bytes)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/_rels/workbook.xml.rels":
                text = data.decode("utf-8")
                text = text.replace('Target="/xl/', 'Target="')
                data = text.encode("utf-8")
            zout.writestr(item, data)
    return out_buf.getvalue()


def generate_products_excel(products: List[Product]) -> bytes:
    """Generate a formatted .xlsx workbook with clickable product links.

    Args:
        products: List of Product ORM objects.

    Returns:
        Raw bytes of the generated .xlsx file.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "AliExpress Products"

    # Freeze header row
    ws.freeze_panes = "A2"

    # Header styling (8-digit ARGB colors)
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
    header_fill = PatternFill(start_color="FF1E293B", end_color="FF1E293B", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    ws.append(EXCEL_HEADERS)
    for col_idx in range(1, len(EXCEL_HEADERS) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    data_font = Font(name="Calibri", size=10, color="FF0F172A")
    link_font = Font(name="Calibri", size=10, color="FF2563EB", underline="single")

    for row_idx, product in enumerate(products, start=2):
        scraped_str = (
            product.scraped_at.strftime("%Y-%m-%d %H:%M:%S")
            if product.scraped_at is not None
            else ""
        )

        clean_url = _clean_xml_string(product.product_url)
        row_values = [
            _clean_xml_string(product.item_id),
            _clean_xml_string(product.title),
            float(product.price) if product.price is not None else None,
            float(product.original_price) if product.original_price is not None else None,
            _clean_xml_string(product.currency or "USD"),
            float(product.rating) if product.rating is not None else None,
            _clean_xml_string(product.orders_count),
            _clean_xml_string(product.store_name),
            _clean_xml_string(product.category_or_query),
            clean_url,
            _clean_xml_string(product.image_url),
            scraped_str,
        ]
        ws.append(row_values)

        for col_idx in range(1, len(EXCEL_HEADERS) + 1):
            ws.cell(row=row_idx, column=col_idx).font = data_font

        # Make product URL column (column 10) a clickable hyperlink
        if clean_url:
            url_cell = ws.cell(row=row_idx, column=10)
            url_cell.hyperlink = clean_url
            url_cell.font = link_font

    # Auto-adjust column widths within [12, 50]
    min_width = 12
    max_width = 50
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value) if cell.value is not None else ""
            if len(val_str) > max_len:
                max_len = len(val_str)
        adjusted_width = max(min_width, min(max_width, max_len + 3))
        ws.column_dimensions[col_letter].width = adjusted_width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return _normalize_xlsx_zip(buffer.getvalue())

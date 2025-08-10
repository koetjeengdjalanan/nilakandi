"""Excel file handling utilities for the Nilakandi application.

This module provides functions for:
- Exporting pandas DataFrames to Excel files in memory
- Saving Excel files to blob storage with timestamped filenames

These utilities support the reporting and data export features of the application.
"""

import logging
import time
from io import BytesIO

import pandas as pd
from django.conf import settings
from django.core.files.storage import storages


def export_to_excel(inputs: list[tuple[str, pd.DataFrame]], decimal_count: int = 8) -> BytesIO:
    """Export pandas DataFrames to an Excel file in memory.

    This function takes a list of (sheet_name, DataFrame) pairs and writes them to an Excel file
    in a BytesIO buffer. Sheet names are sanitized to comply with Excel's limitations by replacing
    invalid characters and truncating to 31 characters. Empty DataFrames are skipped.
    Column widths are automatically adjusted for readability.

    In DEBUG mode, a copy of the Excel file is saved to disk with a timestamp in the filename.

    Args:
        inputs (list[tuple[str, pd.DataFrame]]): A list of tuples where each tuple contains a
            sheet name (str) and a pandas DataFrame to be exported to that sheet.
        decimal_count (int): Number of decimal places to display for numeric values.

    Returns:
        BytesIO: A BytesIO buffer containing the Excel file, with the position set to the beginning.

    Example:
        >>> dfs = [("Sheet1", df1), ("Sheet2", df2)]
        >>> buffer = export_to_excel(dfs)
        >>> response = HttpResponse(
        ...     buffer.getvalue(),
        ...     content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ... )
        >>> response['Content-Disposition'] = 'attachment; filename="export.xlsx"'
    """
    buffer = BytesIO()
    title_row = 0
    data_startrow = 1  # row where pandas should begin writing headers
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        used_sheet_names: set[str] = set()
        for pivot_title, df in inputs:
            if df.empty:
                continue

            raw_name = pivot_title
            clean_name = (
                raw_name.replace("/", "_")
                .replace("\\", "_")
                .replace(":", "_")
                .replace("*", "_")
                .replace("?", "_")
                .replace("[", "_")
                .replace("]", "_")[:31]
            ) or "Sheet"
            base = clean_name
            i = 1
            while clean_name in used_sheet_names:
                suffix = f"_{i}"
                clean_name = base[: 31 - len(suffix)] + suffix
                i += 1
            used_sheet_names.add(clean_name)

            # Write DataFrame starting below the title row
            df.to_excel(
                writer,
                sheet_name=clean_name,
                startrow=data_startrow,
                merge_cells=True,
                index=True,
            )

            workbook = writer.book
            ws = writer.sheets[clean_name]

            # Title
            total_cols = df.index.nlevels + len(df.columns)
            title_fmt = workbook.add_format({"bold": True, "align": "left", "valign": "vcenter", "font_size": 16})
            ws.merge_range(title_row, 0, title_row, total_cols - 1, pivot_title, title_fmt)

            # Number format (only applied to numeric columns)
            num_fmt_str = "#,##0" + ("." + "0" * decimal_count)
            num_fmt = workbook.add_format({"num_format": num_fmt_str})

            # Autosize (sampled for performance)
            index_levels = df.index.nlevels

            # Use workbook/engine autofit instead of manual loops
            try:
                # Available in XlsxWriter >= 3.1.0
                col_widths = ws.autofit()  # returns a dict {col_idx: width}
            except AttributeError:
                col_widths = {}

            # Re-apply number format to numeric data columns (without changing autofit widths)
            for ci in range(len(df.columns)):
                col_series = df.iloc[:, ci]
                if pd.api.types.is_numeric_dtype(col_series):
                    excel_col = index_levels + ci
                    width = col_widths.get(excel_col) if col_widths else 20
                    ws.set_column(excel_col, excel_col, width, num_fmt)

    buffer.seek(0)
    if settings.DEBUG:
        with open(
            f"/home/vscode/devAssets/final_report_POC2-{time.strftime('%Y%m%d-%H%M%S')}.xlsx",
            "wb",
        ) as f:
            f.write(buffer.getvalue())
    return buffer


def save_as_blob(file: BytesIO, blobs_destination: str) -> bool:
    """Save a file object to blob storage with a timestamped filename.

    This function takes a BytesIO file object and saves it to the specified blob
    storage destination with a filename that includes the current timestamp.

    Args:
        file (BytesIO): The file object to save, typically an Excel file.
        blobs_destination (str): The destination path in blob storage where the file
            should be saved.

    Returns:
        bool: True if the file was successfully saved, False otherwise.

    Raises:
        Exception: Catches and logs any exceptions that occur during the save process
            but does not re-raise them.
    """
    if settings.DEBUG:
        pass  # No-op in DEBUG mode, as files are saved to disk instead
    file.seek(0)
    try:
        store = storages["result-blobs"]
        store.save(
            f"{blobs_destination.rstrip('/')}/nilakandi-report-{time.strftime('%Y%m%d-%H%M%S')}.xlsx",
            file,
        )
        return True
    except Exception as e:
        logging.getLogger("nilakandi.tasks").error(
            f"Failed to save Excel file to {blobs_destination}: {e}",
            exc_info=True,
            stack_info=True,
            stacklevel=2,
        )
        return False

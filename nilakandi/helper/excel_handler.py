"""Excel file handling utilities for the Nilakandi application.

This module provides functions for:
- Exporting pandas DataFrames to Excel files in memory
- Transforming hierarchical DataFrames into an indented, subtotaled format with gradient row colors
- Saving Excel files to blob storage with timestamped filenames

These utilities support the reporting and data export features of the application.
"""

import logging
import time
from io import BytesIO

import pandas as pd
from django.conf import settings
from django.core.files.storage import storages


def _create_hierarchical_df(pivot_df: pd.DataFrame) -> pd.DataFrame:
    """Transform a hierarchical DataFrame into an indented, subtotaled format.

    This function is designed to work on a DataFrame that has a MultiIndex (typically from
    a pivot table). It calculates subtotals for all intermediate index levels and then
    reconstructs the DataFrame with indented rows to create a visual hierarchy.

    Args:
        pivot_df (pd.DataFrame): The input DataFrame with a MultiIndex.

    Returns:
        pd.DataFrame: A new DataFrame with a single 'Item' column for the indented
        labels and the original data columns. The original index is dropped.
    """
    if pivot_df.empty or pivot_df.index.nlevels <= 1:
        return pivot_df.reset_index()

    index_levels = pivot_df.index.names
    column_order = pivot_df.columns
    original_df_flat = pivot_df.reset_index()

    # Calculate all necessary subtotals dynamically
    subtotals = {}
    for i in range(1, len(index_levels)):
        subtotal_level_group = index_levels[:i]
        subtotals[tuple(subtotal_level_group)] = (
            original_df_flat.groupby(subtotal_level_group)[column_order].sum().reset_index()
        )
        subtotals[tuple(subtotal_level_group)] = subtotals[tuple(subtotal_level_group)].set_index(subtotal_level_group)

    # Recursive function to build the report rows
    output_rows = []

    def build_report(level=0, parent_index=()):
        current_level_name = index_levels[level]

        mask = pd.Series(True, index=pivot_df.index)
        for i, p_val in enumerate(parent_index):
            mask &= pivot_df.index.get_level_values(i) == p_val

        unique_values_at_level = pivot_df.index[mask].get_level_values(current_level_name).unique()

        for value in unique_values_at_level:
            current_index = parent_index + (value,)
            label = f"{'    ' * level}{value}"

            is_subtotal_level = level < len(index_levels) - 1

            if is_subtotal_level:
                subtotal_key = tuple(index_levels[: level + 1])
                data_series = subtotals[subtotal_key].loc[current_index]
            else:
                data_series = pivot_df.loc[current_index]

            data = data_series.reindex(column_order, fill_value=0)
            output_rows.append([label] + data.tolist())

            if is_subtotal_level:
                build_report(level + 1, current_index)

    build_report()

    final_df = pd.DataFrame(output_rows, columns=["Item"] + list(column_order))
    return final_df


def export_to_excel(inputs: list[tuple[str, pd.DataFrame]], decimal_count: int = 8) -> BytesIO:
    """Export pandas DataFrames to an Excel file in memory.

    This function writes DataFrames to an Excel file. It correctly handles single and multi-level
    column headers (with vertical merging) and NaN values. Hierarchical DataFrames are transformed
    into an indented format with subtotals and gradient row colors. Column widths are dynamically
    set with a minimum width of 20. Number formatting is applied to all numeric cells.

    Args:
        inputs (list[tuple[str, pd.DataFrame]]): List of (sheet_name, DataFrame) pairs.
        decimal_count (int): Number of decimal places for numeric values.

    Returns:
        BytesIO: A BytesIO buffer containing the Excel file.
    """
    buffer = BytesIO()
    title_row = 0
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        used_sheet_names: set[str] = set()
        for pivot_title, df in inputs:
            if df.empty:
                continue

            grand_total_row = None
            df_body = df
            is_hierarchical = all(
                [
                    df.index.nlevels > 1,
                    any(["services" in pivot_title.lower(), "marketplaces" in pivot_title.lower()]),
                ]
            )

            if is_hierarchical and len(df.index) > 0 and df.index.get_level_values(0)[-1] == "Grand Total":
                grand_total_row = df.tail(1)
                df_body = df.iloc[:-1]

            if is_hierarchical:
                processed_df = _create_hierarchical_df(df_body)
                index_to_write = False
            else:
                processed_df = df
                index_to_write = True

            if grand_total_row is not None:
                grand_total_data = [["Grand Total"] + grand_total_row.values[0].tolist()]
                grand_total_df = pd.DataFrame(grand_total_data, columns=processed_df.columns)
                processed_df = pd.concat([processed_df, grand_total_df], ignore_index=True)

            clean_name = (
                str(pivot_title)
                .replace("/", "_")
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

            workbook = writer.book
            ws = writer.sheets[clean_name] = workbook.add_worksheet(clean_name)

            header_format = workbook.add_format(
                {
                    "bold": True,
                    "text_wrap": True,
                    "valign": "vcenter",
                    "align": "center",
                    "fg_color": "#D9D9D9",
                    "border": 1,
                }
            )

            df_for_writing = processed_df.reset_index() if index_to_write else processed_df

            # --- Start of Fix: Robust Header Writing without using private attributes ---
            header_rows = df_for_writing.columns.nlevels if isinstance(df_for_writing.columns, pd.MultiIndex) else 1
            data_start_row = title_row + 1 + header_rows

            if isinstance(df_for_writing.columns, pd.MultiIndex):
                written_cells = set()  # Keep track of cells that have been handled
                for level_num in range(df_for_writing.columns.nlevels):
                    for col_num in range(len(df_for_writing.columns)):
                        if (level_num, col_num) in written_cells:
                            continue

                        label = df_for_writing.columns.get_level_values(level_num)[col_num]

                        # Calculate vertical span
                        row_span = 1
                        for i in range(level_num + 1, df_for_writing.columns.nlevels):
                            # If the label in the level below is empty, it's a vertical merge
                            if str(df_for_writing.columns.get_level_values(i)[col_num]).strip() == "":
                                row_span += 1
                            else:
                                break

                        # Calculate horizontal span
                        col_span = 1
                        for i in range(col_num + 1, len(df_for_writing.columns)):
                            match = True
                            for j in range(level_num, level_num + row_span):
                                if (
                                    df_for_writing.columns.get_level_values(j)[i]
                                    != df_for_writing.columns.get_level_values(j)[col_num]
                                ):
                                    match = False
                                    break
                            if match:
                                col_span += 1
                            else:
                                break

                        # Mark all cells in the merge range as written
                        for r_off in range(row_span):
                            for c_off in range(col_span):
                                written_cells.add((level_num + r_off, col_num + c_off))

                        if row_span > 1 or col_span > 1:
                            ws.merge_range(
                                title_row + 1 + level_num,
                                col_num,
                                title_row + level_num + row_span,
                                col_num + col_span - 1,
                                label,
                                header_format,
                            )
                        else:
                            ws.write(title_row + 1 + level_num, col_num, label, header_format)
            else:  # Single-level headers
                for col_num, value in enumerate(df_for_writing.columns.values):
                    ws.write(data_start_row - 1, col_num, str(value), header_format)
            # --- End of Fix ---

            title_fmt = workbook.add_format({"bold": True, "align": "left", "valign": "vcenter", "font_size": 16})
            ws.merge_range(title_row, 0, title_row, len(df_for_writing.columns) - 1, pivot_title, title_fmt)

            colors = ["#95B3D7", "#B8CCE4", "#DCE6F1", "#FFFFFF"]
            num_fmt_str = "#,##0" + ("." + "0" * decimal_count if decimal_count > 0 else "")

            default_fmt = workbook.add_format({"bottom": 1})
            default_num_fmt = workbook.add_format({"num_format": num_fmt_str, "bottom": 1})
            level_formats = [
                workbook.add_format({"bg_color": color, "num_format": num_fmt_str, "bottom": 1}) for color in colors
            ]
            text_formats = [workbook.add_format({"bg_color": color, "bottom": 1}) for color in colors]
            grand_total_num_fmt = workbook.add_format({"num_format": num_fmt_str, "bold": True, "top": 6})
            grand_total_text_fmt = workbook.add_format({"bold": True, "top": 6, "align": "right"})

            for row_idx, row_data in df_for_writing.iterrows():
                excel_row_num = data_start_row + row_idx
                skip_cell_num = 0

                for col_idx, (col_name, value) in enumerate(row_data.items()):
                    if skip_cell_num > 0:
                        skip_cell_num -= 1
                        continue
                    cell_value = "" if pd.isna(value) else value
                    is_numeric = pd.api.types.is_number(cell_value)

                    if is_hierarchical and col_name == "Item":
                        item_label = str(cell_value)
                        level_idx: int = min(
                            (len(item_label) - len(item_label.lstrip(" "))) // 4, len(text_formats) - 1
                        )
                        cell_format = grand_total_text_fmt if item_label == "Grand Total" else text_formats[level_idx]
                        if level_idx > 0:
                            cell_format.set_indent(level_idx)
                        ws.write(excel_row_num, col_idx, item_label.lstrip(" "), cell_format)
                    elif is_hierarchical:
                        item_label = str(row_data.get("Item", ""))
                        if is_numeric:
                            cell_format = (
                                grand_total_num_fmt
                                if item_label == "Grand Total"
                                else level_formats[
                                    min((len(item_label) - len(item_label.lstrip(" "))) // 4, len(level_formats) - 1)
                                ]
                            )
                        else:
                            cell_format = (
                                grand_total_text_fmt
                                if item_label == "Grand Total"
                                else text_formats[
                                    min((len(item_label) - len(item_label.lstrip(" "))) // 4, len(text_formats) - 1)
                                ]
                            )
                        ws.write(excel_row_num, col_idx, cell_value, cell_format)
                    else:
                        if is_numeric:
                            ws.write_number(
                                excel_row_num,
                                col_idx,
                                cell_value,
                                (default_num_fmt if row_data.iloc[0] != "Grand Total" else grand_total_num_fmt),
                            )
                        else:
                            if row_data.iloc[0] == "Grand Total":
                                skip_cell_num = df_for_writing.index.nlevels - 1 if index_to_write else 0
                                if skip_cell_num > 0:
                                    ws.merge_range(
                                        excel_row_num,
                                        col_idx,
                                        excel_row_num + skip_cell_num,
                                        col_idx,
                                        cell_value,
                                        grand_total_text_fmt,
                                    )
                                else:
                                    ws.write_string(
                                        excel_row_num,
                                        col_idx,
                                        cell_value,
                                        (default_fmt if row_data.iloc[0] != "Grand Total" else grand_total_text_fmt),
                                    )
                            else:
                                ws.write_string(
                                    excel_row_num,
                                    col_idx,
                                    cell_value,
                                    (default_fmt if row_data.iloc[0] != "Grand Total" else grand_total_text_fmt),
                                )

            df_for_width = df_for_writing
            for col_num, col_name in enumerate(df_for_width.columns):
                header_text = str(col_name)
                if isinstance(col_name, tuple):
                    header_text = " ".join(map(str, col_name))

                max_len = df_for_width[col_name].astype(str).map(len).max()
                header_len = len(header_text)
                width = max(max_len, header_len, 20) + 2
                ws.set_column(col_num, col_num, width)

            ws.freeze_panes(data_start_row, 0)

    buffer.seek(0)
    if settings.DEBUG:
        with open(f"/home/vscode/devAssets/final_report_POC2-{time.strftime('%Y%m%d-%H%M%S')}.xlsx", "wb") as f:
            f.write(buffer.getvalue())
    return buffer


def save_as_blob(file: BytesIO, blobs_destination: str) -> bool:
    """Save a file object to blob storage with a timestamped filename."""
    if settings.DEBUG:
        return True

    file.seek(0)
    try:
        store = storages["result-blobs"]
        store.save(f"{blobs_destination.rstrip('/')}/nilakandi-report-{time.strftime('%Y%m%d-%H%M%S')}.xlsx", file)
        return True
    except Exception as e:
        logging.getLogger("nilakandi.tasks").error(
            f"Failed to save Excel file to {blobs_destination}: {e}", exc_info=True
        )
        return False

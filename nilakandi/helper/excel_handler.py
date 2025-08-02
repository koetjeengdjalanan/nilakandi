import logging
import time
from io import BytesIO

import pandas as pd
import storages

from config import settings


def export_to_excel(inputs: list[tuple[str, pd.DataFrame]]) -> BytesIO:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        for sheet_name, df in inputs:
            if df.empty:
                continue
            clean_name = (
                sheet_name.replace("/", "_")
                .replace("\\", "_")
                .replace(":", "_")
                .replace("*", "_")
                .replace("?", "_")
                .replace("[", "_")
                .replace("]", "_")[:31]
            )
            df.to_excel(writer, sheet_name=clean_name, index=False, merge_cells=True)
            writer.sheets[clean_name].autofit()

    buffer.seek(0)
    if settings.DEBUG:
        with open(
            f"/home/vscode/devAssets/final_report_POC2-{time.strftime('%Y%m%d-%H%M%S')}.xlsx",
            "wb",
        ) as f:
            f.write(buffer.getvalue())
    return buffer


def save_as_blob(file: BytesIO, blobs_destination: str) -> bool:
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

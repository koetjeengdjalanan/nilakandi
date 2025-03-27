from typing import Any, Dict, List, Optional, TypeVar, Union

import pandas as pd
from pydantic import BaseModel

PandasDataFrame = TypeVar("pandas.core.frame.DataFrame")


class ApiResult(BaseModel):
    """ApiResult is a Pydantic model that represents the result of an API call.

    Attributes:
        status (int): The HTTP status code of the API response.
        headers (Dict[str, str]): The headers returned in the API response.
        meta (Dict[str, str | None]): Metadata associated with the API response.
        next_link (Optional[str]): The URL for the next set of results, if available.
        raw (List[Dict[str, Any]]): The raw data returned by the API.
        data (PandasDataFrame): A pandas DataFrame representation of the raw data.
    """

    status: int
    headers: Dict[str, str]
    meta: Optional[Dict[str, str | None]] = None
    next_link: Optional[str] = None
    raw: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
    data: PandasDataFrame = pd.DataFrame()

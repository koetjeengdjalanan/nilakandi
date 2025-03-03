def wait_retry_after(retry_state):
    try:
        response = retry_state.outcome.result()
        if response is not None and "Retry-After" in response.headers:
            return response.headers["Retry-After"]
    except Exception:
        pass
    return 20

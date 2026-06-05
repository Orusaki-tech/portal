class SatellitePipelineError(Exception):
    status_code = 500
    user_message = "An unexpected error occurred while processing satellite imagery."

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.user_message


class StacUnavailableError(SatellitePipelineError):
    status_code = 503
    user_message = "The satellite imagery catalog is currently unreachable. Please try again or select a different source."


class NoScenesFoundError(SatellitePipelineError):
    status_code = 404
    user_message = "No satellite imagery found for this area with the current filters."


class AreaTooLargeError(SatellitePipelineError):
    status_code = 400
    user_message = "This area is too large for a single request."


class ProcessingTimeoutError(SatellitePipelineError):
    status_code = 504
    user_message = "Image processing timed out. Try a smaller area or reduce the buffer."


class InvalidGeometryError(SatellitePipelineError):
    status_code = 400
    user_message = "The selected area has an invalid boundary."


class CoverageError(SatellitePipelineError):
    status_code = 404
    user_message = "Available scenes do not fully cover the target area."


class ProviderError(SatellitePipelineError):
    status_code = 502
    user_message = "The satellite provider returned an error."

class LLMError(Exception):
    """Base class for provider errors, normalized across providers."""

    retryable = False


class RateLimited(LLMError):
    retryable = True

    def __init__(self, message: str = "Provider rate limit hit", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailable(LLMError):
    """5xx / overloaded / network failures — retryable with backoff."""

    retryable = True


class CircuitOpen(ProviderUnavailable):
    """The circuit breaker is open — failing fast without calling the provider."""

    retryable = False


class ContextTooLong(LLMError):
    retryable = False


class ProviderBadRequest(LLMError):
    retryable = False


class ProviderNotConfigured(LLMError):
    retryable = False

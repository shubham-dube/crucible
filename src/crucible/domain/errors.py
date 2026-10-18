"""Domain exceptions."""


class CrucibleError(Exception):
    """Base class for all Crucible errors."""


class NetworkLoadError(CrucibleError):
    """A target agent network could not be loaded or parsed."""


class ConfigError(CrucibleError):
    """Invalid Crucible configuration or input."""


class ExecutionError(CrucibleError):
    """A scenario run could not be executed."""


class BudgetExceededError(CrucibleError):
    """The configured live-LLM spend or call budget is used up."""

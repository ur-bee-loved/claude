class OmniconvError(Exception):
    """Base class for all errors raised by the application."""


class UnknownFormatError(OmniconvError):
    """The format of a file could not be determined or is not in the table."""


class NoRouteError(OmniconvError):
    """No chain of available converters links the source and target formats."""


class ConversionError(OmniconvError):
    """A backend failed while converting a file."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr

    def __str__(self) -> str:
        base = super().__str__()
        if self.stderr:
            tail = self.stderr.strip().splitlines()[-8:]
            return base + "\n" + "\n".join("  | " + line for line in tail)
        return base


class MissingDependencyError(OmniconvError):
    """A converter was selected whose requirements turned out to be missing."""

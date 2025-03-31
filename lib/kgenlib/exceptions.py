"""Custom exceptions for the kgenlib package."""

class DeleteContent(Exception):
    """
    Raised when content should be deleted.

    This exception is used to signal that a piece of content should be deleted.
    It can be raised in situations where content is found to be invalid,
    inappropriate, or otherwise undesirable.

    Example:
        if content_is_invalid(content):
            raise DeleteContent("Content is invalid and should be deleted.")
    """
    pass
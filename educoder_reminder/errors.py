class CollectionError(Exception):
    """Safe, user-facing collection error without request credentials."""


class AuthenticationExpired(CollectionError):
    """The server explicitly reports an unauthenticated session."""


class IdentityMismatch(CollectionError):
    """The authenticated account differs from the cached identity."""

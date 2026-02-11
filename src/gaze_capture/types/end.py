class EndToken:
    """Sentinel type to signal the end of a stream."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "<EndToken>"

_END = EndToken()
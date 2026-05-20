class Counter:
    """A simple incrementing counter starting at 0."""

    def __init__(self):
        pass

    def inc(self) -> int:
        self.value += 1
        return self.value

    def get(self) -> int:
        return self.value

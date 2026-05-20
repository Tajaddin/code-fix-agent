class CartTotal:
    """Running cart total. Each call to add() accumulates the price."""

    def __init__(self):
        self.total = 0.0

    def add(self, price: float) -> float:
        new_total = self.total + price
        return new_total

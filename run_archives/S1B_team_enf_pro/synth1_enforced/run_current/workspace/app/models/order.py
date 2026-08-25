"""Order model."""


class Order:
    def __init__(self, items):
        self.items = items  # list of (name, price, quantity)
        self._discount_pct = 0

    @property
    def item_total(self):
        return sum(price * qty for _, price, qty in self.items)

    def apply_discount(self, percent):
        self._discount_pct = percent

    @property
    def total(self):
        return self.item_total * (1 - self._discount_pct / 100)

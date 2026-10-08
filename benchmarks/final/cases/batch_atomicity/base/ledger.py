class Ledger:
    def __init__(self, balances):
        self.balances = dict(balances)

    def apply_batch(self, changes):
        for account, delta in changes:
            if account not in self.balances:
                raise KeyError(account)
            self.balances[account] += delta
            if self.balances[account] < 0:
                raise ValueError("overdraft")
        return dict(self.balances)

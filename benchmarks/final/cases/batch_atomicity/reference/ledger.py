class Ledger:
    def __init__(self, balances):
        self.balances = dict(balances)

    def apply_batch(self, changes):
        candidate = dict(self.balances)
        for account, delta in changes:
            if account not in candidate:
                raise KeyError(account)
            candidate[account] += delta
            if candidate[account] < 0:
                raise ValueError("overdraft")
        self.balances = candidate
        return dict(self.balances)

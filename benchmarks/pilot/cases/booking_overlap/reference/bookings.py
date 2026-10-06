class Calendar:
    def __init__(self):
        self.bookings = []

    def book(self, start, end):
        if start >= end:
            raise ValueError("empty interval")
        for existing_start, existing_end in self.bookings:
            if start < existing_end and existing_start < end:
                return False
        self.bookings.append((start, end))
        return True

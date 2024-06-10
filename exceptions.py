class RatingException(Exception):
    """Exception raised for errors in the Rating System.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

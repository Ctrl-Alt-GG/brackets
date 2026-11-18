import math

# How far one result can move a rating.
K = 32
# The rating difference at which the stronger side is expected to win ten times as often.
D = 400


def expected_result(rating: float, opponent_rating: float) -> float:
    """The result a side is expected to get, from 0 for a loss to 1 for a win."""
    return 1.0 / (1.0 + math.pow(10.0, (opponent_rating - rating) / D))

`tournament.json` pins the API responses for a group stage followed by knockout and Swiss
stages, including results, draft pairings, future slots, empty stages and teams without
players. It covers Details, stages, teams, players, standings, rankings and the tournament
listing. The fixture is built by [orm_api_test.py](../../api/orm_api_test.py).

Database identifiers and creation timestamps are normalized because they depend on the test
run. Decimal scale is normalized (for example, `3.0` and `3` compare equally), and Swiss
pairings use a fixed random seed. Collection ordering, scheduled times, nulls, scores and
statistical values remain exact.
Foreign key relationships are checked separately by the tournament flow tests.

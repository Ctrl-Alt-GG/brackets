`tournament.json` pins the API responses for a group stage followed by knockout and Swiss
stages, including results, draft pairings, future slots, empty stages and teams without
players. It covers Details, stages, teams, players, standings, rankings and the tournament
listing. The fixture is built by [orm_api_test.py](../../api/orm_api_test.py).

Entity identifiers are replaced with stable labels; every foreign key and standings key
retains its relationship to those labels. Creation timestamps are normalized because they
depend on the run. Decimal strings ignore trailing zeros while retaining their JSON type,
and Swiss pairings use a fixed random seed. Collection ordering, scheduled times, nulls,
scores and statistical values remain exact.

from bracket.models.db.util import RoundWithMatches, StageItemWithRounds


def get_draft_round(
    stage_item: StageItemWithRounds,
) -> RoundWithMatches | None:
    return next(
        (round_ for round_ in sorted(stage_item.rounds, key=lambda r: r.id) if round_.is_draft),
        None,
    )

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.ranking import Ranking, RankingBody, RankingCreateBody
from bracket.utils.id_types import RankingId, StageItemId, TournamentId


async def get_all_rankings_in_tournament(
    session: AsyncSession, tournament_id: TournamentId
) -> list[Ranking]:
    entities = await session.scalars(
        select(orm.Ranking)
        .where(orm.Ranking.tournament_id == tournament_id)
        .order_by(orm.Ranking.position, orm.Ranking.id)
        .execution_options(populate_existing=True)
    )
    return [Ranking.model_validate(entity) for entity in entities]


async def get_default_rankings_in_tournament(
    session: AsyncSession, tournament_id: TournamentId
) -> Ranking:
    entity = await session.scalar(
        select(orm.Ranking)
        .where(orm.Ranking.tournament_id == tournament_id)
        .order_by(orm.Ranking.position, orm.Ranking.id)
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if entity is None:
        raise ValueError("No default ranking found")
    return Ranking.model_validate(entity)


async def get_ranking_for_stage_item(
    session: AsyncSession, tournament_id: TournamentId, stage_item_id: StageItemId
) -> Ranking | None:
    entity = await session.scalar(
        select(orm.Ranking)
        .join(orm.StageItem, orm.StageItem.ranking_id == orm.Ranking.id)
        .where(orm.Ranking.tournament_id == tournament_id, orm.StageItem.id == stage_item_id)
        .execution_options(populate_existing=True)
    )
    return Ranking.model_validate(entity) if entity is not None else None


async def sql_update_ranking(
    session: AsyncSession,
    tournament_id: TournamentId,
    ranking_id: RankingId,
    ranking_body: RankingBody,
) -> None:
    """Change the points rule of a ranking, and move it to its new position."""
    entity = await session.scalar(
        select(orm.Ranking).where(
            orm.Ranking.tournament_id == tournament_id, orm.Ranking.id == ranking_id
        )
    )
    if entity is not None:
        entity.win_points = ranking_body.win_points
        entity.draw_points = ranking_body.draw_points
        entity.loss_points = ranking_body.loss_points
        entity.add_score_points = ranking_body.add_score_points
        await session.flush()

    order = [
        ranking.id
        for ranking in await get_all_rankings_in_tournament(session, tournament_id)
        if ranking.id != ranking_id
    ]
    order.insert(min(ranking_body.position, len(order)), ranking_id)
    await sql_set_ranking_order(session, tournament_id, order)


async def sql_set_ranking_order(
    session: AsyncSession, tournament_id: TournamentId, ranking_ids: list[RankingId]
) -> None:
    """Number the rankings 0, 1, 2, ... in this order, so that no two share a position."""
    if not ranking_ids:
        return
    positions = {ranking_id: position for position, ranking_id in enumerate(ranking_ids)}
    entities = await session.scalars(
        select(orm.Ranking).where(
            orm.Ranking.tournament_id == tournament_id, orm.Ranking.id.in_(ranking_ids)
        )
    )
    for entity in entities:
        entity.position = positions[RankingId(entity.id)]
    await session.flush()


async def sql_delete_ranking(
    session: AsyncSession, tournament_id: TournamentId, ranking_id: RankingId
) -> None:
    """Delete a ranking. The ones after it move up, so the positions stay 0, 1, 2, ..."""
    await session.execute(
        delete(orm.Ranking).where(
            orm.Ranking.id == ranking_id, orm.Ranking.tournament_id == tournament_id
        )
    )
    await sql_set_ranking_order(
        session,
        tournament_id,
        [ranking.id for ranking in await get_all_rankings_in_tournament(session, tournament_id)],
    )


async def sql_create_ranking(
    session: AsyncSession,
    tournament_id: TournamentId,
    ranking_body: RankingCreateBody,
    position: int,
) -> None:
    session.add(
        orm.Ranking(
            tournament_id=tournament_id,
            win_points=ranking_body.win_points,
            draw_points=ranking_body.draw_points,
            loss_points=ranking_body.loss_points,
            add_score_points=ranking_body.add_score_points,
            position=position,
        )
    )
    await session.flush()

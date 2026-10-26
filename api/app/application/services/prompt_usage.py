# api/app/application/services/prompt_usage.py

"""Counts the workflows whose current version maps a prompt into a step."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def count_workflows_using_prompt(session: AsyncSession, prompt_id: UUID) -> int:
    """Number of workflows whose latest version has an input mapping with this promptId."""
    result = await session.execute(
        text(
            """
            SELECT count(*)
            FROM workflows w
            JOIN LATERAL (
                SELECT wv.steps
                FROM workflow_versions wv
                WHERE wv.workflow_id = w.id
                ORDER BY wv.created_at DESC
                LIMIT 1
            ) cur ON TRUE
            WHERE cur.steps::text LIKE :pattern
            """
        ),
        {"pattern": f'%"promptId": "{UUID(str(prompt_id))}"%'},
    )
    return int(result.scalar_one())


async def count_workflows_using_marketplace_prompt(session: AsyncSession, slug: str) -> int:
    """Number of workflows, in any org, whose latest version maps a copy of this marketplace prompt."""
    result = await session.execute(
        text(
            """
            SELECT count(*)
            FROM workflows w
            JOIN LATERAL (
                SELECT wv.steps
                FROM workflow_versions wv
                WHERE wv.workflow_id = w.id
                ORDER BY wv.created_at DESC
                LIMIT 1
            ) cur ON TRUE
            WHERE EXISTS (
                SELECT 1
                FROM prompts p
                WHERE (p.slug = :slug OR p.slug LIKE :copy_pattern)
                  AND cur.steps::text LIKE '%"promptId": "' || p.id::text || '"%'
            )
            """
        ),
        {"slug": slug, "copy_pattern": f"{slug}-copy-%"},
    )
    return int(result.scalar_one())

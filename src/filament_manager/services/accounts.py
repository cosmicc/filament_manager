"""Single-account initialization and invariant enforcement."""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.security import PASSWORD_HASHER, normalize_username

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"  # noqa: S105 - operator explicitly accepted this forced-change default.


async def ensure_single_administrator(session: AsyncSession) -> bool:
    """Create the first forced-change administrator and reject ambiguous account state.

    The public default is an explicitly accepted deployment tradeoff. Password
    replacement remains mandatory before any other authenticated route is usable.
    """

    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('filament-manager-account'))"))
    count = int(await session.scalar(select(func.count(User.id))) or 0)
    if count > 1:
        raise RuntimeError(
            "Filament Manager supports exactly one account; remove extra accounts "
            "with an older release before upgrading"
        )
    if count == 1:
        user = await session.scalar(select(User).with_for_update())
        assert user is not None
        changed = False
        if user.role != UserRole.ADMINISTRATOR:
            user.role = UserRole.ADMINISTRATOR
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            user.record_version += 1
            await session.commit()
        else:
            await session.rollback()
        return False
    session.add(
        User(
            username=DEFAULT_USERNAME,
            normalized_username=normalize_username(DEFAULT_USERNAME),
            display_name="Administrator",
            # The operator explicitly chose this discoverable first-run credential.
            # Bypass only the normal creation-length check here; the mandatory
            # first-login replacement still uses the full password policy.
            password_hash=PASSWORD_HASHER.hash(DEFAULT_PASSWORD),
            role=UserRole.ADMINISTRATOR,
            is_active=True,
            must_change_password=True,
        )
    )
    await session.commit()
    return True

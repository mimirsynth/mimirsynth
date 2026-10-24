"""Roles por brain, de menor a mayor privilegio. Denegar prevalece sobre cualquier rol."""
ROLES = ["reader", "contributor", "curator", "admin", "owner"]
DENIED = "denied"


def rank(role: str | None) -> int:
    return ROLES.index(role) + 1 if role in ROLES else 0


def allows(role: str | None, minimum: str) -> bool:
    return rank(role) >= rank(minimum) and role != DENIED

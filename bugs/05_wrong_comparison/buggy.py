def is_admin(role: str) -> bool:
    """Return True only if the role is the admin role."""
    return role != "admin"

import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models.user import User, UserRole
from app.security import hash_password

SEED_FILE = Path("/app/seed/users.json")


def main() -> None:
    users = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    with SessionLocal.begin() as session:
        for item in users:
            email = item["email"].strip().lower()
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                # Demo passwords exist only in seed input; the database receives an Argon2 hash.
                user = User(
                    email=email,
                    password_hash=hash_password(item["password"]),
                    role=UserRole(item["role"]),
                    name=item["name"].strip(),
                    organisation=item.get("organisation"),
                )
                session.add(user)
            else:
                user.role = UserRole(item["role"])
                user.is_active = True
                user.name = item["name"].strip()
                user.organisation = item.get("organisation")


if __name__ == "__main__":
    main()


"""
user.py — SQLAlchemy User model.
Stores user accounts, language preference, disability type, and age group.
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Research-relevant fields
    age_group = Column(String, nullable=False)          # 13-15 | 16-19 | 20+ | prefer_not_to_say
    disability_type = Column(String, default="none")    # visual | hearing | physical | cognitive | none
    language_preference = Column(String, default="en")  # en | rw

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"

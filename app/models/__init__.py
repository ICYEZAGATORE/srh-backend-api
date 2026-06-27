"""SQLAlchemy ORM models.

Importing this package registers every model on the shared ``Base.metadata``
so that Alembic autogeneration and ``Base.metadata.create_all`` see all tables.
"""

from app.models.session import Session
from app.models.query import Query
from app.models.assessment import Assessment
from app.models.knowledge import KnowledgeEntry

__all__ = ["Session", "Query", "Assessment", "KnowledgeEntry"]

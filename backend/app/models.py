"""Imports every model module so `Base.metadata` knows all tables (Alembic, tests)."""

from app.accounts import models as accounts  # noqa: F401
from app.availability import models as availability  # noqa: F401
from app.bookings import models as bookings  # noqa: F401
from app.catalog import models as catalog  # noqa: F401
from app.jobs import models as jobs  # noqa: F401
from app.listings import models as listings  # noqa: F401
from app.notifications import models as notifications  # noqa: F401

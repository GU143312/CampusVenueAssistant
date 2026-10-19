from datetime import date, datetime

import pytest

from domain.query_service import QueryService, TZ
from scripts.seed import seed


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "demo.sqlite"
    seed(path, date(2026,10,20))
    return path


@pytest.fixture
def service(db):
    return QueryService(db, datetime(2026,10,20,9,tzinfo=TZ))


@pytest.fixture
def request_data():
    return {"date_local":"2026-10-23", "earliest_start":"15:30", "latest_end":"19:30",
        "duration_minutes":120, "participants":6, "required_equipment":["projector"],
        "preferred_building":"C", "limit":20}

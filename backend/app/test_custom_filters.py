from datetime import date
from pathlib import Path
from uuid import uuid4

from app.models import (
    CustomFieldFilterRequest,
    ProductGroup,
    Project,
    ProjectStatus,
    GroupStatus,
)
from app.storage import DataStore, LocalRepository


def make_repo(tmp_path: Path) -> LocalRepository:
    repo = LocalRepository(tmp_path)
    group_a = ProductGroup(
        id=uuid4(),
        name="Group A",
        status=GroupStatus.ACTIVE,
        brands=["Alpha"],
        extra_fields={"color": "red", "volume": 10, "featured": True},
    )
    group_b = ProductGroup(
        id=uuid4(),
        name="Group B",
        status=GroupStatus.ACTIVE,
        brands=["Beta"],
        extra_fields={"color": "blue", "volume": 12, "featured": False},
    )
    group_c = ProductGroup(
        id=uuid4(),
        name="Group C",
        status=GroupStatus.ARCHIVED,
        brands=["Alpha"],
        extra_fields={"color": "red", "volume": 15},
    )

    repo.store = DataStore(
        product_groups=[group_a, group_b, group_c],
        projects=[
            Project(
                id=uuid4(),
                name="Project 1",
                group_id=group_a.id,
                brand="Alpha",
                market="RU",
                status=ProjectStatus.IN_PROGRESS,
                custom_fields={"color": "red", "size": 10, "approved": True},
            ),
            Project(
                id=uuid4(),
                name="Project 2",
                group_id=group_b.id,
                brand="Beta",
                market="EU",
                status=ProjectStatus.CLOSED,
                custom_fields={"color": "blue", "size": 12, "approved": False},
            ),
            Project(
                id=uuid4(),
                name="Project 3",
                group_id=group_c.id,
                brand="Alpha",
                market="RU",
                status=ProjectStatus.IN_PROGRESS,
                planned_launch=date(2024, 12, 31),
                custom_fields={"color": "red", "size": 15},
            ),
        ],
    )
    repo.save()
    return repo


def test_project_custom_field_filters(tmp_path: Path):
    repo = make_repo(tmp_path / "store.json")

    # Select filter (color) AND numeric range (size)
    filters = [
        CustomFieldFilterRequest(field_id="color", type="select", values=["red"]),
        CustomFieldFilterRequest(field_id="size", type="number", value_from=12, value_to=20),
    ]
    results = repo.list_projects(filters=filters)
    assert len(results) == 1
    assert results[0].custom_fields["size"] == 15

    # Boolean filter
    bool_filter = [CustomFieldFilterRequest(field_id="approved", type="checkbox", bool=True)]
    approved = repo.list_projects(filters=bool_filter)
    assert [p.name for p in approved] == ["Project 1"]


def test_group_custom_field_filters(tmp_path: Path):
    repo = make_repo(tmp_path / "store.json")

    filters = [
        CustomFieldFilterRequest(field_id="color", type="select", values=["red"]),
        CustomFieldFilterRequest(field_id="volume", type="number", value_from=11, value_to=16),
    ]
    results = repo.list_groups(filters=filters)
    assert len(results) == 1
    assert results[0].name == "Group C"

    # Boolean tri-state
    featured = repo.list_groups(filters=[CustomFieldFilterRequest(field_id="featured", type="checkbox", bool=True)])
    assert [g.name for g in featured] == ["Group A"]


def test_filter_metadata_counts_only_reusable(tmp_path: Path):
    repo = make_repo(tmp_path / "store.json")

    project_meta = repo.list_project_filter_meta()
    group_meta = repo.list_group_filter_meta()

    project_fields = {m.field_id for m in project_meta}
    group_fields = {m.field_id for m in group_meta}

    # Fields used in more than one entity are included; one-off fields omitted
    assert "color" in project_fields
    assert "size" in project_fields
    assert "approved" in project_fields
    assert "note" not in project_fields

    assert "color" in group_fields
    assert "volume" in group_fields
    assert "featured" in group_fields

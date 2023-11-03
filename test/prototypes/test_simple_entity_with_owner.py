# test_simple_entity_with_owner.py

from __future__ import unicode_literals

from draftsman.entity import SimpleEntityWithOwner, simple_entities_with_owner
from draftsman.error import InvalidEntityError
from draftsman.warning import UnknownEntityWarning, UnknownKeywordWarning

import pytest


class TestSimpleEntityWithOwner:
    def test_contstructor_init(self):
        entity = SimpleEntityWithOwner(variation=13)
        assert entity.name == simple_entities_with_owner[0]
        assert entity.variation == 13

        with pytest.warns(UnknownKeywordWarning):
            SimpleEntityWithOwner(unused_keyword="whatever")

        with pytest.warns(UnknownEntityWarning):
            SimpleEntityWithOwner("this is not correct")

    def test_to_dict(self):
        entity = SimpleEntityWithOwner("simple-entity-with-owner")
        assert entity.variation == 1
        assert entity.to_dict(exclude_defaults=False) == {
            "name": "simple-entity-with-owner",
            "position": {"x": 0.5, "y": 0.5},
            "variation": 1, # Default
            "tags": {} # Default
        }

        entity.variation = None
        assert entity.variation == None
        assert entity.to_dict(exclude_defaults=False) == {
            "name": "simple-entity-with-owner",
            "position": {"x": 0.5, "y": 0.5},
            "tags": {} # Default
        }

    def test_power_and_circuit_flags(self):
        for name in simple_entities_with_owner:
            entity = SimpleEntityWithOwner(name)
            assert entity.power_connectable == False
            assert entity.dual_power_connectable == False
            assert entity.circuit_connectable == False
            assert entity.dual_circuit_connectable == False

    def test_mergable_with(self):
        entity1 = SimpleEntityWithOwner("simple-entity-with-owner")
        entity2 = SimpleEntityWithOwner(
            "simple-entity-with-owner", tags={"some": "stuff"}
        )

        assert entity1.mergable_with(entity1)

        assert entity1.mergable_with(entity2)
        assert entity2.mergable_with(entity1)

        entity2.tile_position = (1, 1)
        assert not entity1.mergable_with(entity2)

    def test_merge(self):
        entity1 = SimpleEntityWithOwner("simple-entity-with-owner")
        entity2 = SimpleEntityWithOwner(
            "simple-entity-with-owner", tags={"some": "stuff"}
        )

        entity1.merge(entity2)
        del entity2

        assert entity1.tags == {"some": "stuff"}

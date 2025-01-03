# test_electric_pole.py

from draftsman.classes.blueprint import Blueprint
from draftsman.classes.group import Group
from draftsman.entity import ElectricPole, electric_poles, Container
from draftsman.error import DataFormatError
from draftsman.warning import UnknownEntityWarning, UnknownKeywordWarning

from collections.abc import Hashable
import sys
import pytest


class TestElectricPole:
    def test_constructor_init(self):
        electric_pole = ElectricPole("substation", position=[1, 1], neighbours=[1, 2])

        # Warnings
        with pytest.warns(UnknownKeywordWarning):
            ElectricPole(
                "small-electric-pole", unused_keyword=10
            ).validate().reissue_all()
        with pytest.warns(UnknownEntityWarning):
            ElectricPole("this is not an electric pole").validate().reissue_all()

    def test_mergable_with(self):
        group = Group()
        group.entities.append("small-electric-pole")
        group.entities.append("small-electric-pole", tile_position=(5, 0))
        group.add_power_connection(0, 1)
        group.add_circuit_connection("red", 0, 1)
        group.add_circuit_connection("green", 0, 1)

        blueprint = Blueprint()
        blueprint.entities.append(group)
        group.position = (5, 0)

        group1_entity = blueprint.entities[(0, 1)]
        group2_entity = group.entities[0]

        assert group1_entity.mergable_with(group2_entity)
        assert group2_entity.mergable_with(group1_entity)

        group.position = (5, 5)
        assert not group1_entity.mergable_with(group2_entity)

        group2_entity = ElectricPole("medium-electric-pole", tile_position=(5, 0))
        assert not group1_entity.mergable_with(group2_entity)

    def test_merge(self):
        group = Group()
        group.entities.append("small-electric-pole")
        group.entities.append("small-electric-pole", tile_position=(2, 0))
        group.add_power_connection(0, 1)
        group.add_circuit_connection("red", 0, 1)
        group.add_circuit_connection("green", 0, 1)

        blueprint = Blueprint()
        blueprint.entities.append(group)
        group.position = (2, 0)
        blueprint.entities.append(group, merge=True)
        blueprint.add_power_connection((0, 0), (1, 0))

        assert len(blueprint.entities) == 2
        assert len(blueprint.entities[0].entities) == 2
        assert len(blueprint.entities[1].entities) == 1
        assert blueprint.to_dict()["blueprint"]["entities"] == [
            {
                "entity_number": 1,
                "name": "small-electric-pole",
                "position": {"x": 0.5, "y": 0.5},
            },
            {
                "entity_number": 2,
                "name": "small-electric-pole",
                "position": {"x": 2.5, "y": 0.5},
            },
            {
                "entity_number": 3,
                "name": "small-electric-pole",
                "position": {"x": 4.5, "y": 0.5},
            },
        ]
        assert blueprint.to_dict()["blueprint"]["wires"] == [
            [1, 5, 3, 5],
            [1, 5, 2, 5],
            [1, 1, 2, 1],
            [1, 2, 2, 2],
            [2, 5, 3, 5],
            [2, 1, 3, 1],
            [2, 2, 3, 2],
        ]

        # Exactly on top of one another
        group = Group()
        group.entities.append("small-electric-pole")
        group.entities.append("small-electric-pole", tile_position=(2, 0))
        group.add_power_connection(0, 1)
        group.add_circuit_connection("red", 0, 1)

        blueprint = Blueprint()
        blueprint.entities.append(group)
        blueprint.entities.append(group, merge=True)

        assert len(blueprint.entities) == 2
        assert len(blueprint.entities[0].entities) == 2
        assert len(blueprint.entities[1].entities) == 0
        assert blueprint.to_dict()["blueprint"]["entities"] == [
            {
                "entity_number": 1,
                "name": "small-electric-pole",
                "position": {"x": 0.5, "y": 0.5},
            },
            {
                "entity_number": 2,
                "name": "small-electric-pole",
                "position": {"x": 2.5, "y": 0.5},
            },
        ]
        assert blueprint.to_dict()["blueprint"]["wires"] == [[1, 5, 2, 5], [1, 1, 2, 1]]

        # Test wire connections
        group = Group()
        group.entities.append("small-electric-pole")
        group.entities.append("small-electric-pole", tile_position=(2, 0))
        group.add_circuit_connection("red", 0, 1)

        blueprint = Blueprint()
        blueprint.entities.append("small-electric-pole")
        blueprint.entities.append(group, merge=True)

        assert len(blueprint.entities) == 2
        assert len(blueprint.entities[1].entities) == 1
        assert blueprint.to_dict()["blueprint"]["entities"] == [
            {
                "entity_number": 1,
                "name": "small-electric-pole",
                "position": {"x": 0.5, "y": 0.5},
            },
            {
                "entity_number": 2,
                "name": "small-electric-pole",
                "position": {"x": 2.5, "y": 0.5},
            },
        ]
        assert blueprint.to_dict()["blueprint"]["wires"] == [[1, 1, 2, 1]]

    def test_eq(self):
        pole1 = ElectricPole("small-electric-pole")
        pole2 = ElectricPole("small-electric-pole")

        assert pole1 == pole2

        pole1.tags = {"some": "stuff"}

        assert pole1 != pole2

        container = Container()

        assert pole1 != container
        assert pole2 != container

        # hashable
        assert isinstance(pole1, Hashable)

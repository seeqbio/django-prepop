"""Utilities for batch loading/unloading of fixtures, see design.md"""
from django.db import transaction
from django.utils.module_loading import import_string

from .core import UnresolvedFixtureError
from .core import AbstractStorageFixture

import logging
logger = logging.getLogger('portal')


def unpack_fixture_modules(module_paths):
    batch = []
    for module_path in module_paths:
        fixtures = import_string(module_path + '.FIXTURES')
        assert all(isinstance(f, AbstractStorageFixture) for f in fixtures)
        batch += fixtures

    return batch


@transaction.atomic()
def load_fixtures(fixtures):
    """Loads a sequence of fixtures in a transaction. Returns an integer retcode."""
    assert all(isinstance(f, AbstractStorageFixture) for f in fixtures)

    for fixture in fixtures:
        try:
            fixture.load()
        except UnresolvedFixtureError as e:
            logger.info('Failed to resolve %s due to missing dependency: %s' % (fixture, e.args[0]))
            return 1

    return 0


@transaction.atomic()
def unload_fixtures(fixtures):
    """Unloads a sequence of fixtures in a transaction. Returns an integer retcode."""
    assert all(isinstance(f, AbstractStorageFixture) for f in fixtures)

    # Important: trigger data resolution of all fixtures before starting to
    # unload. Without this we might run into unresolvable fixtures half way
    # through because we just unloaded a dependency.
    for fixture in fixtures:
        fixture.resolved_data

    for fixture in fixtures:
        fixture.unload()

    return 0

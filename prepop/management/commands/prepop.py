from django.core.management.base import BaseCommand, CommandError

from prepop.batch import load_fixtures, unload_fixtures
from prepop.batch import unpack_fixture_modules

import logging
logger = logging.getLogger('prepop')


class Command(BaseCommand):
    help = """
        Load or unload fixtures from a specified fixture module. Example:

            $ manage.py prepop load project.fixtures.X project.fixtures.dev.Y

        A fixture module is any python module that declares a `FIXTURES`
        attribute at its top level consisting of fixture objects, as defined by `project.fixtures`.

        All fixture objects are loaded/unloaded in one transaction, in the specified order.
    """
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('action', type=str, choices=['load', 'unload'])
        parser.add_argument('fixtures', nargs='+', type=str, help="""
            Absolute import path of Python modules to be loaded.
        """)

    def handle(self, *args, **kwargs):
        action = kwargs['action']
        func = {'load': load_fixtures, 'unload': unload_fixtures}[action]
        fixtures = unpack_fixture_modules(kwargs['fixtures'])
        retcode = func(fixtures)
        if retcode:
            raise CommandError('fixture %s failed!' % action)

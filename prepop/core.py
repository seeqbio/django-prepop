"""Core implementation of Fixture API, see design.md"""
from abc import ABC
from abc import abstractmethod

from .walk import walks_on_trees, TraversalTerminator

import logging
logger = logging.getLogger('portal')


class UnresolvedFixtureError(Exception):
    """Raised when there are unexpected UnresolvableFixture instances."""
    pass


class FixtureProgrammingError(Exception):
    """Raised when common misuses of API are detected, for DX improvement."""
    pass


class UnresolvableFixture:
    """A wrapper for fixtures that fail to resolve during data resolution."""
    def __init__(self, fixture):
        self.fixture = fixture


class AbstractStorageFixture(ABC):
    """This class is the *de facto* specification of our fixture API. For this
    reason, it remains agnostic about what a fixture exactly is and how it's stored.

    External API, for use by fixture clients:

        * load()            puts the fixture in storage, if not exists()
        * unload()          removes (what seems like) the fixture from storage, if exists()

    Internal API, for use by fixture API and fixture classes.

        * exists()          abstract
        * create()          abstract
        * delete()          abstract
        * resolvable        boolean, True if resolve attempted and all
                            dependencies are resolvable.
        * resolved_data     contents of self.data after data resolution
                            it might contain instances of UnresolvableFixture.

    Fixture clients are discouraged from relying on the internal API.
    """

    def __init__(self, **data):
        self.data = data

    def __str__(self):
        return '%s(%s)' % (self.__class__.__name__, ', '.join('%s=%s' % (k, v) for k, v in self.data.items()))

    def load(self):
        """Loads this fixture into storage unless it already exists. Raises
        UnresolvedFixtureError if the fixture's data cannot be resolved.
        """
        self.attempt_data_resolution()

        if self.exists():
            logger.debug('Fixture already exists, nothing to load: %s' % self)
            return

        if not self.resolvable:
            raise UnresolvedFixtureError(self._unresolvable_dep)

        logger.debug('Creating fixture: %s' % self)
        self.create()
        logger.debug('Loaded fixture: %s' % self)

    def unload(self):
        self.attempt_data_resolution()

        if not self.exists():
            logger.debug('Fixture does not exist, nothing to unload: %s' % self)
            return

        self.delete()
        logger.debug('Unloaded fixture: %s' % self)

    def resolve_self(self):
        """A fixture class must implement this if and only if it wants its
        fixture instances to be referable in other fixtures' data."""
        return UnresolvableFixture(self)

    @property
    def resolved_data(self):
        self.attempt_data_resolution()
        return self._resolved_data

    @property
    def resolvable(self):
        if not hasattr(self, '_unresolvable_dep'):
            raise FixtureProgrammingError(
                'Trying to check if %s is resolvable before '
                'data resolution is attempted.' % self
            )

        return self._unresolvable_dep is None

    # ========= Private helpers ========
    def _resolve_data(self):
        """Data resolution algorithm, sets instance attributes and returns
        nothing. We typically need to resolve data only once but the
        timing depends on the context. This function is *not* responsible for

            * resolving data at the right time
            * avoiding a re-resolution if it has already happened

        Instead of calling this function directly, use either of the following:

            * (happy path) directly access the resolved_data property.
            * (delicate path, not for clients) call attempt_data_resolution().
        """
        self._resolved_data = self._resolve_fixtures_in_data(self.data)
        self._unresolvable_dep = self.find_unresolvable_dependency(self._resolved_data)
        if self._unresolvable_dep:
            # Field resolvers expect properly resolved values, don't bother
            # with them if we have unresolvable dependencies
            return

        for field, resolver in self._get_field_resolvers().items():
            if field in self._resolved_data:
                self._resolved_data[field] = resolver(self._resolved_data[field])

    @staticmethod
    @walks_on_trees
    def _resolve_fixtures_in_data(value):
        # - not a module function to keep scope clean.
        # - @staticmethod for signature to comply with @walks_on_trees.
        if isinstance(value, AbstractStorageFixture):
            resolved = value.resolve_self()

            if isinstance(resolved, AbstractStorageFixture):
                raise FixtureProgrammingError(
                    'Fixture %s resolved to another fixture %s' % (value, resolved)
                )
            return TraversalTerminator(resolved)

    def _get_field_resolvers(self):
        # unpack field resolvers, see @register_field_resolver
        resolvers = {}
        for attr in dir(self):
            value = getattr(self, attr)
            field_name = getattr(value, '_registered_field_resolver_for', None)
            if callable(value) and field_name is not None:
                resolvers[field_name] = value

        return resolvers

    # ========= Helpers for internal use ========
    @classmethod
    def find_unresolvable_dependency(cls, resolved_data):
        # returns the first unresolvable fixture, or None.
        @walks_on_trees
        def raise_if_unresolved(value):
            if isinstance(value, UnresolvableFixture):
                raise UnresolvedFixtureError(value.fixture)

            if isinstance(value, AbstractStorageFixture):
                raise FixtureProgrammingError(
                    'Expected provided data to be already '
                    'resolved, found unexpected fixture instance %s' % value
                )

        try:
            raise_if_unresolved(resolved_data)
            return None
        except UnresolvedFixtureError as e:
            return e.args[0]

    def attempt_data_resolution(self):
        """Ensures that data resolution has already been attempted. Nuances:

            * It does *not* re-resolve if resolution has already happened.
            * It's ok if there remain unresolvable dependencies.

        """
        if not hasattr(self, '_resolved_data'):
            self._resolve_data()

    # ========= Abstract Methods, Subclass API ===========
    @abstractmethod
    def exists(self):
        """Returns a boolean and does *not* assume that this fixture is resolvable.

        Example scenario when your fixture maybe unresolvable and you have to
        handle it in your exists():

            * Job -> Patient is a nullable FK.
            * A Patient and its Job are both loaded via fixtures.
            * The Patient is removed manually.
            * The Job now has a null FK to Patient.
            * The Job fixture is unresolvable but it can still be identified in db.
            * Your exists() implementation is the last chance to not crash.
        """
        pass

    @abstractmethod
    def create(self):
        """Creates this fixture, wrapped by load(). This method can assume that
        this fixture is resolvable."""
        pass

    @abstractmethod
    def delete(self):
        """Deletes this fixture, wrapped by unload(). This method can *not*
        assume that this fixture is resolvable.

        See exists() for an example scenario when .delete() of an unresolvable
        fixture maybe called.
        """
        pass


def register_field_resolver(field_name):
    """Decorator for registering custom field resolvers in any fixture class."""
    def decorator(fn):
        fn._registered_field_resolver_for = field_name
        return fn

    return decorator


class ModelFixture(AbstractStorageFixture):
    model = None
    identifying_fields = []

    def __str__(self):
        return '{cls}({fields})'.format(
            cls=self.__class__.__name__,
            fields=', '.join('%s=%s' % (k, self.data[k]) for k in self.identifying_fields)
        )

    def existing_object(self):
        """Returns the existing instance of this model in db. Returns None if
        and only if this fixture does not exist in db.

        Important: we cannot insist on self.resolvable when working with
        model fixtures. A common scenario to support is when *some* of a
        fixture's data is not resolvable but its identifying fields are
        resolvable. In such cases, if we insist on self.resolvable, we "won't
        see" that the fixture exists in db."""
        model_kw = {k: self.resolved_data[k] for k in self.identifying_fields}

        if self.find_unresolvable_dependency(model_kw):
            return None

        try:
            return self.model.objects.get(**model_kw)
        except self.model.DoesNotExist:
            return None

    def exists(self):
        return self.existing_object() is not None

    def create(self):
        model_kw = self.resolved_data.copy()

        # collect m2m fields and remove them from model_kw, to be set later
        m2ms = {}
        for key in list(model_kw.keys()):
            if self.model._meta.get_field(key).many_to_many:
                m2ms[key] = model_kw.pop(key)

        obj = self.model(**model_kw)

        if m2ms:
            # m2ms need an id, save and add them before we can even validate.
            obj.save()
            for key, value in m2ms.items():
                # set() automatically saves to db
                getattr(obj, key).set(value)
            obj.full_clean()
        else:
            obj.full_clean()
            obj.save()

    def delete(self):
        self.existing_object().delete()

    def resolve_self(self):
        return self.existing_object() or UnresolvableFixture(self)

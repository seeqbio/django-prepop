# Fixture API

Storage fixtures are a way to put data in storage:

* reproducibly,
* programmatically,
* at will,
* with minimal assumptions about current state of storage.

The point of fixtures is to mimic external input (e.g. user interaction,
pipeline output) during development, automated testing, prototypes, QA,
demo sites, and deployments.

## Quick Start

To create a fixture you simply instantiate a fixture class with some data.
For example, you may have a fixture class called `UserFixture` that allows you
to programmatically create users as if a user was created through normal
operation.

```py
Norman = UserFixture(
    email='norman@example.com',
    first_name='Norman',
    last_name='Genes'
)
```

Now you can use it like this:

```py
Norman.exists()
Norman.load()
Norman.unload()
```

## Fixture Data

The keyword arguments you provide to a fixture upon instantiation is called its
data. In the simplest cases these are just key/value pairs used for your
specific fixture class to configure itself. For example in a `ModelFixture`
these are treated as field name and values.

### Composing Fixtures

You can refer to your fixture in other fixtures' data:

```py
P020 = PatientFixture(identifier='P020', author=Norman)
```

You can then use this as you'd expect:

```py
Norman.load()
P020.resolved_data['author'] # User object, not UserFixture
P020.load()                  # correct author FK to User
P020.unload()                # won't affect Norman
```

For this to work, fixtures go through a process called **data resolution**.
This is triggered automatically and fixture clients can ignore its timing.

During data resolution, all references to other fixtures in the fixture's data
are resolved to an appropriate instance of the real data.

## Fixture Classes

To create a new *type* of fixture, you need to define a fixture class. For
this, all you need is a subclass of `AbstractStorageFixture` or a more useful
intermediate base class like `ModelFixture`.

A functioning fixture class has to at least provide these three methods:

* `exists()`
* `load()`
* `unload()`

See `AbstractStorageFixture` for more details.

### Custom Field Resolvers

Field resolvers are a mechanism for fixture classes to define field-specific
processing to be performed after all other fixtures (dependencies) have
been successfully resolved. For example:

```py
class MyFixture(AbstractStorageFixture):
    ...

    @register_field_resolver
    def resolve_genes(self, genes):
        if isinstance(genes, str):
            with open(genes) as f:
                return [line.strip() for line in f.readlines()]


fixture = MyFixture(genes='/path/to/some/file')
fixture.resolved_data['genes'] # a list of genes
```

Field resolvers are invoked after and only if all other fixtures have already
been successfully resolved. The value that a field resolver receives as
argument is the field value after fixture resolution.

### Model Fixtures

For the very common case where a fixture class is such that its fixtures are
1:1 with instances of a django model in the database, a special base class is
provided `ModelFixture`. For example:

```py
class PatientFixture(ModelFixture):
    model = Patient
    identifying_fields = ['identifier']
```

## Fixture batch API

Fixture modules allow you build complex recipes involving multiple fixtures and
load them all in order and in a transaction. The batch API in `lib.batch`
provides two main utilities:

* Fixture modules: any module that has a `FIXTURES` attributes consisting of an
  iterable of fixture instances is a fixture module. Use
  `lib.batch.unpack_fixture_modules()` to convert a number of fixture modules
  to a list of fixtures.
* Batch load/unload: any iterable of fixtures can be loaded or unloaded in one
  database transaction. Use `lib.batch.{load,unload}_fixtures` for this.

## Design Principles

1. **Code as spec**: the implementation of `AbstractStorageFixture` is the *de
   facto* spec of our fixture API. It should be kept completely agnostic about
   specifics of particular fixtures, what they are, and how they are stored. If
   you need to define new generic behavior, consider subclassing it before
   modifying it.
2. **Unified backend API**: fixture classes should ideally use the exact same
   backend API that's used in normal course of operation. If your fixture class
   is getting too complicated, it might be an indication that a corresponding
   backend API is messy or non-existent.
3. **Rigid data resolution implementation**. Getting the timing of data
   resolution right is delicate, specially when there are multiple fixtures and
   complex inter-dependencies. To keep the internal API stable, this logic is
   reserved for `AbstractStorageFixture` and fixture classes are discouraged
   from overriding it.
4. **Transactions in batch API**. All other internal fixture API, including
   this class, assume that they are modifying the storage in a transaction and
   can freely raise exceptions for their error control. Specifically core
   fixture API does not concern itself with unloading things if a load fails.
5. **No recursive loading of fixtures**. Suppose fixture `A` refers to fixture
   `B` in its data, and neither `A` or `B` exists in storage. What should
   happen upon `A.load()`?

   We have two options. Either we fail because `B` does not exist, or we
   implicitly also load `B`. Both are easy to implement but the latter makes
   `unload()` impossible to get right. This is why we don't recursively load
   dependency fixtures. A consequence of this is a fixture's dependencies must
   be explicitly loaded before it can be loaded. See fixture modules and batch
   API for convenience utilities.

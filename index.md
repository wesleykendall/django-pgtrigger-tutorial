---
layout: default
permalink: /
---

# django-pgtrigger-tutorial

This is a tutorial repository that you can use to configure and run
various [Postgres Triggers](https://www.postgresql.org/docs/current/sql-createtrigger.html)
inside a Django app using [django-pgtrigger](https://django-pgtrigger.readthedocs.io).

This tutorial was part of the talk given by [Wes Kendall](github.com/wesleykendall) at
the [SF Django Meetup on July 23rd, 2020](https://www.meetup.com/The-San-Francisco-Django-Meetup-Group/events/271678803).

**Contents**
* TOC
{:toc}

# Setup

The tutorial assumes you have [Docker](docker.com) installed on your computer.

Run the following command to set up the entire project:

```
git clone https://github.com/wesleykendall/django-pgtrigger-tutorial.git && \
cd django-pgtrigger-tutorial && \
docker-compose build
```

Wait a few seconds for the build to start and then run this to finish
setup:
```
docker-compose run --rm app python manage.py migrate
```

# Tutorial

The models and associated triggers in this tutorial
are all located under [tutorial/models.py](https://github.com/wesleykendall/pgtrigger-django-tutorial/blob/master/tutorial/models.py)
in the main Github repo. The models have several triggers defined, many
of which we will go through in this tutorial.

Although not required, it is helpful to have a basic understanding of
`django-pgtrigger` before going through this tutorial. Check out the
docs [here](https://django-pgtrigger.readthedocs.io)

**Note** Every example in the tutorial that uses `docker-compose` can
be executed by you locally, assuming that you followed the setup instructions
above.

## Protecting model deletions

``pgtrigger.Protect`` is a trigger definition that raises an exception,
i.e. "protecting" an operation from happening. The trigger can be configured
for whatever conditions and events that need to be protected.

For example, the ``CannotDelete`` model registers a ``pgtrigger.Protect``
trigger to protect against deletions:

```python
class CannotDelete(models.Model):
    """This model cannot be deleted.

    The ``pgtrigger.Protect`` trigger protects the deletion operation
    from happening
    """
    class Meta:
        triggers = [
            pgtrigger.Protect(name='protect_deletes', operation=pgtrigger.Delete)
        ]
```

Run this code locally with the following code that tries to delete
the model. It will fail loudly:

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

# This object cannot be deleted
cannot_delete = CannotDelete.objects.create()
cannot_delete.delete()

";
```

The error will look something like:

```
Traceback (most recent call last):
  File "/usr/local/lib/python3.8/site-packages/django/db/backends/utils.py", line 86, in _execute
    return self.cursor.execute(sql, params)
psycopg2.errors.RaiseException: pgtrigger: Cannot delete rows from tutorial_cannotdelete table
CONTEXT:  PL/pgSQL function pgtrigger_protect_c1608bb7cb9f8647() line 5 at RAISE
```

Instead of trying to protect deletions of a model in the application layer,
a method that can be easily circumvented or ignored, a `pgtrigger.Protect`
trigger can reliably protect against operations you don't want to happen.


## Append-only models

The `pgtrigger.Protect` trigger is useful for many more things than just protecting
deletions. Depending on the combinations of operations and conditions, one
can express many types of protections on models and fields.

For example, this trigger creates an "append-only" model:

```python
class AppendOnly(models.Model):
    """This model can only be appended.

    The ``pgtrigger.Protect`` trigger protects the update or delete operations
    from happening, making this an "append-only" model.
    """
    int_field = models.IntegerField()

    class Meta:
        triggers = [
            pgtrigger.Protect(
                name='append_only',
                operation=pgtrigger.Update | pgtrigger.Delete
            )
        ]
```

Running this code shows how we can create the model but not update or
delete it (i.e. an "append-only" model).

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

from django.db import InternalError

# This model does not allow updates or deletes
append_only = AppendOnly.objects.create(int_field=0)

try:
    # Saving anything will result in an error
    append_only.save()
except InternalError:
    print('Cannot update!')

try:
    append_only.delete()
except InternalError:
    print('Cannot delete!')

";
```

Since we're catching the errors in this example, you'll see output that
looks like this:

```
Cannot update!
Cannot delete!
```


## Read-only fields

The `pgtrigger.Protect` trigger operates at a table level, so one might
ask themselves if it can be used to protect column-level operations.
This is where *conditions* come into play.

A condition on a row-level trigger is a ``WHERE`` clause that can operate
on the ``OLD`` and ``NEW`` rows that are part of the database operation
that's happening. Although
``django-pgtrigger`` allows one to write raw SQL for conditions, the
`pgtrigger.Q` and `pgtrigger.F` objects allow you to construct clauses
on the ``OLD`` and ``NEW`` rows similar to how Django's `Q` and  `F`
objects work.

In this example, we've made the "created_at" field be read-only
by protecting updates only when this field changes.

```python
class ReadOnlyField(models.Model):
    """
    The "created_at" field cannot be updated (i.e. a read-only field).

    Updates to other fields will pass, but any updates to created_at will
    result in an error
    """
    created_at = models.DateTimeField(auto_now_add=True)
    int_field = models.IntegerField()

    class Meta:
        triggers = [
            pgtrigger.Protect(
                name='read_only',
                operation=pgtrigger.Update,
                condition=pgtrigger.Q(old__created_at__df=pgtrigger.F('new__created_at'))
            )
        ]
```

Running this code shows how we are not allowed to update the "created_at"
field after the model is created.

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

from django.db import InternalError
from django.utils import timezone

# This model does not allow updates or deletes
read_only_field = ReadOnlyField.objects.create(int_field=0)

# An update on int_field is fine
read_only_field.int_field = 1
read_only_field.save()

try:
    # An update on created_at will result in an error
    read_only_field.created_at = timezone.now()
    read_only_field.save()
except InternalError:
    print('Cannot update field!')

";
```

Since we're catching the errors in this example, you'll see output that
looks like this:

```
Cannot update field!
```

The error is thrown from the above code because we configured this protection
trigger to only fire whenever the ``created_at`` of the ``OLD`` row
(``old__created_at``)
is distinct from (``old__created_at__df``) the
``created_at`` in the ``NEW`` row of the
update. When this condition doesn't happen, the protection trigger doesn't
fire and we are allowed to proceed with the operation.

**Note** If you want to make multiple read-only fields, extend your condition
to support it. For example, this condition will make `created_at` and
`int_field` both read-only fields.

```python
class ReadOnlyFields(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    int_field = models.IntegerField()

    class Meta:
        triggers = [
            pgtrigger.Protect(
                name='multiple_read_only',
                operation=pgtrigger.Update,
                condition=(
                    pgtrigger.Q(old__created_at__df=pgtrigger.F('new__created_at')) |
                    pgtrigger.Q(old__int_field__df=pgtrigger.F('new__int_field'))
                )
            )
        ]
```

## Soft-deleting models

A model is "soft" deleted whenever a field is updated to indicate that
the object is deleted. For example, oftentimes one will set an ``is_active``
flag to ``False`` to indicate a model is deleted without actually deleting it
from the database.

Triggers, specifically `pgtrigger.Before` triggers that run before an
operation, can dynamically ignore the operation being executed and
apply a different operation. The `pgtrigger.SoftDelete` trigger
behaves in this very way, setting a field on a model and saving it
whenever a deletion happens on the model.

Here's an example of how to configure the `pgtrigger.SoftDelete`
trigger on a model.

```python
class SoftDelete(models.Model):
    """
    This model cannot be deleted. When a user tries to delete it, the
    model will be "soft" deleted instead and have the ``is_active``
    boolean set to ``False``
    """
    is_active = models.BooleanField(default=True)

    class Meta:
        triggers = [
            pgtrigger.SoftDelete(
                name='soft_delete',
                field='is_active',
                value=False
            )
        ]
```

Running this code shows how we can delete the model using standard
Django ORM calls without it actually being deleted.

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

# This model does not allow updates or deletes
soft_delete = SoftDelete.objects.create(is_active=True)
soft_delete_id = soft_delete.id

# Let's try to delete the model. Django will still behave as it normally does
# and will flush the object's contents, but the object will still be in the
# database in an inactive state
soft_delete.delete()

soft_delete = SoftDelete.objects.get(id=soft_delete_id)
print('is_active =', soft_delete.is_active)

";
```

The following will print:

```
is_active = False
```

As mentioned in the comments of the example, Django still behaves the same
way, but the database sets the ``is_active`` flag to ``False`` under the hood.

It is important to keep in mind that Django will still try to cascade
delete models that reference soft deleted models. One has the option to
make these models soft delete-able as well, and one can also fully delete
these with ``on_delete=models.CASCADE`` or ignore the delete altogether
with ``on_delete=models.DO_NOTHING`` in their foreign key definition. It
is up to the engineer to decide how cascading model deletion should happen
on soft-delete models in their application.


## Versioning a model

The previous soft-delete example showed an example of a `pgtrigger.Before`
trigger, which is a trigger that modifies rows before the intended operation
takes place. We're going to use a base `pgtrigger.Trigger` class here to
write a trigger that will increment an integer field before an update is applied.

In this example, we're going to write some raw SQL that will be embedded
directly into the trigger function that fires. When writing raw SQL for
a `pgtrigger.Trigger` class, one only needs to write the SQL that executes
inside the trigger function and nothing else.

Below is an example of a model with a "version" field that is updated
any time the model is updated. We've also made sure that this field is
a read-only field so that nobody tries to update the version of the model.

```python
class Versioned(models.Model):
    """
    This model is versioned. The "version" field is incremented on every
    update, and users cannot directly update the "version" field.
    """
    version = models.IntegerField(default=0)
    char_field = models.CharField(max_length=32)

    class Meta:
        triggers = [
            # Protect anyone editing the version field directly
            pgtrigger.Protect(
                name='protect_version_edits',
                operation=pgtrigger.Update,
                condition=pgtrigger.Q(old__version__df=pgtrigger.F('new__version'))
            ),
            # Increment the version field on changes
            pgtrigger.Trigger(
                name='versioned',
                when=pgtrigger.Before,
                operation=pgtrigger.Update,
                func='NEW.version = NEW.version + 1; RETURN NEW;',
                # Don't increment version on redundant updates.
                condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*')
            )
        ]
```

Given our versioned model, the following code shows how the version
field is automatically updated:

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

from django.db import InternalError

versioned = Versioned.objects.create(version=0, char_field='hello')
print('initial version', versioned.version)

# Updating the model results in a new version
versioned.char_field = 'hi'
versioned.save()
versioned.refresh_from_db()
print('version after first update', versioned.version)

# Doing a redundant update does not bump the version
versioned.save()
versioned.refresh_from_db()
print('version after redundant update', versioned.version)

# Bump the version one more time
versioned.char_field = 'new field'
versioned.save()
versioned.refresh_from_db()
print('version after second update', versioned.version)

# Try to edit the version. It will result in an error
versioned.version = 1
try:
    versioned.save()
except InternalError:
    print('Cannot update version!')

";
```

The above example will output this:

```
initial version 0
version after first update 1
version after redundant update 1
version after second update 2
Cannot update version!
```

**Note** In our example trigger, we are incrementing the ``NEW`` row
and returning it. There is no need to do any database operations. Postgres
will take this modified ``NEW`` row and use it when performing the final
``UPDATE`` operation.

**Note** The return value of a ``BEFORE`` trigger is very important since
it tells Postgres what row to use in the database operation. If ``NULL`` is returned, Postgres
will block the operation from being performed. This is how `pgtrigger.SoftDelete`
works.


## Creating "official" interfaces

Have you ever wanted to force engineers to use exactly one interface for
performing a specific database operation? For example, ensuring that
``User.objects.create_user()`` is always used instead of calling
``User.objects.create()``?

The `pgtrigger.Protect` trigger used in combination with
the `pgtrigger.ignore()` context manager / decorator can be used to
accomplish this.

For example, imagine we have an ``OfficialInterface`` model, and we want to ensure
that the ``OfficialInterface.objects.official_create()`` interface is the only
method that can be used to create our example model:

```python
class OfficialInterfaceManager(models.Manager):
    @pgtrigger.ignore('tutorial.OfficialInterface:protect_inserts')
    def official_create(self):
        return self.create()


class OfficialInterface(models.Model):
    """
    This model has inserts protected and can only be created by
    using OfficialInterface.objects.official_create()
    """

    objects = OfficialInterfaceManager()

    class Meta:
        triggers = [
            pgtrigger.Protect(
                name='protect_inserts',
                operation=pgtrigger.Insert,
            )
        ]
```

Let's try to create this model using the standard ``OfficialInterface.objects.create()``
method. It will result in an error, but we can create the object with
our official ``OfficialInterface.objects.official_create()`` interface:

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

from django.db import InternalError

num_objects = OfficialInterface.objects.count()
try:
    OfficialInterface.objects.create()
except InternalError:
    print('No no no... Cannot use that interface!')
    assert OfficialInterface.objects.count() == num_objects

# We can create the object using the official interface
obj = OfficialInterface.objects.official_create()
print('created', obj)
assert OfficialInterface.objects.count() == num_objects + 1

";
```

You should see something similar to the following output (the ID of the
object might be different on your computer):

```
No no no... Cannot use that interface!
created OfficialInterface object (2)
```

In the example, we've used `pgtrigger.ignore()` to dynamically ignore
our insertion protection trigger. `pgtrigger.ignore()` will ignore
the execution of that trigger for a single thread of execution, thus
allowing us to define an "official" interface for a protected operation.

**Note** This example means that the Django admin and any other tools
that call the default ``objects.create()`` won't work. While this may
be desired behavior, keep in mind that a protection trigger will protect
the operation from anywhere (unless it is specifically ignored).


## Restricting fields that transition

Oftentimes a status field on a model has particular states and transitions
among those states. The `pgtrigger.FSM` trigger allows one to ensure
valid transitions (i.e. enforcing a finite state machine) of a field.

Consider the following model that has the following possible transitions of
its status:

1. "unpublished" to "published"
2. "unpublished" to "inactive"
3. "published" to "inactive"

We can list all of these valid transitions in a `pgtrigger.FSM` trigger
like so, and it will raise an exception any time there is an invalid transition:


```python
class FSM(models.Model):
    """The "status" field can only perform configured transitions during
    updates. Any invalid transitions will result in an error.
    """
    class Status(models.TextChoices):
        UNPUBLISHED = 'unpublished'
        PUBLISHED = 'published'
        INACTIVE = 'inactive'

    status = models.CharField(
        choices=Status.choices,
        default=Status.UNPUBLISHED,
        max_length=16
    )

    class Meta:
        triggers = [
            pgtrigger.FSM(
                name='validate_status_transitions',
                field='status',
                transitions=(
                    ('unpublished', 'published'),
                    ('unpublished', 'inactive'),
                    ('published', 'inactive'),
                )
            )
        ]
```

The following code shows how we can perform valid transitions and how
an invalid transition will result in an error:

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

from django.db import InternalError

# The "status" defaults to "unpublished"
fsm = FSM.objects.create()

# We are allowed to transition to "published"
fsm.status = FSM.Status.PUBLISHED
fsm.save()

# We can go to "inactive"
fsm.status = FSM.Status.INACTIVE
fsm.save()

# We cant go from "inactive" to "published"
fsm.status = FSM.Status.PUBLISHED
try:
    fsm.save()
except InternalError:
    print('Cannot make that transition!')

";
```

You'll see the following output:

```
Cannot make that transition!
```

**Note** All triggers in `django-pgtrigger` can have conditions applied to them.
For example, we can also define a `pgtrigger.FSM` trigger that only enforces
transitions under certain conditions.

## Tracking model history and changes

``django-pgtrigger`` can be used to snapshot all model changes, snapshot
changes whenever a particular condition happens, and even attach context from
your application (e.g. the authenticated user) to the triggered event.

Historical tracking and auditing is a problem that is going to be different
for every organization's needs. Because of the scope of this problem, we
have created an entire history tracking library called
[django-pghistory](https://django-pghistory.readthedocs.io)
that solves common needs for doing history tracking. It is implemented
using ``django-pgtrigger``, and we show an example of it here.

The following example configures a model so that the following changes are
tracked:

1. All model changes. Whenever an insert or update happens, a "snapshot"
   event will be created that snapshots every field of the model by default.
   This is a basic way of how one can track all history for a model.
2. Creations of the model. When the model is created, a special "create"
   event is fired that snapshots the fields of the model at time of
   creation.
3. When a field matches a condition. We fire the "low_int" event whenever
   the "int_field" is under 0 for any model update.

```python
@pghistory.track(
    # Create a "snapshot" event on every insert/update
    pghistory.Snapshot('snapshot'),
    # Create a "create" event whenever a model is created
    pghistory.AfterInsert('create'),
    # Create a "low_int" event on every update where int_field < 0
    pghistory.AfterUpdate('low_int', condition=pgtrigger.Q(new__int_field__lt=0)),
)
class Tracked(models.Model):
    """
    This model uses django-pghistory to track and snapshot field
    changes and events on this model. django-pghistory is a library on
    top of django-pgtrigger that helps make history tracking on Django
    models easy
    """
    int_field = models.IntegerField()
    char_field = models.CharField(max_length=64)

```

Snapshot triggers from ``django-pghistory`` will create event tables that
hold all events. Run this code to create events and access them. We'll also
attach some context to the events:

```
docker-compose run --rm app python manage.py shell_plus --quiet-load -c "

import pghistory.models
import pprint

# All changes to this model will be tracked, and we'll also track
# other configured events
tracked = Tracked.objects.create(int_field=1, char_field='hello')

# Make 4 different changes
tracked.char_field = 'hi'
tracked.int_field = 0
tracked.save()

tracked.char_field = 'bye'
tracked.save()

# Let's add some context to these last events
with pghistory.context(misc='context'):

    # Since int_field < 0, we'll start firing a "low_int" event here
    tracked.int_field = -1
    tracked.char_field = 'foo'
    tracked.save()

    tracked.char_field = 'bar'
    tracked.save()

# Now that we've done our updates, let's explore the events. First,
# let's print all of values of the tracked snapshots along with any
# context
print('snapshots')
pprint.pprint(list(
    tracked.event
    .filter(pgh_label='snapshot')
    .values('int_field', 'char_field', 'pgh_context__metadata')
    .order_by('pgh_created_at')
))
print()

# Use the special AggregateEvent proxy model in pghistory to render
# snapshot diffs
print('diffs')
pprint.pprint(list(
    pghistory.models.AggregateEvent.objects.target(tracked)
    .filter(pgh_label='snapshot')
    .values('pgh_diff')
    .order_by('pgh_created_at')
))
print()

create_events = tracked.event.filter(pgh_label='create').count()
low_int_events = tracked.event.filter(pgh_label='low_int').count()
print('create events', create_events)
print('low_int events', low_int_events)

";
```

You'll see output that looks like this:

```
snapshots
[{'char_field': 'hello', 'int_field': 1, 'pgh_context__metadata': None},
 {'char_field': 'hi', 'int_field': 0, 'pgh_context__metadata': None},
 {'char_field': 'bye', 'int_field': 0, 'pgh_context__metadata': None},
 {'char_field': 'foo',
  'int_field': -1,
  'pgh_context__metadata': {'misc': 'context'}},
 {'char_field': 'bar',
  'int_field': -1,
  'pgh_context__metadata': {'misc': 'context'}}]

diffs
[{'pgh_diff': None},
 {'pgh_diff': {'char_field': ['hello', 'hi'], 'int_field': [1, 0]}},
 {'pgh_diff': {'char_field': ['hi', 'bye']}},
 {'pgh_diff': {'char_field': ['bye', 'foo'], 'int_field': [0, -1]}},
 {'pgh_diff': {'char_field': ['foo', 'bar']}}]

create events 1
low_int events 2
```

In the "snapshots" section of the output, we've rendered all of our snapshots
in order. The last two snapshots have context associated with them that we
attached using ``pghistory.context()``.

The "diffs" section shows how to use `pghistory.models.AggregateEvent`
to aggregate events for the target model and render diffs of events. These
diffs show a "before" and "after" of the fields that were changed in the
filtered events.

The last two prints show counts of the specific events that we configured
to track.

This example only touches the surface of what is offered by
[django-pghistory](https://django-pghistory.readthedocs.io). Be sure
to [read the docs](https://django-pghistory.readthedocs.io) to learn
more about how to configure it for your use case.

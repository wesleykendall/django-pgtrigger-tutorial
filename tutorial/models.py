from django.db import (
    models,
)
import pghistory
import pgtrigger


@pgtrigger.register(
    pgtrigger.Protect(
        name='protect_deletes',
        operation=pgtrigger.Delete,
    )
)
class CannotDelete(models.Model):
    """This model cannot be deleted.

    The ``pgtrigger.Protect`` trigger protects the deletion operation
    from happening
    """


@pgtrigger.register(
    pgtrigger.Protect(
        name='append_only',
        operation=(pgtrigger.Update | pgtrigger.Delete),
    )
)
class AppendOnly(models.Model):
    """This model can only be appended.

    The ``pgtrigger.Protect`` trigger protects the update or delete operations
    from happening, making this an "append-only" model.
    """

    int_field = models.IntegerField()


@pgtrigger.register(
    pgtrigger.Protect(
        name='read_only_field',
        operation=pgtrigger.Update,
        condition=pgtrigger.Q(
            old__created_at__df=pgtrigger.F("new__created_at")
        ),
    )
)
class ReadOnlyField(models.Model):
    """
    The "created_at" field cannot be updated (i.e. a read-only field).

    Updates to other fields will pass, but any updates to created_at will
    result in an error
    """

    created_at = models.DateTimeField(auto_now_add=True)
    int_field = models.IntegerField()


@pgtrigger.register(
    pgtrigger.SoftDelete(
        name='soft_delete',
        field='is_active',
        value=False,
    )
)
class SoftDelete(models.Model):
    """
    This model cannot be deleted. When a user tries to delete it, the
    model will be "soft" deleted instead and have the ``is_active``
    boolean set to ``False``
    """

    is_active = models.BooleanField(default=True)


@pgtrigger.register(
    pgtrigger.Protect(
        name='versioned',
        operation=pgtrigger.Update,
        condition=pgtrigger.Q(old__version__df=pgtrigger.F('new__version')),
    ),
    pgtrigger.Trigger(
        when=pgtrigger.Before,
        operation=pgtrigger.Update,
        func='NEW.version = NEW.version + 1; RETURN NEW;',
        condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
    ),
)
class Versioned(models.Model):
    """
    This model is versioned. The "version" field is incremented on every
    update, and users cannot directly update the "version" field.
    """

    version = models.IntegerField(default=0)
    char_field = models.CharField(max_length=32)


class OfficialInterfaceManager(models.Manager):
    @pgtrigger.ignore('tutorial.OfficialInterface:protect_inserts')
    def official_create(
        self,
    ):
        return self.create()


@pgtrigger.register(
    pgtrigger.Protect(
        name='protect_inserts',
        operation=pgtrigger.Insert,
    )
)
class OfficialInterface(models.Model):
    """
    This model has inserts protected and can only be created by
    using OfficialInterface.objects.official_create()
    """

    objects = OfficialInterfaceManager()


@pgtrigger.register(
    pgtrigger.FSM(
        name='check_status_transitions',
        field='status',
        transitions=(
            (
                'unpublished',
                'published',
            ),
            (
                'unpublished',
                'inactive',
            ),
            (
                'published',
                'inactive',
            ),
        ),
    )
)
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
        max_length=16,
    )


@pghistory.track(
    # Create a "snapshot" event on every insert/update
    pghistory.Snapshot('snapshot'),
    # Create a "create" event whenever a model is created
    pghistory.AfterInsert('create'),
    # Create a "low_int" event on every update where int_field < 0
    pghistory.AfterUpdate(
        'low_int',
        condition=pgtrigger.Q(new__int_field__lt=0),
    ),
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

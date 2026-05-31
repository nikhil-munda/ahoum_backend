from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import UserProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create a UserProfile whenever a new User row is inserted.
    Role defaults to ROLE_SEEKER and is overwritten immediately by
    SignupSerializer; the default only applies to users created outside
    the normal signup flow (e.g. createsuperuser).
    """
    if created:
        UserProfile.objects.create(user=instance)

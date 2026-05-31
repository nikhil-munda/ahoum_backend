from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailAuthBackend(ModelBackend):
    """
    Authenticate by email + password.

    username is a uuid4().hex set internally at signup and never exposed.
    All lookups are by User.email. The ModelBackend fallback in
    AUTHENTICATION_BACKENDS handles username-based admin login.
    """

    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None:
            return None

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # email is not DB-unique on Django's default User model;
            # uniqueness is enforced at the API layer in SignupSerializer.
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

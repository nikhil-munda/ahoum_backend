from rest_framework.permissions import BasePermission


class IsEventOwner(BasePermission):
    """
    Object-level permission: only the event's creator may update or delete it.
    has_permission returns True so this class can be composed with view-level
    permissions without blocking non-object actions (list, create, my_events).
    """

    message = "You do not own this event."
    code = "not_owner"

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        return obj.created_by == request.user

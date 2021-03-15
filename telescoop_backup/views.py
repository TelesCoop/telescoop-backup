from django.conf.global_settings import AUTHENTICATION_BACKENDS
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .emails import email_user_activation
from .models import User
from .serializers import AuthSerializer


@api_view(["POST"])
@permission_classes([])
def frontend_signup(request):
    """
    Sign up user

    Args:
        request:
            The request body should contain a JSON object such as::
                {
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "email@ex.com",
                    "password": "secret_pa$$w0rD",
                }

    Returns:
        JSON object::
            AuthSerializer
    """
    user = AuthSerializer(data=request.data)
    user.is_valid(raise_exception=True)
    user = user.save()
    email_user_activation(request, user)

    return Response(status=201)


@api_view(["POST"])
@permission_classes([])
def frontend_login(request):
    """
    Log in a user

    Args:
        request:
            The request body should contain a JSON object such as::

              {"email": "email@ex.com",
               "password": "secret_pa$$w0rD"}

    Returns:
        JSON object::
            AuthSerializer
    """

    data = request.data
    email, password = data["email"].lower(), data["password"]

    user = authenticate(email=email, password=password)

    if user is not None:
        user.backend = AUTHENTICATION_BACKENDS[0]
        login(request, user)
        return Response(AuthSerializer(user).data)
    else:
        return HttpResponse("Email et mot de passe ne correspondent pas", status=400)


@api_view(["POST"])
def frontend_logout(request):
    """Log out view."""
    logout(request)
    return HttpResponse(status=200)


@api_view(["GET"])
@ensure_csrf_cookie
@permission_classes([])
def who_am_i(request):
    """Returns information about the current user."""
    if request.user.is_anonymous:
        return Response(status=400)

    return Response(AuthSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([])
def user_activation(request):
    """Active user"""
    try:
        user = User.objects.get(
            email=request.data.get("email"),
            activation_key=request.data.get("activation_key"),
        )
    except User.DoesNotExist:
        return Response(status=404)

    if not user.is_active:
        user.is_active = True
        user.save()

    return Response(status=200)

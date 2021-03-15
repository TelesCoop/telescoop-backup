from django.core import exceptions
from django.contrib.auth.hashers import make_password
from django.contrib.auth import password_validation
from rest_framework import serializers
from .models import User


class AuthSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=True, max_length=150)
    email = serializers.EmailField(required=True, max_length=100)
    password = serializers.CharField(write_only=True, required=True, max_length=100)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "password")

    def validate_password(self, value):
        errors = None
        try:
            password_validation.validate_password(password=value, user=User)
        except exceptions.ValidationError as e:
            errors = {"password": list(e.messages)}

        if errors:
            raise serializers.ValidationError(errors)
        return make_password(value)

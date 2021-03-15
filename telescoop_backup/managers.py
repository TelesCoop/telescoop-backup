from django.contrib.auth.models import BaseUserManager
from typing import Optional


class UserManager(BaseUserManager):
    def create_user(
        self,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        password: Optional[str] = None,
        is_active: Optional[bool] = False,
        is_admin: Optional[bool] = False,
    ):
        """
        Creates and saves a User with the given email and password.
        """
        if not email:
            raise ValueError("Users must have an email address")

        user = self.model(
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
            is_admin=is_admin,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        first_name: Optional[str] = "toto",
        last_name: Optional[str] = "admin",
        password=None,
        is_active: bool = True,
    ):
        """
        Creates and saves a superuser with the given email and password.
        """
        user = self.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
        )
        user.is_admin = True
        user.is_active = is_active
        user.save(using=self._db)
        return user

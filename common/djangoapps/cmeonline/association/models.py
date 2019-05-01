"""
  McDaniel
  May-2019

  Extend Django user table with custom attribute fields for CME Online.

  Reference: https://docs.djangoproject.com/en/1.11/topics/auth/customizing/#extending-the-existing-user-model

"""
from __future__ import absolute_import
import os
from django.contrib.auth.models import User
from django.db import models


# Create your models here.
class Association(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    association_name = models.CharField(max_length=100)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username

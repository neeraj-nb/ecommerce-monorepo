"""Seed dummy User rows in bulk, for load-test data volume / general realism.

Unlike the order/product/review seeders, there's no known unindexed-scan
endpoint this specifically targets today -- email is already a unique
(indexed) field, and the only per-user lookup is by primary key
(users/<id>/, /profile/). It exists so a load-tested system has a
realistically large user base overall, not to expose one particular bug.

All seeded users share ONE pre-hashed password -- hashing per-user at volume
would be extremely slow, since password hashing is deliberately expensive by
design. Fine for disposable fixture data; these are not meant to be used as
real credentials for anything sensitive.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = 'Generate dummy users in bulk for load-test data volume.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=20000)
        parser.add_argument('--batch-size', type=int, default=2000)
        parser.add_argument('--password', default='LoadTestPassw0rd!')

    def handle(self, *args, **options):
        count = options['count']
        batch_size = options['batch_size']
        hashed = make_password(options['password'])  # hash once, reuse -- see module docstring

        created_total = 0
        for start in range(0, count, batch_size):
            n = min(batch_size, count - start)
            users = []
            for i in range(start, start + n):
                users.append(User(
                    username=f"dummy_user_{i}",
                    email=f"dummy_user_{i}@loadtest.example.com",
                    password=hashed,
                    is_active=True,
                ))
            User.objects.bulk_create(users, ignore_conflicts=True)
            created_total += n
            self.stdout.write(f"  ... {created_total}/{count}")

        self.stdout.write(self.style.SUCCESS(f"Successfully created {created_total} dummy users"))

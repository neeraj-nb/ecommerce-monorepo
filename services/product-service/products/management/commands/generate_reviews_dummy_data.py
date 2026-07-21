"""Seed Review rows in bulk for existing products, for load-test data volume.

Bypasses Review.save()'s per-row incremental rating update (update_rating_add
in models.py) -- bulk_create doesn't call save() at all, so ratings are
recomputed once per product afterward via update_rating() instead of once per
review inserted.

ProductSerializer nests each product's FULL, unbounded review list inline,
and ProductListView has no pagination -- this command exists to make that
cost visible under load, not to fix it.
"""
import random

from django.core.management.base import BaseCommand
from faker import Faker

from products.models import Product, Review


class Command(BaseCommand):
    help = 'Generate dummy reviews for existing products (bulk-seeded, rating recomputed once per product).'

    def add_arguments(self, parser):
        parser.add_argument('--per-product', type=int, default=20, help='Reviews to create per product')
        parser.add_argument(
            '--max-products', type=int, default=None,
            help='Limit to the first N products (default: all existing products)',
        )
        parser.add_argument('--batch-size', type=int, default=2000)

    def handle(self, *args, **options):
        per_product = options['per_product']
        max_products = options['max_products']
        batch_size = options['batch_size']
        fake = Faker()

        products = Product.objects.all()
        if max_products:
            products = products[:max_products]
        product_ids = list(products.values_list('id', flat=True))

        batch = []
        total_created = 0
        touched_product_ids = set()

        def flush():
            nonlocal batch, total_created
            if not batch:
                return
            # ignore_conflicts: unique_together('product','user_id') could rarely
            # collide with a pre-existing review from an earlier seeding run --
            # skip the duplicate row rather than fail the whole batch over it.
            Review.objects.bulk_create(batch, ignore_conflicts=True)
            total_created += len(batch)
            self.stdout.write(f"  ... {total_created} reviews")
            batch = []

        for product_id in product_ids:
            user_ids = random.sample(range(1, 10_000_000), per_product)
            for user_id in user_ids:
                batch.append(Review(
                    product_id=product_id,
                    user_id=user_id,
                    rating=random.randint(1, 5),
                    title=fake.sentence(nb_words=4),
                    comment=fake.text(max_nb_chars=200),
                ))
            touched_product_ids.add(product_id)
            if len(batch) >= batch_size:
                flush()
        flush()

        self.stdout.write("Recomputing ratings for touched products...")
        for product in Product.objects.filter(id__in=touched_product_ids):
            product.update_rating()

        self.stdout.write(self.style.SUCCESS(
            f"Successfully created {total_created} dummy reviews across {len(touched_product_ids)} products"
        ))

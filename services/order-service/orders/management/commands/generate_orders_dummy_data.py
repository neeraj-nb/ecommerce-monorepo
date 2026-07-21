"""Seed historical Order/OrderItem rows directly via bulk_create, bypassing
the saga entirely -- this is fixture data for load-test table volume, not
meant to exercise the saga itself.

In particular: Order.user_id has no database index today, which a handful of
test orders can't expose but a large, varied table will (OrderListView's
filter(user_id=...) sequential-scans the whole table as it grows). This
command exists to make that cost visible under load, not to fix it.
"""
import random

from django.core.management.base import BaseCommand

from orders.models import Order, OrderItem

STATUSES = [Order.Status.CONFIRMED, Order.Status.CANCELLED, Order.Status.PENDING, Order.Status.INVENTORY_RESERVED]
STATUS_WEIGHTS = [0.85, 0.10, 0.03, 0.02]


class Command(BaseCommand):
    help = 'Generate dummy historical orders (bulk, bypasses the saga) for load-test data volume.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=50000, help='Number of orders to create')
        parser.add_argument(
            '--user-count', type=int, default=5000,
            help='Spread orders across this many distinct user_ids (no FK -- need not exist in user-service)',
        )
        parser.add_argument(
            '--product-count', type=int, default=2000,
            help='Distinct product_ids referenced in order items (no FK -- need not exist in product-service)',
        )
        parser.add_argument('--batch-size', type=int, default=2000)

    def handle(self, *args, **options):
        count = options['count']
        user_count = options['user_count']
        product_count = options['product_count']
        batch_size = options['batch_size']

        created_total = 0
        for start in range(0, count, batch_size):
            n = min(batch_size, count - start)
            orders = []
            for _ in range(n):
                status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
                orders.append(Order(
                    user_id=random.randint(1, user_count),
                    status=status,
                    total_amount=round(random.uniform(15.0, 400.0), 2),
                    currency='USD',
                    shipping_name='Load Test Customer',
                    shipping_address=f"{random.randint(1, 9999)} Load Test Ave",
                    cancel_reason='Simulated decline' if status == Order.Status.CANCELLED else '',
                ))
            created = Order.objects.bulk_create(orders)

            items = []
            for o in created:
                for _ in range(random.randint(1, 4)):
                    product_id = random.randint(1, product_count)
                    items.append(OrderItem(
                        order=o,
                        product_id=product_id,
                        product_name=f"Load Test Product {product_id}",
                        unit_price=round(random.uniform(5.0, 150.0), 2),
                        quantity=random.randint(1, 5),
                    ))
            OrderItem.objects.bulk_create(items)

            created_total += n
            self.stdout.write(f"  ... {created_total}/{count}")

        self.stdout.write(self.style.SUCCESS(f"Successfully created {created_total} dummy orders"))

from django.core.management.base import BaseCommand
from products.models import Product
from faker import Faker
import random
from django.utils.text import slugify

class Command(BaseCommand):
    help = 'Generate dummy products'

    def add_arguments(self, parser):
        # Add optional argument --count
        parser.add_argument(
            '--count',
            type=int,
            default=10000,
            help='Number of dummy products to create',
        )

    def handle(self, *args, **kwargs):
        count = kwargs['count']
        fake = Faker()
        products = []

        for _ in range(count):
            name = fake.unique.word().title() + " " + fake.word().title()
            slug = slugify(name + "-" + str(random.randint(1, 10000)))
            category = fake.word().title()
            desc = fake.text(max_nb_chars=200)
            price = round(random.uniform(10.0, 1000.0), 2)
            discount_price = round(price * random.uniform(0.5, 0.9), 2)
            stock = random.randint(0, 500)
            sold_by = fake.company()
            average_rating = round(random.uniform(0, 5), 2)
            total_reviews = random.randint(0, 1000)

            products.append(Product(
                name=name,
                slug=slug,
                category=category,
                desc=desc,
                stock=stock,
                price=price,
                discount_price=discount_price,
                sold_by=sold_by,
                average_rating=average_rating,
                total_reviews=total_reviews
            ))

        Product.objects.bulk_create(products, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f'Successfully created {count} products'))

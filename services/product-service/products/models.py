from django.db import models
from django.utils.text import slugify

class Product(models.Model):
    name = models.CharField(max_length=100)
    desc = models.TextField(max_length=500)
    category = models.CharField(max_length=50, null=True)
    slug = models.SlugField(max_length=50, unique=True, editable=False)
    picture = models.ImageField(upload_to="products/images",null=True,blank=True)
    stock = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10,decimal_places=2)
    discount_price = models.DecimalField(max_digits=10,decimal_places=2)
    sold_by = models.CharField(max_length=100)
    is_available = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)  # Auto updated
    total_reviews = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name).lower()
        return super(Product, self).save(*args, **kwargs)

    def update_rating(self):
        """Recalculate average rating and total reviews."""
        reviews = self.reviews.all()
        self.total_reviews = reviews.count()
        self.average_rating = (
            reviews.aggregate(models.Avg('rating'))['rating__avg'] or 0
        )
        self.save()
        
    def update_rating_add(self, new):
        """Recalculate average rating and total reviews."""
        self.total_reviews = self.total_reviews + 1
        self.average_rating = (self.average_rating * (self.total_reviews-1) + new)/ self.total_reviews
        self.save()
        
    def update_rating_delete(self, remove):
        """Recalculate average rating and total reviews."""
        self.total_reviews = self.total_reviews - 1
        self.average_rating = (self.average_rating * (self.total_reviews+1) - remove)/ self.total_reviews
        self.save()
    
    def _str_(self):
        return self.name
        
class Review(models.Model):
    
    product = models.ForeignKey(Product, related_name='reviews', on_delete=models.CASCADE)
    user_id = models.UUIDField()  # reference to external user service
    rating = models.PositiveSmallIntegerField()  # 1-5 stars
    title = models.CharField(max_length=100)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user_id')  # Prevent duplicate reviews by the same user
        ordering = ['-created_at']

    def _str_(self):
        return f"{self.product.name} - {self.title}"

    def save(self, *args, **kwargs):
        """Override save to auto-update product rating."""
        super().save(*args, **kwargs)
        self.product.update_rating_add(self.rating)
        
    def delete(self, *args, **kwargs):
        """Override delete to auto-update product rating."""
        super().delete(*args, **kwargs)
        self.product.update_rating_delete(self.rating)
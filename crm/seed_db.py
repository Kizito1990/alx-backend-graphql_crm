from .models import Customer, Product

def run():
    customers = [
        {"name": "John Doe", "email": "john@example.com", "phone": "+1234567890"},
        {"name": "Jane Smith", "email": "jane@example.com"}
    ]
    for c in customers:
        Customer.objects.get_or_create(**c)

    products = [
        {"name": "Phone", "price": 300.00, "stock": 15},
        {"name": "Headphones", "price": 50.00, "stock": 50}
    ]
    for p in products:
        Product.objects.get_or_create(**p)

    print("Database seeded successfully!")

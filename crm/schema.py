import graphene
from graphene_django import DjangoObjectType
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
import re

from .models import Customer, Product, Order
from .filters import CustomerFilter, ProductFilter, OrderFilter
from graphene_django.filter import DjangoFilterConnectionField


# ============================
# GraphQL Types
# ============================
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = "__all__"


class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = "__all__"


class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = "__all__"


# ============================
# Input Types
# ============================
class CustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)


class ProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    price = graphene.Decimal(required=True)  # Decimal for precision
    stock = graphene.Int(required=False)


class OrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime(required=False)


# ============================
# Mutations
# ============================
class CreateCustomer(graphene.Mutation):
    class Arguments:
        input = CustomerInput(required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String()

    def mutate(self, info, input):
        # Email uniqueness check
        if Customer.objects.filter(email=input.email).exists():
            raise ValidationError("Email already exists")

        # Phone validation (if provided)
        if input.phone:
            pattern = r'^(\+?\d{7,15}|\d{3}-\d{3}-\d{4})$'
            if not re.match(pattern, input.phone):
                raise ValidationError("Invalid phone format. Use +1234567890 or 123-456-7890")

        customer = Customer(name=input.name, email=input.email, phone=input.phone)
        customer.full_clean()
        customer.save()

        return CreateCustomer(customer=customer, message="Customer created successfully")


class BulkCreateCustomers(graphene.Mutation):
    class Arguments:
        input = graphene.List(CustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)

    def mutate(self, info, input):
        created_customers = []
        errors = []

        with transaction.atomic():
            for idx, data in enumerate(input):
                try:
                    if Customer.objects.filter(email=data.email).exists():
                        raise ValidationError(f"Email already exists: {data.email}")
                    if data.phone:
                        pattern = r'^(\+?\d{7,15}|\d{3}-\d{3}-\d{4})$'
                        if not re.match(pattern, data.phone):
                            raise ValidationError(f"Invalid phone format: {data.phone}")

                    customer = Customer(name=data.name, email=data.email, phone=data.phone)
                    customer.full_clean()
                    customer.save()
                    created_customers.append(customer)

                except ValidationError as e:
                    errors.append(f"Row {idx+1}: {', '.join(e.messages)}")

        return BulkCreateCustomers(customers=created_customers, errors=errors)


class CreateProduct(graphene.Mutation):
    class Arguments:
        input = ProductInput(required=True)

    product = graphene.Field(ProductType)

    def mutate(self, info, input):
        # Decimal handling to avoid float issues
        try:
            price_value = Decimal(str(input.price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            raise ValidationError("Invalid price format. Must be a number with up to 2 decimal places.")

        if price_value <= 0:
            raise ValidationError("Price must be positive")
        if input.stock is not None and input.stock < 0:
            raise ValidationError("Stock cannot be negative")

        product = Product(name=input.name, price=price_value, stock=input.stock or 0)
        product.full_clean()
        product.save()

        return CreateProduct(product=product)


class CreateOrder(graphene.Mutation):
    class Arguments:
        input = OrderInput(required=True)

    order = graphene.Field(OrderType)

    def mutate(self, info, input):
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except ObjectDoesNotExist:
            raise ValidationError("Invalid customer ID")

        products = Product.objects.filter(pk__in=input.product_ids)
        if not products.exists():
            raise ValidationError("Invalid product IDs")
        if len(products) != len(input.product_ids):
            raise ValidationError("Some product IDs are invalid")
        if products.count() < 1:
            raise ValidationError("At least one product must be selected")

        order = Order(customer=customer, order_date=input.order_date or timezone.now())
        order.save()
        order.products.set(products)

        # Calculate total accurately
        total = sum(p.price for p in products)
        order.total_amount = Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        order.save()

        return CreateOrder(order=order)


# ============================
# Query + Mutation Registration
# ============================
class Query(graphene.ObjectType):
    all_customers = DjangoFilterConnectionField(CustomerType, filterset_class=CustomerFilter, order_by=graphene.List(of_type=graphene.String))
    all_products = DjangoFilterConnectionField(ProductType, filterset_class=ProductFilter, order_by=graphene.List(of_type=graphene.String))
    all_orders = DjangoFilterConnectionField(OrderType, filterset_class=OrderFilter, order_by=graphene.List(of_type=graphene.String))

    def resolve_all_customers(self, info, **kwargs):
        qs = Customer.objects.all()
        order_by = kwargs.get('order_by')
        if order_by:
            qs = qs.order_by(*order_by)
        return qs

    def resolve_all_products(self, info, **kwargs):
        qs = Product.objects.all()
        order_by = kwargs.get('order_by')
        if order_by:
            qs = qs.order_by(*order_by)
        return qs

    def resolve_all_orders(self, info, **kwargs):
        qs = Order.objects.all()
        order_by = kwargs.get('order_by')
        if order_by:
            qs = qs.order_by(*order_by)
        return qs

        
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()

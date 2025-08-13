import graphene
from graphene_django import DjangoObjectType
from .models import Customer, Product, Order
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP


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
    price = graphene.Float(required=True)
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
        if Customer.objects.filter(email=input.email).exists():
            raise ValidationError("Email already exists")
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
        # Convert to Decimal and force 2 decimal places
        try:
            price_value = Decimal(str(input.price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            raise ValidationError("Invalid price format. Must be a number with up to 2 decimal places.")

        if price_value <= 0:
            raise ValidationError("Price must be positive")
        if input.stock is not None and input.stock < 0:
            raise ValidationError("Stock cannot be negative")

        product = Product(
            name=input.name,
            price=price_value,
            stock=input.stock or 0
        )
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

        order = Order(customer=customer, order_date=input.order_date or timezone.now())
        order.save()
        order.products.set(products)
        order.calculate_total()
        return CreateOrder(order=order)


# ============================
# Query + Mutation Registration
# ============================
class Query(graphene.ObjectType):
    customers = graphene.List(CustomerType)
    products = graphene.List(ProductType)
    orders = graphene.List(OrderType)

    def resolve_customers(self, info):
        return Customer.objects.all()

    def resolve_products(self, info):
        return Product.objects.all()

    def resolve_orders(self, info):
        return Order.objects.all()


class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()

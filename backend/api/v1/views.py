from datetime import datetime

from api.filters import IngredientFilter, RecipeFilter
from api.pagination import CustomPagination
from api.permissions import IsAdminOrReadOnly, IsAuthorOrReadOnly
from api.utils.mixins import MixinMethodPostDelete
from api.v1.serializers import SubscribeSerializer
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from djoser.views import UserViewSet
from recipes.models import (Favourite, Ingredient, IngredientRecipe, Recipe,
                            ShoppingCart, Tag)
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from users.models import Subscribe
from users.serializers import CustomUserSerializer

from .serializers import (IngredientSerializer, RecipeReadSerializer,
                          RecipeSmallSerializer, RecipeWriteSerializer,
                          TagSerializer)

User = get_user_model()


class CustomUserViewSet(UserViewSet, MixinMethodPostDelete):
    queryset = User.objects.all()
    serializer_class = CustomUserSerializer
    pagination_class = CustomPagination

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[IsAuthenticated]
    )
    def subscribe(self, request, **kwargs):
        return self.post_delete_obj(
            Subscribe, User, SubscribeSerializer, request, kwargs.get('id')
        )

    @action(
        detail=False,
        permission_classes=[IsAuthenticated]
    )
    def subscriptions(self, request):
        user = request.user
        queryset = User.objects.filter(subscribing__user=user)
        pages = self.paginate_queryset(queryset)
        serializer = SubscribeSerializer(pages,
                                         many=True,
                                         context={'request': request})
        return self.get_paginated_response(serializer.data)


class IngredientViewSet(ReadOnlyModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    permission_classes = (IsAdminOrReadOnly,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = IngredientFilter


class TagViewSet(ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = (IsAdminOrReadOnly,)


class RecipeViewSet(ModelViewSet, MixinMethodPostDelete):
    queryset = Recipe.objects.all()
    permission_classes = (IsAuthorOrReadOnly | IsAdminOrReadOnly,)
    pagination_class = CustomPagination
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RecipeFilter

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_serializer_class(self):
        if self.request.method in SAFE_METHODS:
            return RecipeReadSerializer
        return RecipeWriteSerializer

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[IsAuthenticated]
    )
    def favorite(self, request, pk):
        return self.post_delete_obj(
            Favourite, Recipe, RecipeSmallSerializer, request, pk
        )

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[IsAuthenticated]
    )
    def shopping_cart(self, request, pk):
        return self.post_delete_obj(
            ShoppingCart, Recipe, RecipeSmallSerializer, request, pk
        )

    @action(
        detail=False,
        permission_classes=[IsAuthenticated]
    )
    def download_shopping_cart(self, request):
        user = request.user
        if not user.shopping_cart.exists():
            return Response(status=HTTP_400_BAD_REQUEST)

        ingredients = IngredientRecipe.objects.filter(
            recipe__shopping_cart__user=request.user
        ).values(
            'ingredient__name',
            'ingredient__measurement_unit'
        ).annotate(sum_amount=Sum('amount'))

        today = datetime.today()
        shopping_list = (
            f'Список покупок для: {user.get_full_name()}\n\n'
            f'Дата: {today:%Y-%m-%d}\n\n'
        )
        shopping_list += '\n'.join([
            f'- {ingredient["ingredient__name"]} '
            f'({ingredient["ingredient__measurement_unit"]})'
            f' - {ingredient["sum_amount"]}'
            for ingredient in ingredients
        ])
        shopping_list += f'\n\nFoodgram ({today:%Y})'

        filename = f'{user.username}_shopping_list.txt'
        response = HttpResponse(shopping_list, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename={filename}'

        return response

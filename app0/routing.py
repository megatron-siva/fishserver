from django.urls import path

from app0 import consumers

websocket_urlpatterns = [
    path('ws/<str:room_name>/', consumers.MainFisherConsummer.as_asgi()),
]
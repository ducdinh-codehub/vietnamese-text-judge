from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/analyze", views.analyze, name="analyze"),
    path("scam", views.scam_page, name="scam"),
    path("api/scam", views.scam_check, name="scam_check"),
    path("emotion", views.emotion_page, name="emotion"),
    path("api/emotion", views.emotion_check, name="emotion_check"),
    path("api/status", views.status, name="status"),
]

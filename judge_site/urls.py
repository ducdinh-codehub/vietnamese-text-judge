from django.urls import include, path

urlpatterns = [
    path("", include("judge.urls")),
]

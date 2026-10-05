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
    path("live", views.live_page, name="live"),
    path("live/queue", views.live_queue_page, name="live_queue"),
    path("api/live/comments", views.live_feed, name="live_feed"),
    path("api/live/post", views.live_post, name="live_post"),
    path("api/live/queue", views.live_queue, name="live_queue_api"),
    path("api/live/queue/<int:comment_id>", views.live_queue_action, name="live_queue_action"),
    path("api/live/reset", views.live_reset, name="live_reset"),
]

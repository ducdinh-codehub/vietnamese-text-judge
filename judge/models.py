from django.conf import settings
from django.db import models

from . import live


class LiveComment(models.Model):
    """One viewer comment in the livestream chat, with how the moderator sorted it."""

    KIND_CHOICES = [(key, f"{k['emoji']} {k['label']}") for key, k in live.KINDS.items()]
    STATUS_CHOICES = [("new", "Đang chờ"), ("done", "Đã xử lý")]

    author = models.CharField(max_length=40)
    text = models.CharField(max_length=300)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    # The words that made the rule fire, shown to moderators as the reason.
    match = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=20)
    laya_negative = models.FloatField()
    # A moderator overruled the block: the comment is shown in the chat after all.
    restored = models.BooleanField(default=False)

    # Only meaningful for queue kinds (order, price, product, complaint).
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="new")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        permissions = [("moderate_live", "Can work through the livestream queue and see hidden comments")]

    def __str__(self):
        return f"{self.author}: {self.text[:40]}"

    @property
    def queued(self):
        return self.kind in live.QUEUE_KINDS

    @property
    def visible(self):
        return self.kind not in live.HIDDEN_KINDS or self.restored

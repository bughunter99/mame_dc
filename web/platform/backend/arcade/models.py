from django.db import models
from django.contrib.auth.models import User
import uuid


class Game(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    rom_download_url = models.URLField()
    wasm_bundle_url = models.URLField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class SaveState(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="save_states")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="save_states")
    slot = models.PositiveSmallIntegerField(default=0)
    state_blob_url = models.URLField()
    checksum = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "game", "slot")


class HighScore(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="high_scores")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="high_scores")
    score = models.BigIntegerField()
    metadata = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "submitted_at"]


class PlaySession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="play_sessions")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="play_sessions")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

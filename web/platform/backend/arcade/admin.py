from django.contrib import admin

from .models import Game, HighScore, SaveState


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "enabled", "updated_at")
    search_fields = ("title", "slug")
    list_filter = ("enabled",)


@admin.register(SaveState)
class SaveStateAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "slot", "updated_at")
    list_filter = ("game", "slot")
    search_fields = ("user__username", "game__title")


@admin.register(HighScore)
class HighScoreAdmin(admin.ModelAdmin):
    list_display = ("game", "user", "score", "submitted_at")
    list_filter = ("game",)
    search_fields = ("user__username", "game__title")

# Register your models here.

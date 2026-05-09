from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/auth/register", views.register_user, name="register_user"),
    path("api/auth/login", views.login_user, name="login_user"),
    path("api/auth/logout", views.logout_user, name="logout_user"),
    path("api/games", views.list_games, name="list_games"),
    path("api/games/sync-local-roms", views.sync_local_roms, name="sync_local_roms"),
    path("api/saves", views.list_save_states, name="list_save_states"),
    path("api/saves/upsert", views.upsert_save_state, name="upsert_save_state"),
    path("api/highscores", views.submit_high_score, name="submit_high_score"),
    path("api/leaderboard", views.leaderboard, name="leaderboard"),
]

from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/auth/register", views.register_user, name="register_user"),
    path("api/auth/login", views.login_user, name="login_user"),
    path("api/auth/logout", views.logout_user, name="logout_user"),
    path("api/games", views.list_games, name="list_games"),
    path("api/games/<int:game_id>/launch", views.launch_game, name="launch_game"),
    path("api/games/<int:game_id>/rom-diagnose", views.diagnose_game_rom, name="diagnose_game_rom"),
    path("api/games/sync-local-roms", views.sync_local_roms, name="sync_local_roms"),
    path("api/roms/download/<str:token>", views.download_local_rom_with_token, name="download_local_rom_with_token"),
    path("api/saves", views.list_save_states, name="list_save_states"),
    path("api/saves/upsert", views.upsert_save_state, name="upsert_save_state"),
    path("api/saves/upload", views.upload_save_state_file, name="upload_save_state_file"),
    path("api/highscores", views.submit_high_score, name="submit_high_score"),
    path("api/leaderboard", views.leaderboard, name="leaderboard"),
]

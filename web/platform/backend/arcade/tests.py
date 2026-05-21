from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Game, HighScore, PlaySession, SaveState


class LaunchApiTests(TestCase):
	def test_launch_for_external_rom_keeps_original_url(self):
		game = Game.objects.create(
			title="Sample External",
			slug="sample-external",
			rom_download_url="https://example.invalid/roms/ext.zip",
			wasm_bundle_url="https://example.invalid/wasm/mame.js",
			enabled=True,
		)

		response = self.client.get(f"/api/games/{game.id}/launch")

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["launch"]["rom_download_url"], game.rom_download_url)
		self.assertEqual(payload["launch"]["wasm_bundle_url"], game.wasm_bundle_url)
		self.assertIsNone(payload["launch"]["token_ttl_seconds"])
		self.assertIn("play_session_id", payload["launch"])
		self.assertTrue(PlaySession.objects.filter(id=payload["launch"]["play_session_id"]).exists())

	def test_launch_for_local_rom_returns_tokenized_download_url(self):
		game = Game.objects.create(
			title="Sample Local",
			slug="sample-local",
			rom_download_url="http://testserver/roms/sample_local.zip",
			wasm_bundle_url="http://testserver/static/wasm/mame.js",
			enabled=True,
		)

		response = self.client.get(f"/api/games/{game.id}/launch")

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		tokenized_url = payload["launch"]["rom_download_url"]
		self.assertIn("/api/roms/download/", tokenized_url)
		self.assertEqual(payload["launch"]["token_ttl_seconds"], 120)


class RomTokenDownloadTests(TestCase):
	@override_settings(LOCAL_ROMS_URL_PREFIX="/roms/")
	def test_signed_rom_download_returns_binary(self):
		with TemporaryDirectory() as temp_dir:
			rom_dir = Path(temp_dir)
			rom_file = rom_dir / "sample_local.zip"
			rom_bytes = b"mame-rom-binary"
			rom_file.write_bytes(rom_bytes)

			with override_settings(LOCAL_ROMS_DIR=rom_dir):
				game = Game.objects.create(
					title="Sample Local",
					slug="sample-local-token",
					rom_download_url="http://testserver/roms/sample_local.zip",
					wasm_bundle_url="http://testserver/static/wasm/mame.js",
					enabled=True,
				)

				launch_response = self.client.get(f"/api/games/{game.id}/launch")
				self.assertEqual(launch_response.status_code, 200)
				launch_payload = launch_response.json()

				tokenized_url = launch_payload["launch"]["rom_download_url"]
				token_path = tokenized_url.replace("http://testserver", "")
				download_response = self.client.get(token_path)

				self.assertEqual(download_response.status_code, 200)
				self.assertEqual(b"".join(download_response.streaming_content), rom_bytes)
				download_response.close()

	@override_settings(LOCAL_ROMS_URL_PREFIX="/roms/")
	def test_launch_infers_sf2rb_from_bootleg_markers(self):
		with TemporaryDirectory() as temp_dir:
			rom_dir = Path(temp_dir)
			rom_file = rom_dir / "sf2ce.zip"
			with zipfile.ZipFile(rom_file, "w") as archive:
				archive.writestr("sf2ce.23", b"a")
				archive.writestr("sf2ce.22", b"b")
				archive.writestr("s92_21a.bin", b"c")

			with override_settings(LOCAL_ROMS_DIR=rom_dir):
				game = Game.objects.create(
					title="SF2 Local",
					slug="sf2-local-token",
					rom_download_url="http://testserver/roms/sf2ce.zip",
					wasm_bundle_url="http://testserver/static/wasm/mame.js",
					enabled=True,
				)

				launch_response = self.client.get(f"/api/games/{game.id}/launch")
				self.assertEqual(launch_response.status_code, 200)
				launch_payload = launch_response.json()
				self.assertEqual(launch_payload["launch"]["machine_name"], "sf2rb")


class RomDiagnosisApiTests(TestCase):
	@override_settings(LOCAL_ROMS_URL_PREFIX="/roms/")
	def test_rom_diagnose_reports_likely_machine_and_missing_markers(self):
		with TemporaryDirectory() as temp_dir:
			rom_dir = Path(temp_dir)
			rom_file = rom_dir / "sf2ce.zip"
			with zipfile.ZipFile(rom_file, "w") as archive:
				archive.writestr("sf2ce.23", b"a")
				archive.writestr("sf2ce.22", b"b")
				archive.writestr("s92_21a.bin", b"c")

			with override_settings(LOCAL_ROMS_DIR=rom_dir):
				game = Game.objects.create(
					title="SF2 Local",
					slug="sf2-local-diagnose",
					rom_download_url="http://testserver/roms/sf2ce.zip",
					wasm_bundle_url="http://testserver/static/wasm/mame.js",
					enabled=True,
				)

				response = self.client.get(f"/api/games/{game.id}/rom-diagnose")
				self.assertEqual(response.status_code, 200)
				payload = response.json()
				self.assertTrue(payload["local_rom"])
				self.assertEqual(payload["inferred_machine"], "sf2rb")
				self.assertEqual(payload["likely_machine"], "sf2rb")
				self.assertGreaterEqual(payload["entry_count"], 3)
				self.assertIn("s92-13m.6c", payload["missing_markers"]["sf2rb"])


class ScoreValidationTests(TestCase):
	def test_submit_high_score_requires_valid_session_and_duration(self):
		game = Game.objects.create(
			title="Score Game",
			slug="score-game",
			rom_download_url="https://example.invalid/roms/score.zip",
			wasm_bundle_url="https://example.invalid/wasm/mame.js",
			enabled=True,
		)
		launch_response = self.client.get(f"/api/games/{game.id}/launch")
		session_id = launch_response.json()["launch"]["play_session_id"]

		response = self.client.post(
			"/api/highscores",
			data={
				"game_id": game.id,
				"score": 1234,
				"session_id": session_id,
				"duration_ms": 10,
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(HighScore.objects.count(), 1)
		score = HighScore.objects.first()
		self.assertEqual(score.metadata["session_id"], session_id)
		self.assertEqual(score.metadata["duration_ms"], 10)

	def test_submit_high_score_rejects_impossible_duration(self):
		game = Game.objects.create(
			title="Score Game 2",
			slug="score-game-2",
			rom_download_url="https://example.invalid/roms/score2.zip",
			wasm_bundle_url="https://example.invalid/wasm/mame.js",
			enabled=True,
		)
		launch_response = self.client.get(f"/api/games/{game.id}/launch")
		session_id = launch_response.json()["launch"]["play_session_id"]

		response = self.client.post(
			"/api/highscores",
			data={
				"game_id": game.id,
				"score": 99999,
				"session_id": session_id,
				"duration_ms": 99999999,
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(HighScore.objects.count(), 0)


class SaveStateUploadTests(TestCase):
	def test_upload_save_state_file_creates_or_updates_slot(self):
		user = User.objects.create_user(username="tester", password="pass-12345")
		self.client.force_login(user)
		game = Game.objects.create(
			title="Save Game",
			slug="save-game",
			rom_download_url="https://example.invalid/roms/save.zip",
			wasm_bundle_url="https://example.invalid/wasm/mame.js",
			enabled=True,
		)

		with TemporaryDirectory() as temp_dir:
			with override_settings(MEDIA_ROOT=Path(temp_dir), MEDIA_URL="/media/"):
				state_file = SimpleUploadedFile(
					"slot0.state",
					b"binary-state-data",
					content_type="application/octet-stream",
				)
				response = self.client.post(
					"/api/saves/upload",
					data={"game_id": str(game.id), "slot": "0", "state_file": state_file},
				)

				self.assertEqual(response.status_code, 201)
				payload = response.json()
				self.assertIn("/media/savestates/", payload["state_blob_url"])
				self.assertEqual(SaveState.objects.count(), 1)


class LocalRomSyncTests(TestCase):
	@override_settings(LOCAL_ROMS_URL_PREFIX="/roms/")
	def test_sync_disables_local_games_without_matching_rom_file(self):
		with TemporaryDirectory() as temp_dir:
			rom_dir = Path(temp_dir)
			(rom_dir / "sf2ce.zip").write_bytes(b"zip-bytes")

			stale_game = Game.objects.create(
				title="sf2rb",
				slug="local-sf2rb",
				rom_download_url="http://testserver/roms/sf2rb.zip",
				wasm_bundle_url="http://testserver/static/wasm/mame.js",
				enabled=True,
			)

			with override_settings(LOCAL_ROMS_DIR=rom_dir):
				response = self.client.post("/api/games/sync-local-roms")

			self.assertEqual(response.status_code, 200)
			payload = response.json()
			self.assertEqual(payload["disabled"], 1)

			stale_game.refresh_from_db()
			self.assertFalse(stale_game.enabled)

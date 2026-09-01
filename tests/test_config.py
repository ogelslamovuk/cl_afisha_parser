import os
import tempfile
import unittest

from src.config import load_config


class ConfigTests(unittest.TestCase):
    def test_local_config_overrides_base_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "config.yaml")
            local_path = os.path.join(tmp, "config.local.yaml")

            with open(base_path, "w", encoding="utf-8") as f:
                f.write(
                    "source:\n"
                    "  api_url: https://api.example.test/base\n"
                    "telegram:\n"
                    "  enabled: true\n"
                    "  bot_token_env: TELEGRAM_BOT_TOKEN\n"
                )
            with open(local_path, "w", encoding="utf-8") as f:
                f.write("telegram:\n  bot_token: local-token\n")

            config = load_config(base_path, local_path=local_path)

        self.assertEqual(config["source"]["api_url"], "https://api.example.test/base")
        self.assertEqual(config["telegram"]["bot_token"], "local-token")
        self.assertEqual(config["telegram"]["bot_token_env"], "TELEGRAM_BOT_TOKEN")


if __name__ == "__main__":
    unittest.main()

import os

from django.apps import AppConfig


class JudgeConfig(AppConfig):
    name = "judge"

    def ready(self):
        # Load the multilingual checkpoint in the background so the first request is fast.
        # Under `runserver` the autoreloader imports the project twice; only warm the child process.
        if os.environ.get("RUN_MAIN") == "true" or os.environ.get("JUDGE_WARMUP") == "1":
            from .analyzer import start_warm_up

            start_warm_up()

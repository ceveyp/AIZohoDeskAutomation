from enum import StrEnum

# Truncate ticket / agent context in log lines (not a retention policy).
LOG_SNIPPET_CHARS = 500


class SupportedModels(StrEnum):
    GPT_5_NANO = "gpt-5-nano"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5 = "gpt-5"

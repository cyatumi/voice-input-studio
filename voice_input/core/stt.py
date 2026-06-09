"""Speech-to-text via OpenAI Whisper API."""
from __future__ import annotations

import io

from openai import OpenAI


class WhisperSTT:
    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self.api_key = api_key
        self.model = model
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("OpenAI APIキーが設定されていません。設定画面で入力してください。")
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def transcribe(self, wav_bytes: bytes, language: str = "ja") -> str:
        if not wav_bytes:
            return ""
        client = self._get_client()
        # OpenAI SDK expects a file-like object with a name attribute.
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"

        # The `prompt` parameter nudges Whisper to output text with proper
        # Japanese punctuation (、。) rather than an unpunctuated stream.
        # It also helps with word boundaries in Japanese.
        whisper_prompt = (
            "以下は日本語の自然な会話・独り言です。"
            "句読点（、。！？）を文脈に合わせて適切に付けて書き起こしてください。"
        )
        response = client.audio.transcriptions.create(
            model=self.model,
            file=audio_file,
            language=language,
            response_format="text",
            prompt=whisper_prompt,
        )
        # When response_format="text", SDK returns the raw string.
        return str(response).strip()

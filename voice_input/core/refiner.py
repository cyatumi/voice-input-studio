"""Text refinement — supports Google Gemini and OpenAI GPT.

Medium intensity by default:
  - remove fillers (えー, あの, えっと)
  - remove unnatural whitespace
  - insert punctuation based on context
  - fix obviously wrong kanji conversions
  - DO NOT change meaning, tone, politeness level
"""
from __future__ import annotations

import google.generativeai as genai
from openai import OpenAI


class GeminiRefiner:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model_name = model
        self._configured = False
        self._model: genai.GenerativeModel | None = None

    def _ensure(self) -> genai.GenerativeModel:
        if not self.api_key:
            raise RuntimeError("Gemini APIキーが設定されていません。設定画面で入力してください。")
        if not self._configured:
            genai.configure(api_key=self.api_key)
            self._configured = True
        if self._model is None:
            self._model = genai.GenerativeModel(self.model_name)
        return self._model

    def refine(self, text: str, system_prompt: str, vocabulary: dict[str, str] | None = None) -> str:
        """Apply prompt-driven refinement. If system_prompt is empty, return text untouched."""
        if not text.strip():
            return text
        if not system_prompt.strip():
            return text

        # Pre-apply vocabulary as a hard override so we don't waste tokens on known fixes.
        if vocabulary:
            for wrong, right in vocabulary.items():
                if wrong in text:
                    text = text.replace(wrong, right)

        model = self._ensure()
        vocab_hint = ""
        if vocabulary:
            entries = "\n".join(f"- 「{w}」→「{r}」" for w, r in vocabulary.items())
            vocab_hint = (
                "\n\n# 用語辞書 (これらの読みが出てきたら必ずこの表記にすること):\n" + entries
            )

        full_prompt = (
            f"{system_prompt}{vocab_hint}\n\n"
            f"# 入力テキスト\n{text}\n\n"
            f"# 整形後のテキストのみ出力 (前置き不要)"
        )

        response = model.generate_content(
            full_prompt,
            generation_config={"temperature": 0.2},
        )
        refined = (response.text or "").strip()
        return refined or text


class OpenAIRefiner:
    """Text refinement via OpenAI Chat Completions (gpt-4o-mini by default).

    Uses the same OpenAI API key as the Whisper STT step — no extra key needed.
    gpt-4o-mini is inexpensive (~$0.15/1M input tokens) and handles Japanese well.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model_name = model
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("OpenAI APIキーが設定されていません。設定画面で入力してください。")
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def refine(self, text: str, system_prompt: str, vocabulary: dict[str, str] | None = None) -> str:
        """Apply prompt-driven refinement using OpenAI Chat Completions."""
        if not text.strip():
            return text
        if not system_prompt.strip():
            return text

        if vocabulary:
            for wrong, right in vocabulary.items():
                if wrong in text:
                    text = text.replace(wrong, right)

        vocab_hint = ""
        if vocabulary:
            entries = "\n".join(f"- 「{w}」→「{r}」" for w, r in vocabulary.items())
            vocab_hint = (
                "\n\n# 用語辞書 (これらの読みが出てきたら必ずこの表記にすること):\n" + entries
            )

        user_content = (
            f"# 入力テキスト\n{text}\n\n"
            f"# 整形後のテキストのみ出力 (前置き不要)"
        )
        full_system = system_prompt + vocab_hint

        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        refined = (response.choices[0].message.content or "").strip()
        return refined or text

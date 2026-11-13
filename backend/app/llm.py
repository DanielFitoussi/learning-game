"""The only module that talks to OpenAI.

To swap the AI provider, write another class with the same complete_json
method (the TextModel protocol in app/text_model.py) and use it instead.
"""

import os

from openai import OpenAI

MODEL_ENV_VAR = "OPENAI_MODEL"

JSON_REMINDER = "Answer with JSON only."


class OpenAITextModel:
    """TextModel backed by the OpenAI Responses API in JSON mode.

    The model name comes from OPENAI_MODEL. The API key is read by the
    OpenAI SDK itself from OPENAI_API_KEY.
    """

    def __init__(self, client: OpenAI | None = None) -> None:
        # Check the model name first, so a missing setting fails before
        # the SDK client is created.
        model_name = os.environ.get(MODEL_ENV_VAR, "").strip()
        if not model_name:
            raise RuntimeError(
                f"The environment variable {MODEL_ENV_VAR} is not set. "
                f"Set it to the OpenAI model name to use."
            )
        self.model_name = model_name
        self.client = client if client is not None else OpenAI()

    def complete_json(self, instructions: str, material: str) -> str:
        """Send the instructions and material, and return the model's JSON text."""
        response = self.client.responses.create(
            model=self.model_name,
            instructions=instructions,
            input=[
                {"role": "user", "content": material},
                {"role": "user", "content": JSON_REMINDER},
            ],
            text={"format": {"type": "json_object"}},
        )
        return response.output_text

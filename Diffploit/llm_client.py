/*
 * Copyright (c) 2025 PoCEffectiveness
 * All rights reserved.
 */


import os
import re
from openai import OpenAI

class LLMClient:
    # def __init__(self, model_name: str = "qwen3-235b-a22b"):
    def __init__(self, model_name: str = "deepseek-chat"):
        self.api_key = "Your_API_Key_Here"  # Replace with your actual API key
        self.base_url = "https://api.deepseek.com/v1"
        self.model_name = model_name
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.system_prompt = "You are a vulnerability exploitation auto-repair expert."

    def ask(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=8192, 
            )
            print(f"[LLMClient] Tokens used: {response.usage.prompt_tokens} (prompt), {response.usage.completion_tokens} (completion), {response.usage.total_tokens} (total)")
            content = response.choices[0].message.content

            print(f"[LLMClient] Prompt: \n{prompt}")
            print(f"[LLMClient] Response: \n{content}")
            match = re.search(r"```(?:\w+\n)?(.*?)```", content, re.DOTALL)
            if match:
                content = match.group(1)

            return content
        except Exception as e:
            return f"[LLMClient Error] {str(e)}"
        
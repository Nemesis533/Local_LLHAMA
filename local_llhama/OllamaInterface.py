import requests

class OllamaClient:
    """
    Client to interact with Ollama server for language model inference.
    """

    def __init__(self, host: str = 'http://localhost:11434', model: str = 'deepseek-r1:14b', system_prompt: str = ''):
        self.host = host.rstrip('/')
        self.model = model
        self.system_prompt = system_prompt

    def set_model(self, model_name: str):
        self.model = model_name

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def send_message(self, user_message: str, temperature: float = 0.5, top_p: float = 0.9, max_tokens: int = 512):
        url = f"{self.host}/api/generate"

        payload = {
            "model": self.model,
            "prompt": user_message,
            "system": self.system_prompt,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens
            },
            "stream": False,
            "think" : False,
        }

        headers = {'Content-Type': 'application/json'}

        try:
            # This sends a POST request, equivalent to curl -X POST
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result.get('response', '').strip()

        except requests.RequestException as e:
            error_msg = ''
            if e.response is not None:
                error_msg = e.response.text
            return f"Error communicating with Ollama: {e}\nServer response: {error_msg}"


if __name__ == "__main__":
    client = OllamaClient(model="deepseek-r1:14b")
    client.set_system_prompt("You are a helpful assistant.")
    response = client.send_message("What is the capital of France?")
    print("Response:", response)

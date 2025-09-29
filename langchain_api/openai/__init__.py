class _Emb: 
    async def create(self, *args, **kwargs):
        raise RuntimeError('OpenAI client not available in this environment')

class AsyncOpenAI: 
    def __init__(self, *args, **kwargs):
        self.embeddings = _Emb()

# Черновой расчёт стоимости токенов для gpt-4.1-mini (примерные значения)
# В реальности подтягивайте цены из официального прайсинга API.

PRICES = {
	"gpt-4.1-mini": {
		"input_per_1k": 0.00005,
		"output_per_1k": 0.00010,
	}
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
	p = PRICES.get(model, PRICES["gpt-4.1-mini"])
	return (input_tokens/1000)*p["input_per_1k"] + (output_tokens/1000)*p["output_per_1k"]

if __name__ == "__main__":
	cost = estimate_cost("gpt-4.1-mini", input_tokens=800, output_tokens=200)
	print({"model": "gpt-4.1-mini", "input_tokens": 800, "output_tokens": 200, "usd": round(cost, 6)})
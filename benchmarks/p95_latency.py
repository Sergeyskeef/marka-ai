import time
import statistics
from typing import List

# Минимальный пинг-бенчмарк: измеряет локальное вычисление как замену сетевому

def measure_once() -> float:
	start = time.perf_counter()
	# Имитация лёгкой работы
	sum(i*i for i in range(5000))
	return (time.perf_counter() - start) * 1000

def main(iterations: int = 50):
	ms: List[float] = [measure_once() for _ in range(iterations)]
	p95 = statistics.quantiles(ms, n=100)[94]
	print({
		"samples": len(ms),
		"avg_ms": round(sum(ms)/len(ms), 3),
		"p95_ms": round(p95, 3),
	})

if __name__ == "__main__":
	main()
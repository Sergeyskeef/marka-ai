import json
import random
import statistics
from collections import Counter


def generate_mock_products(n=100, seed=42):
    random.seed(seed)
    categories = ['electronics', 'home', 'books', 'toys', 'clothing']
    products = []
    for i in range(1, n+1):
        category = random.choices(categories, weights=[0.25,0.2,0.2,0.15,0.2])[0]
        price = round(random.gauss(50 if category=='electronics' else 20, 15), 2)
        price = max(0.5, price)
        rating = round(min(5.0, max(1.0, random.gauss(4.0 if category in ['books','electronics'] else 3.7, 0.5))), 2)
        reviews = max(0, int(abs(random.gauss(30 if category=='electronics' else 10, 20))))
        products.append({
            'id': i,
            'name': f'product_{i}',
            'category': category,
            'price': price,
            'rating': rating,
            'reviews_count': reviews
        })
    return products


def analyze_products(products):
    prices = [p['price'] for p in products]
    ratings = [p['rating'] for p in products]
    report = {}
    report['count'] = len(products)
    report['price_mean'] = statistics.mean(prices)
    report['price_median'] = statistics.median(prices)
    report['price_stddev'] = statistics.pstdev(prices)
    report['rating_mean'] = statistics.mean(ratings)
    report['top_categories'] = Counter([p['category'] for p in products]).most_common(3)
    # find top 5 most expensive
    report['top_expensive'] = sorted(products, key=lambda x: x['price'], reverse=True)[:5]
    # simple correlation-like indicator (not true Pearson here to avoid statistics import complexity)
    avg_price = report['price_mean']
    avg_rating = report['rating_mean']
    report['price_rating_summary'] = {
        'avg_price': avg_price,
        'avg_rating': avg_rating,
        'expensive_high_rating_pct': len([p for p in products if p['price']>avg_price and p['rating']>=avg_rating]) / len(products)
    }
    return report


def save_report(report, path='workspace/report.json'):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def main(n=100):
    print('[INFO] Generating mock products...')
    products = generate_mock_products(n)
    print(f'[INFO] Generated {len(products)} products')
    print('[INFO] Analyzing products...')
    report = analyze_products(products)
    save_report(report)
    print('[INFO] Report saved to workspace/report.json')
    # Print a short summary
    print('[SUMMARY] count={count}, price_mean={price_mean:.2f}, rating_mean={rating_mean:.2f}'.format(
        count=report['count'], price_mean=report['price_mean'], rating_mean=report['rating_mean']
    ))
    return report


if __name__ == '__main__':
    main()

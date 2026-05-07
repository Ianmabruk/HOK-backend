"""Normalize existing product category values to URL-safe slugs.

Examples:
- "Living Room" -> "living-room"
- "living_room" -> "living-room"
- "  KITCHEN  " -> "kitchen"

Run:
  python scripts/normalize_product_categories.py
"""

import re

from app import create_app
from models.models import Product, db


def normalize_category(value):
    normalized = (value or '').strip().lower().replace('_', '-')
    normalized = re.sub(r'\s+', '-', normalized)
    normalized = re.sub(r'-+', '-', normalized)
    return normalized.strip('-')


def main():
    app = create_app()
    with app.app_context():
        products = Product.query.all()
        updated = 0

        for product in products:
            current = (product.category or '').strip()
            if not current:
                continue

            normalized = normalize_category(current)
            if normalized != current:
                product.category = normalized
                updated += 1

        if updated:
            db.session.commit()
            print(f'Normalized category for {updated} product(s).')
        else:
            print('No category updates needed.')


if __name__ == '__main__':
    main()

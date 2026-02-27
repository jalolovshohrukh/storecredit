import os

DATABASE_URL = os.environ.get('DATABASE_URL', '')

COLORS = [
    '#6C63FF', '#FF6B6B', '#4ECDC4', '#45B7D1',
    '#96CEB4', '#F7B731', '#A29BFE', '#FD79A8',
]

CURRENCIES = ['USD', 'EUR', 'UZS', 'RUB', 'GBP', 'CNY', 'KZT', 'TRY', 'JPY', 'AED']

CUR_SYM = {
    'USD': '$', 'EUR': '€', 'UZS': "so'm", 'RUB': '₽',
    'GBP': '£', 'CNY': '¥', 'KZT': '₸', 'TRY': '₺',
    'JPY': '¥', 'AED': 'AED',
}

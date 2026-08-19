import os
from src.executor import Trading212Client
from dotenv import load_dotenv

load_dotenv(override=True)
client = Trading212Client(os.getenv('T212_API_KEY'), os.getenv('T212_API_SECRET'), os.getenv('T212_ENV'))
inst = client.get_instruments()
aapl = [i for i in inst if 'AAPL' in i.get('ticker', '')]
print("Keys available:", list(aapl[0].keys()) if aapl else "None")
print(aapl[0] if aapl else "")

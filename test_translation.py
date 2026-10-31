print("Starting test...")
from deep_translator import GoogleTranslator
print("Imported translator")

# Test simple translation
try:
    print("Testing Tamil translation of 'Fever'...")
    trans = GoogleTranslator(source='en', target='ta')
    result = trans.translate('Fever')
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()


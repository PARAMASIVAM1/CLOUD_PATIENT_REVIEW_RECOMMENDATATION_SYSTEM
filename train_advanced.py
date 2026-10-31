"""
Advanced SBERT Training Script
Better model, better doctor matching, language support
"""

import pandas as pd
import sys
from sbert_model_advanced import (
    train_sbert_model_advanced,
    analyze_feedback_with_language,
    find_best_doctors_for_feedback,
    save_models,
    load_models,
    detect_language,
    translate_to_english,
    translate_to_language,
    LANGUAGE_NAMES
)

def load_dataset(filepath="dataset.xlsx"):
    """Load your dataset"""
    try:
        if filepath.endswith('.xlsx'):
            df = pd.read_excel(filepath)
        elif filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            print(f"❌ Unsupported file format: {filepath}")
            return None
        
        print(f"✅ Dataset loaded: {len(df)} rows")
        print(f"   Columns: {list(df.columns)}")
        return df
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        return None
    except Exception as e:
        print(f"❌ Error loading dataset: {e}")
        return None


def validate_dataset(df):
    """Check if dataset has required columns"""
    required_cols = ['feedback_text', 'sentiment_label', 'complaint_category']
    
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        print(f"\n❌ Missing columns: {missing_cols}")
        print(f"   Available columns: {list(df.columns)}")
        return False
    
    print(f"\n✅ Dataset validation passed")
    print(f"   • Feedback samples: {len(df)}")
    print(f"   • Sentiment classes: {df['sentiment_label'].nunique()}")
    print(f"   • Complaint categories: {df['complaint_category'].nunique()}")
    return True


def main():
    print("\n" + "="*75)
    print("🚀 SBERT Advanced Model Training (bert-base-multilingual-uncased)")
    print("="*75)
    print("Features: Better multilingual support, language detection, doctor matching")
    
    # Step 1: Load dataset
    print("\n📂 Step 1: Loading Dataset...")
    df = load_dataset()
    if df is None:
        return
    
    # Step 2: Validate
    print("\n🔍 Step 2: Validating Dataset...")
    if not validate_dataset(df):
        return
    
    # Step 3: Train SBERT Advanced
    print("\n🎯 Step 3: Training Advanced SBERT Model...")
    print("   (Using bert-base-multilingual-uncased)")
    print("   (Supports 104 languages)")
    print("   (This may take 5-10 minutes on first run)")
    print("-" * 75)
    
    results = train_sbert_model_advanced(df)
    
    print("-" * 75)
    print(f"\n📊 Training Results:")
    print(f"   • Sentiment Accuracy: {results['sentiment_accuracy']:.2%}")
    print(f"   • Complaint Accuracy: {results['complaint_accuracy']:.2%}")
    print(f"   • Total Training Samples: {results['total_samples']}")
    
    # Step 4: Save models
    print("\n💾 Step 4: Saving Models...")
    save_models("sbert_models_advanced.pkl")
    
    # Step 5: Test multilingual support
    print("\n🌍 Step 5: Testing Multilingual Support...")
    test_feedbacks_multi = {
        'English': "The doctor was excellent but the waiting time was very long",
        'Tamil': "மருத்துவர் மிகவும் நல்லவர் ஆனால் காத்திருக்கும் நேரம் நீண்டதாக இருந்தது",
        'Hindi': "डॉक्टर बहुत अच्छे थे लेकिन इंतजार का समय बहुत लंबा था",
    }
    
    print("\nMultilingual Feedback Analysis:")
    for lang_name, feedback in test_feedbacks_multi.items():
        print(f"\n{lang_name}:\n  '{feedback}'")
        analysis = analyze_feedback_with_language(feedback)
        if analysis:
            print(f"  📊 Detected: {analysis['detected_language']}")
            print(f"  😊 Sentiment: {analysis['sentiment']} ({analysis['sentiment_confidence']:.1%})")
            print(f"  🎯 Issue: {analysis['complaint']} ({analysis['complaint_confidence']:.1%})")
    
    # Step 6: Test doctor finding
    print("\n\n🏥 Step 6: Testing Smart Doctor Finding...")
    print("-" * 75)
    
    test_cases = [
        {
            'feedback': "Good treatment but fees are too high",
            'age': 35,
            'fees': 500,
            'location': 'Chennai'
        },
        {
            'feedback': "Doctor was rude, poor behavior",
            'age': 50,
            'location': 'Coimbatore'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest Case {i}:")
        print(f"  Feedback: '{test_case['feedback']}'")
        print(f"  Age: {test_case.get('age', 'Any')}, Fees: Rs {test_case.get('fees', 'Any')}, Location: {test_case.get('location', 'Any')}")
        
        doctors = find_best_doctors_for_feedback(
            df,
            test_case['feedback'],
            age=test_case.get('age'),
            fees=test_case.get('fees'),
            location=test_case.get('location'),
            top_k=3
        )
        
        if doctors:
            print(f"\n  ✅ Found {len(doctors)} matching doctors:")
            for j, doc in enumerate(doctors, 1):
                print(f"\n    {j}. {doc.get('doctor_name', 'N/A')}")
                print(f"       • Rating: {doc.get('average_rating', 'N/A')}/5")
                print(f"       • Specialization: {doc.get('specialization', 'N/A')}")
                print(f"       • Consultation Fee: Rs {doc.get('consultation_fee', 'N/A')}")
                print(f"       • Location: {doc.get('location', 'N/A')}")
                print(f"       • Match Score: {doc.get('match_score', 0):.2f}")
        else:
            print(f"\n  ⚠️  No matching doctors found")
    
    # Step 7: Language translation test
    print("\n\n🌐 Step 7: Testing Language Translation...")
    print("-" * 75)
    
    english_text = "Doctor provided excellent treatment with clear explanation"
    print(f"\nEnglish: {english_text}")
    
    for lang_code, lang_name in [('ta', 'Tamil'), ('hi', 'Hindi'), ('te', 'Telugu')]:
        translated = translate_to_language(english_text, lang_code)
        print(f"{lang_name}: {translated}")
    
    print("\n" + "="*75)
    print("✅ Advanced Training Complete!")
    print("="*75)
    print("\n📝 Key Features:")
    print("   ✨ Better SBERT model (bert-base-multilingual-uncased)")
    print("   🌍 Language detection & translation")
    print("   🏥 Smart doctor finding using semantic matching")
    print("   📊 Multi-criteria filtering (age, fees, location, rating)")
    print("   💡 Sentiment + complaint analysis")
    print("\n📖 Usage in Flask App:")
    print("   from sbert_model_advanced import find_best_doctors_for_feedback")
    print("   doctors = find_best_doctors_for_feedback(df, feedback, age, fees, location)")
    print("\n" + "="*75)


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        sys.exit(1)
    
    # Check dependencies
    print("📦 Checking dependencies...")
    required_packages = {
        'pandas': 'pandas',
        'sentence_transformers': 'sentence-transformers',
        'torch': 'torch',
        'sklearn': 'scikit-learn',
        'langdetect': 'langdetect',
        'googletrans': 'google-trans-new'
    }
    
    missing = []
    for import_name, package_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"   ✅ {package_name}")
        except ImportError:
            print(f"   ❌ {package_name} missing")
            missing.append(package_name)
    
    if missing:
        print(f"\n⚠️  Installing missing packages...")
        import subprocess
        subprocess.run(['pip', 'install'] + missing, check=True)
    
    print("\n✅ All dependencies ready\n")
    main()

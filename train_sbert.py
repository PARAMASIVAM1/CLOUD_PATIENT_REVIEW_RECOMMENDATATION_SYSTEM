"""
SBERT Model Training Script
Run this to train your healthcare feedback model
"""

import pandas as pd
import sys
import os

# Import SBERT model functions
from sbert_model import (
    train_sbert_model,
    analyze_feedback_detailed,
    compare_models,
    get_model_status,
    save_models
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
    print("\n" + "="*70)
    print("🚀 SBERT Healthcare Feedback Model Training")
    print("="*70)
    
    # Step 1: Load dataset
    print("\n📂 Step 1: Loading Dataset...")
    df = load_dataset()
    if df is None:
        return
    
    # Step 2: Validate
    print("\n🔍 Step 2: Validating Dataset...")
    if not validate_dataset(df):
        print("\n💡 Tip: Make sure your dataset has these columns:")
        print("   - feedback_text (patient feedback)")
        print("   - sentiment_label (Positive/Negative/Neutral)")
        print("   - complaint_category (Waiting/Fees/Behaviour/etc)")
        return
    
    # Step 3: Train SBERT
    print("\n🎯 Step 3: Training SBERT Model...")
    print("   (This may take 2-5 minutes on first run)")
    print("   (Progress bar will show below)")
    print("-" * 70)
    
    results = train_sbert_model(df)
    
    print("-" * 70)
    print(f"\n📊 Training Results:")
    print(f"   • Sentiment Accuracy: {results['sentiment_accuracy']:.2%}")
    print(f"   • Complaint Accuracy: {results['complaint_accuracy']:.2%}")
    print(f"   • Total Training Samples: {results['total_samples']}")
    
    # Step 4: Save models
    print("\n💾 Step 4: Saving Models...")
    save_models("sbert_models.pkl")
    
    # Step 5: Test predictions
    print("\n🧪 Step 5: Testing Model Predictions...")
    test_feedbacks = [
        "The doctor was very helpful and explained everything clearly. However, the waiting time was too long.",
        "Great hospital with excellent facilities, but fees are quite expensive.",
        "Treatment quality was good but staff behavior needs improvement."
    ]
    
    print("\nSample Predictions:")
    for i, feedback in enumerate(test_feedbacks, 1):
        print(f"\n{i}. Feedback: '{feedback}'")
        analysis = analyze_feedback_detailed(feedback)
        print(f"   📊 Sentiment: {analysis['sentiment']} ({analysis['sentiment_confidence']:.1%})")
        print(f"   🎯 Issue: {analysis['complaint']} ({analysis['complaint_confidence']:.1%})")
    
    # Step 6: Model comparison
    print("\n\n🔬 Step 6: Model Comparison...")
    compare_models("Doctor was good but waiting time was terrible")
    
    print("\n" + "="*70)
    print("✅ Training Complete!")
    print("="*70)
    print("\n📝 Next Steps:")
    print("   1. Use 'sbert_model.py' functions in your Flask app")
    print("   2. Import: from sbert_model import predict_sentiment_sbert")
    print("   3. Call: sentiment, confidence = predict_sentiment_sbert(text)")
    print("   4. Models auto-loaded from 'sbert_models.pkl'")
    print("\n" + "="*70)


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        sys.exit(1)
    
    # Check required libraries
    print("📦 Checking dependencies...")
    required_packages = {
        'pandas': 'pandas',
        'sentence_transformers': 'sentence-transformers',
        'torch': 'torch',
        'sklearn': 'scikit-learn'
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
        print(f"\n❌ Install missing packages:")
        print(f"   pip install {' '.join(missing)}")
        print(f"\n   Or run:")
        print(f"   pip install sentence-transformers torch scikit-learn pandas numpy")
        sys.exit(1)
    
    print("\n✅ All dependencies installed\n")
    main()

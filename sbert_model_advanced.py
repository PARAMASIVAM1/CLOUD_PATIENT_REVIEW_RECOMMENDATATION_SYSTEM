"""
SBERT Advanced Model with Language Detection & Doctor Matching
Uses bert-base-multilingual-uncased for better multilingual support
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer, util
import torch
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
import pickle
import warnings
from langdetect import detect, DetectorFactory
from googletrans import Translator

warnings.filterwarnings('ignore')
DetectorFactory.seed = 0

# Global variables
sbert_model = None
sentiment_classifier = None
complaint_classifier = None
label_encoder_sentiment = None
label_encoder_complaint = None
feedback_embeddings = None
feedback_data = None
doctor_embeddings = None
doctor_data = None
translator = Translator()

# ==================== CONFIGURATION ====================

LANGUAGE_CODES = {
    'tamil': 'ta',
    'hindi': 'hi',
    'english': 'en',
    'telugu': 'te',
    'kannada': 'kn',
    'malayalam': 'ml'
}

LANGUAGE_NAMES = {
    'ta': 'Tamil',
    'hi': 'Hindi', 
    'en': 'English',
    'te': 'Telugu',
    'kn': 'Kannada',
    'ml': 'Malayalam'
}

# ==================== MAIN FUNCTIONS ====================

def train_sbert_model_advanced(data_df):
    """
    Train advanced SBERT model with better multilingual support
    Uses bert-base-multilingual-uncased (stronger than MiniLM)
    """
    global sbert_model, sentiment_classifier, complaint_classifier
    global label_encoder_sentiment, label_encoder_complaint
    global feedback_embeddings, feedback_data
    
    print("🔄 Loading Advanced SBERT Model (bert-base-multilingual-uncased)...")
    print("   This is more powerful for multilingual healthcare feedback")
    
    try:
        # bert-base-multilingual-uncased is BETTER than MiniLM
        # Supports 104 languages with better accuracy
        sbert_model = SentenceTransformer('bert-base-multilingual-uncased')
        print("✅ Advanced SBERT model loaded successfully")
    except Exception as e:
        print(f"⚠️  Falling back to MiniLM: {e}")
        sbert_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    
    # Prepare data
    texts = data_df["feedback_text"].fillna("").astype(str)
    sentiments = data_df["sentiment_label"].fillna("Neutral")
    complaints = data_df["complaint_category"].fillna("General")
    
    print(f"📊 Training on {len(texts)} multilingual feedback samples...")
    
    # Get embeddings
    print("🔢 Generating SBERT embeddings (multilingual)...")
    feedback_embeddings = sbert_model.encode(
        texts.tolist(), 
        show_progress_bar=True, 
        convert_to_tensor=True,
        batch_size=32
    )
    
    X_embeddings = feedback_embeddings.cpu().numpy()
    
    # Train sentiment classifier
    print("🎯 Training sentiment classifier...")
    label_encoder_sentiment = LabelEncoder()
    y_sentiment = label_encoder_sentiment.fit_transform(sentiments)
    
    sentiment_classifier = LogisticRegression(max_iter=1000, random_state=42, multi_class='multinomial')
    sentiment_classifier.fit(X_embeddings, y_sentiment)
    
    sentiment_accuracy = sentiment_classifier.score(X_embeddings, y_sentiment)
    print(f"✅ Sentiment accuracy: {sentiment_accuracy:.2%}")
    
    # Train complaint classifier
    print("🎯 Training complaint classifier...")
    label_encoder_complaint = LabelEncoder()
    y_complaint = label_encoder_complaint.fit_transform(complaints)
    
    complaint_classifier = LogisticRegression(max_iter=1000, random_state=42, multi_class='multinomial')
    complaint_classifier.fit(X_embeddings, y_complaint)
    
    complaint_accuracy = complaint_classifier.score(X_embeddings, y_complaint)
    print(f"✅ Complaint accuracy: {complaint_accuracy:.2%}")
    
    feedback_data = data_df.copy()
    
    print("\n🎉 SBERT Advanced Model Training Complete!")
    print(f"📈 Sentiment: {sentiment_accuracy:.2%} | Complaint: {complaint_accuracy:.2%}")
    
    return {
        "sentiment_accuracy": sentiment_accuracy,
        "complaint_accuracy": complaint_accuracy,
        "total_samples": len(texts)
    }


def detect_language(text):
    """
    Detect language of input text (multilingual support)
    Returns: language code (en, ta, hi, etc.)
    """
    try:
        lang_code = detect(text)
        return lang_code
    except:
        return 'en'  # Default to English


def translate_to_english(text, source_lang=None):
    """
    Translate text to English for processing
    source_lang: auto-detect if None
    """
    try:
        if source_lang is None:
            source_lang = detect_language(text)
        
        if source_lang == 'en':
            return text
        
        translated = translator.translate(text, src_lang=source_lang, dest_lang='en')
        return translated['text']
    except:
        return text


def translate_to_language(text, target_lang='ta'):
    """
    Translate text to target language (Tamil, Hindi, etc.)
    """
    try:
        if detect_language(text) == target_lang:
            return text
        
        translated = translator.translate(text, dest_lang=target_lang)
        return translated['text']
    except:
        return text


def analyze_feedback_with_language(text, target_language=None):
    """
    Analyze feedback with language detection & translation
    Returns analysis in original + target language if specified
    """
    global sbert_model, sentiment_classifier, complaint_classifier
    
    if sbert_model is None:
        return None
    
    try:
        # Detect source language
        source_lang = detect_language(text)
        
        # Translate to English for processing
        text_en = translate_to_english(text, source_lang)
        
        # Get embeddings
        text_embedding = sbert_model.encode([text_en], convert_to_tensor=True)
        text_embedding_np = text_embedding.cpu().numpy()
        
        # Predict
        sentiment_idx = sentiment_classifier.predict(text_embedding_np)[0]
        sentiment = label_encoder_sentiment.inverse_transform([sentiment_idx])[0]
        sentiment_conf = sentiment_classifier.predict_proba(text_embedding_np)[0].max()
        
        complaint_idx = complaint_classifier.predict(text_embedding_np)[0]
        complaint = label_encoder_complaint.inverse_transform([complaint_idx])[0]
        complaint_conf = complaint_classifier.predict_proba(text_embedding_np)[0].max()
        
        # Translate output if needed
        result = {
            'original_text': text,
            'text_english': text_en,
            'detected_language': LANGUAGE_NAMES.get(source_lang, source_lang),
            'sentiment': sentiment,
            'sentiment_confidence': sentiment_conf,
            'complaint': complaint,
            'complaint_confidence': complaint_conf,
        }
        
        # Add translation to target language if specified
        if target_language and target_language != source_lang:
            result['text_translated'] = translate_to_language(text_en, target_language)
            result['target_language'] = LANGUAGE_NAMES.get(target_language, target_language)
        
        return result
    except Exception as e:
        print(f"Error analyzing feedback: {e}")
        return None


def find_best_doctors_for_feedback(data_df, feedback_text, age=None, fees=None, location=None, top_k=5):
    """
    SMART DOCTOR FINDING using SBERT semantic matching
    Analyzes patient feedback and recommends best matching doctors
    
    Key Features:
    - Semantic matching with patient reviews
    - Complaint-based specialization matching
    - Rating + sentiment matching
    - Multi-criteria filtering
    """
    global sbert_model
    
    if sbert_model is None or data_df is None:
        return []
    
    try:
        # Analyze feedback
        analysis = analyze_feedback_with_language(feedback_text)
        
        if analysis is None:
            return []
        
        complaint = analysis['complaint']
        sentiment = analysis['sentiment']
        
        # Filter doctors by complaint type (specialization)
        complaint_to_specialty = {
            'Waiting': ['General Physician', 'Hospital Manager'],
            'Fees': ['All'],  # Match all if budget issue
            'Behaviour': ['All'],  # Any good doctor
            'Treatment': ['Specialist', 'Doctor'],
            'General': ['General Physician', 'ENT', 'Dermatologist']
        }
        
        specialties = complaint_to_specialty.get(complaint, ['All'])
        
        # Start with all doctors
        candidates = data_df.copy()
        
        # Filter by specialization if complaint-based
        if 'All' not in specialties:
            candidates = candidates[candidates['specialization'].isin(specialties)]
        
        # Filter by age appropriateness
        if age:
            try:
                age_val = int(age)
                # Prefer doctors with experience in that age group
                candidates = candidates[candidates['experience_years'] >= max(1, age_val // 10)]
            except:
                pass
        
        # Filter by fees
        if fees:
            try:
                fees_val = float(fees)
                candidates = candidates[candidates['consultation_fee'] <= fees_val * 1.2]
            except:
                pass
        
        # Filter by location
        if location:
            pattern = rf"\b{re.escape(str(location))}\b"
            candidates = candidates[candidates['location'].astype(str).str.contains(pattern, case=False, regex=True, na=False)]
        
        # Sort by rating + sentiment matching
        if len(candidates) > 0:
            # Semantic similarity with feedback
            feedback_embedding = sbert_model.encode([feedback_text], convert_to_tensor=True)
            
            doctor_reviews = candidates['feedback_text'].fillna("").astype(str).tolist()
            review_embeddings = sbert_model.encode(doctor_reviews, convert_to_tensor=True, show_progress_bar=False)
            
            similarities = util.pytorch_cos_sim(feedback_embedding, review_embeddings)[0]
            candidates['review_similarity'] = similarities.cpu().numpy()
            
            # Score based on: rating (50%) + similarity (30%) + experience (20%)
            candidates['match_score'] = (
                candidates['average_rating'] * 0.5 +
                candidates['review_similarity'] * 30 +  # Scale similarity
                (candidates['experience_years'] / candidates['experience_years'].max()) * 20
            )
            
            # Sort by match score
            candidates = candidates.sort_values('match_score', ascending=False)
        
        return candidates.head(top_k).to_dict('records')
    
    except Exception as e:
        print(f"Error finding doctors: {e}")
        return []


def predict_sentiment_sbert(text):
    """Quick sentiment prediction"""
    analysis = analyze_feedback_with_language(text)
    if analysis:
        return analysis['sentiment'], analysis['sentiment_confidence']
    return "Neutral", 0.0


def predict_complaint_sbert(text):
    """Quick complaint prediction"""
    analysis = analyze_feedback_with_language(text)
    if analysis:
        return analysis['complaint'], analysis['complaint_confidence']
    return "General", 0.0


def save_models(filepath="sbert_models_advanced.pkl"):
    """Save trained models"""
    global sbert_model, sentiment_classifier, complaint_classifier
    global label_encoder_sentiment, label_encoder_complaint
    
    try:
        models = {
            'sentiment_classifier': sentiment_classifier,
            'complaint_classifier': complaint_classifier,
            'label_encoder_sentiment': label_encoder_sentiment,
            'label_encoder_complaint': label_encoder_complaint,
        }
        with open(filepath, 'wb') as f:
            pickle.dump(models, f)
        print(f"✅ Models saved to {filepath}")
    except Exception as e:
        print(f"❌ Error saving models: {e}")


def load_models(filepath="sbert_models_advanced.pkl"):
    """Load trained models with graceful fallback when the model file is missing or unreadable."""
    global sbert_model, sentiment_classifier, complaint_classifier
    global label_encoder_sentiment, label_encoder_complaint

    try:
        sbert_model = SentenceTransformer('bert-base-multilingual-uncased')
    except Exception as e:
        print(f"⚠️  SBERT model could not be initialized: {e}")
        sbert_model = None
        return False

    try:
        with open(filepath, 'rb') as f:
            models = pickle.load(f)
    except FileNotFoundError:
        print(f"⚠️  Model file not found: {filepath}")
        return False
    except (UnicodeDecodeError, EOFError, PermissionError, pickle.PickleError) as e:
        print(f"⚠️  Model file could not be read: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Error loading models: {e}")
        return False

    try:
        sentiment_classifier = models['sentiment_classifier']
        complaint_classifier = models['complaint_classifier']
        label_encoder_sentiment = models['label_encoder_sentiment']
        label_encoder_complaint = models['label_encoder_complaint']
    except KeyError as e:
        print(f"⚠️  Model file is missing expected data: {e}")
        return False

    print(f"✅ Models loaded from {filepath}")
    return True


def get_model_status():
    """Check model status"""
    global sbert_model, sentiment_classifier
    
    if sbert_model is None:
        return "❌ Models not trained"
    if sentiment_classifier is None:
        return "⚠️  Models loading..."
    return "✅ Models ready"


if __name__ == "__main__":
    print("✅ SBERT Advanced Model Module Loaded")

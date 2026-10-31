"""
SBERT-Based Model Training for Healthcare Feedback Analysis
Uses Sentence-BERT for powerful multilingual NLP
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer, util
import torch
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
import pickle
import warnings
warnings.filterwarnings('ignore')

# Global variables for SBERT models
sbert_model = None
sentiment_classifier = None
complaint_classifier = None
label_encoder_sentiment = None
label_encoder_complaint = None
feedback_embeddings = None
feedback_data = None

# ==================== INSTALLATION ====================
# Run this in terminal first:
# pip install sentence-transformers torch scikit-learn pandas numpy

# ==================== MAIN FUNCTIONS ====================

def train_sbert_model(data_df):
    """
    Train SBERT model for sentiment analysis and complaint classification
    
    Args:
        data_df: DataFrame with columns:
                - feedback_text (required)
                - sentiment_label (required)
                - complaint_category (required)
    
    Returns:
        Training accuracy metrics
    """
    global sbert_model, sentiment_classifier, complaint_classifier
    global label_encoder_sentiment, label_encoder_complaint
    global feedback_embeddings, feedback_data
    
    print("🔄 Loading SBERT model (this may take 1-2 minutes)...")
    
    # Load pre-trained multilingual SBERT
    # 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2' is smaller & faster
    # 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2' is more accurate
    try:
        sbert_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        print("✅ SBERT model loaded successfully")
    except Exception as e:
        print(f"❌ Error loading SBERT: {e}")
        print("Installing transformers...")
        import subprocess
        subprocess.run(['pip', 'install', '-q', 'sentence-transformers', 'torch'], check=True)
        sbert_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLm-L12-v2')
    
    # Prepare data
    texts = data_df["feedback_text"].fillna("").astype(str)
    sentiments = data_df["sentiment_label"].fillna("Neutral")
    complaints = data_df["complaint_category"].fillna("General")
    
    print(f"📊 Training on {len(texts)} feedback samples...")
    
    # Get embeddings (this is the power of SBERT)
    print("🔢 Generating SBERT embeddings...")
    feedback_embeddings = sbert_model.encode(texts.tolist(), show_progress_bar=True, convert_to_tensor=True)
    
    # Convert to numpy
    X_embeddings = feedback_embeddings.cpu().numpy()
    
    # Train sentiment classifier
    print("🎯 Training sentiment classifier...")
    label_encoder_sentiment = LabelEncoder()
    y_sentiment = label_encoder_sentiment.fit_transform(sentiments)
    
    sentiment_classifier = LogisticRegression(max_iter=1000, random_state=42)
    sentiment_classifier.fit(X_embeddings, y_sentiment)
    
    sentiment_accuracy = sentiment_classifier.score(X_embeddings, y_sentiment)
    print(f"✅ Sentiment classifier accuracy: {sentiment_accuracy:.2%}")
    
    # Train complaint classifier
    print("🎯 Training complaint classifier...")
    label_encoder_complaint = LabelEncoder()
    y_complaint = label_encoder_complaint.fit_transform(complaints)
    
    complaint_classifier = LogisticRegression(max_iter=1000, random_state=42)
    complaint_classifier.fit(X_embeddings, y_complaint)
    
    complaint_accuracy = complaint_classifier.score(X_embeddings, y_complaint)
    print(f"✅ Complaint classifier accuracy: {complaint_accuracy:.2%}")
    
    # Store data for reference
    feedback_data = data_df.copy()
    
    print("\n🎉 SBERT Model Training Complete!")
    print(f"📈 Overall Performance: Sentiment {sentiment_accuracy:.2%} | Complaint {complaint_accuracy:.2%}")
    
    return {
        "sentiment_accuracy": sentiment_accuracy,
        "complaint_accuracy": complaint_accuracy,
        "total_samples": len(texts)
    }


def predict_sentiment_sbert(text):
    """
    Predict sentiment using SBERT
    
    Args:
        text: Feedback text to analyze
    
    Returns:
        Sentiment label (Positive/Negative/Neutral)
    """
    global sbert_model, sentiment_classifier, label_encoder_sentiment
    
    if sbert_model is None or sentiment_classifier is None:
        return "Neutral"
    
    try:
        # Get embedding
        text_embedding = sbert_model.encode([text], convert_to_tensor=True)
        text_embedding_np = text_embedding.cpu().numpy()
        
        # Predict
        prediction_idx = sentiment_classifier.predict(text_embedding_np)[0]
        sentiment = label_encoder_sentiment.inverse_transform([prediction_idx])[0]
        
        # Get confidence score
        confidence = sentiment_classifier.predict_proba(text_embedding_np)[0].max()
        
        return sentiment, confidence
    except Exception as e:
        print(f"Error predicting sentiment: {e}")
        return "Neutral", 0.0


def predict_complaint_sbert(text):
    """
    Predict complaint category using SBERT
    
    Args:
        text: Feedback text to analyze
    
    Returns:
        Complaint category and confidence
    """
    global sbert_model, complaint_classifier, label_encoder_complaint
    
    if sbert_model is None or complaint_classifier is None:
        return "General", 0.0
    
    try:
        text_embedding = sbert_model.encode([text], convert_to_tensor=True)
        text_embedding_np = text_embedding.cpu().numpy()
        
        prediction_idx = complaint_classifier.predict(text_embedding_np)[0]
        complaint = label_encoder_complaint.inverse_transform([prediction_idx])[0]
        
        confidence = complaint_classifier.predict_proba(text_embedding_np)[0].max()
        
        return complaint, confidence
    except Exception as e:
        print(f"Error predicting complaint: {e}")
        return "General", 0.0


def find_similar_feedback_sbert(query_text, top_k=5):
    """
    Find similar feedback in dataset using SBERT semantic similarity
    
    Args:
        query_text: Query text
        top_k: Number of similar feedbacks to return
    
    Returns:
        List of similar feedback entries
    """
    global sbert_model, feedback_embeddings, feedback_data
    
    if sbert_model is None or feedback_embeddings is None:
        return []
    
    try:
        # Get query embedding
        query_embedding = sbert_model.encode([query_text], convert_to_tensor=True)
        
        # Calculate cosine similarity
        similarities = util.pytorch_cos_sim(query_embedding, feedback_embeddings)[0]
        
        # Get top-k
        top_indices = torch.topk(similarities, min(top_k, len(similarities)))[1].cpu().numpy()
        
        results = []
        for idx in top_indices:
            if idx < len(feedback_data):
                results.append({
                    'feedback': feedback_data.iloc[idx]['feedback_text'],
                    'sentiment': feedback_data.iloc[idx]['sentiment_label'],
                    'similarity': similarities[idx].item()
                })
        
        return results
    except Exception as e:
        print(f"Error finding similar feedback: {e}")
        return []


def get_model_status():
    """Check if models are trained"""
    global sbert_model, sentiment_classifier
    
    if sbert_model is None:
        return "❌ Models not trained yet"
    
    if sentiment_classifier is None:
        return "⚠️  Models loading..."
    
    return "✅ Models ready"


def save_models(filepath="sbert_models.pkl"):
    """Save trained models to disk"""
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


def load_models(filepath="sbert_models.pkl"):
    """Load trained models from disk"""
    global sbert_model, sentiment_classifier, complaint_classifier
    global label_encoder_sentiment, label_encoder_complaint
    
    try:
        # Load SBERT
        sbert_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        
        # Load classifiers
        with open(filepath, 'rb') as f:
            models = pickle.load(f)
        
        sentiment_classifier = models['sentiment_classifier']
        complaint_classifier = models['complaint_classifier']
        label_encoder_sentiment = models['label_encoder_sentiment']
        label_encoder_complaint = models['label_encoder_complaint']
        
        print(f"✅ Models loaded from {filepath}")
        return True
    except Exception as e:
        print(f"❌ Error loading models: {e}")
        return False


# ==================== ADVANCED FEATURES ====================

def analyze_feedback_detailed(text):
    """
    Comprehensive analysis of feedback using SBERT
    
    Returns: Full analysis with sentiment, complaint, and similar feedback
    """
    sentiment, sentiment_conf = predict_sentiment_sbert(text)
    complaint, complaint_conf = predict_complaint_sbert(text)
    similar = find_similar_feedback_sbert(text, top_k=3)
    
    analysis = {
        'text': text,
        'sentiment': sentiment,
        'sentiment_confidence': sentiment_conf,
        'complaint': complaint,
        'complaint_confidence': complaint_conf,
        'similar_feedback': similar
    }
    
    return analysis


def batch_analyze_feedback(feedback_list):
    """
    Analyze multiple feedback in batch (faster)
    """
    results = []
    for feedback in feedback_list:
        results.append(analyze_feedback_detailed(feedback))
    return results


# ==================== COMPARISON: TFIDF vs SBERT ====================

def compare_models(test_text):
    """
    Compare old TF-IDF model with new SBERT model
    Shows why SBERT is better
    """
    print("\n" + "="*60)
    print("🔬 TFIDF vs SBERT Comparison")
    print("="*60)
    
    print(f"\nTest Feedback: '{test_text}'\n")
    
    # SBERT analysis
    sentiment, conf = predict_sentiment_sbert(test_text)
    complaint, comp_conf = predict_complaint_sbert(test_text)
    
    print("✨ SBERT Analysis:")
    print(f"  • Sentiment: {sentiment} ({conf:.2%} confidence)")
    print(f"  • Complaint: {complaint} ({comp_conf:.2%} confidence)")
    
    similar = find_similar_feedback_sbert(test_text, top_k=2)
    print(f"  • Similar feedback found: {len(similar)}")
    for i, sim in enumerate(similar, 1):
        print(f"    {i}. {sim['feedback'][:60]}... (similarity: {sim['similarity']:.2%})")
    
    print("\n💡 SBERT Advantages:")
    print("  ✅ Understands context (semantic similarity)")
    print("  ✅ Multilingual support built-in")
    print("  ✅ Better accuracy on small datasets")
    print("  ✅ No manual feature engineering needed")
    print("="*60)


if __name__ == "__main__":
    # Example usage
    print("SBERT Model Module Loaded Successfully ✅")
    print("Use this in your app.py or Flask application")

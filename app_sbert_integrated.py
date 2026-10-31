"""
SBERT Integration into Flask App
Copy-paste this into your app.py or create a new integrated version
"""

from flask import Flask, render_template, request, jsonify
import pandas as pd
from sbert_model import (
    train_sbert_model,
    predict_sentiment_sbert,
    predict_complaint_sbert,
    analyze_feedback_detailed,
    find_similar_feedback_sbert,
    load_models,
    save_models,
    get_model_status
)

app = Flask(__name__)

# ==================== INITIALIZATION ====================

# Try to load existing models, if not found, will train on first request
try:
    load_models("sbert_models.pkl")
    print("✅ SBERT Models loaded from disk")
except:
    print("⚠️  Models not found, will train on first startup")

# Load dataset once
DATA_DF = None

def load_data():
    global DATA_DF
    try:
        DATA_DF = pd.read_excel("dataset.xlsx")
        print(f"✅ Dataset loaded: {len(DATA_DF)} rows")
        return True
    except:
        try:
            DATA_DF = pd.read_csv("dataset.csv")
            print(f"✅ Dataset loaded from CSV: {len(DATA_DF)} rows")
            return True
        except Exception as e:
            print(f"❌ Error loading dataset: {e}")
            return False

# ==================== ROUTES ====================

@app.route('/')
def home():
    """Home page"""
    status = get_model_status()
    return render_template('home.html', model_status=status)


@app.route('/api/model-status')
def model_status():
    """Get current model status"""
    return jsonify({'status': get_model_status()})


@app.route('/api/analyze-feedback', methods=['POST'])
def analyze_feedback():
    """
    Analyze user feedback using SBERT
    
    Input JSON: {'feedback': 'patient feedback text'}
    Output: sentiment, complaint, confidence, similar feedback
    """
    try:
        data = request.get_json()
        feedback = data.get('feedback', '').strip()
        
        if not feedback:
            return jsonify({'error': 'No feedback provided'}), 400
        
        # Perform analysis
        analysis = analyze_feedback_detailed(feedback)
        
        return jsonify({
            'success': True,
            'feedback': feedback,
            'sentiment': analysis['sentiment'],
            'sentiment_confidence': round(analysis['sentiment_confidence'], 3),
            'complaint': analysis['complaint'],
            'complaint_confidence': round(analysis['complaint_confidence'], 3),
            'similar_count': len(analysis['similar_feedback']),
            'similar_feedback': analysis['similar_feedback']
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/predict-sentiment', methods=['POST'])
def predict_sentiment():
    """Quick sentiment prediction only"""
    try:
        data = request.get_json()
        feedback = data.get('feedback', '')
        sentiment, confidence = predict_sentiment_sbert(feedback)
        
        return jsonify({
            'sentiment': sentiment,
            'confidence': round(confidence, 3)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/predict-complaint', methods=['POST'])
def predict_complaint():
    """Quick complaint prediction only"""
    try:
        data = request.get_json()
        feedback = data.get('feedback', '')
        complaint, confidence = predict_complaint_sbert(feedback)
        
        return jsonify({
            'complaint': complaint,
            'confidence': round(confidence, 3)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/find-similar', methods=['POST'])
def find_similar():
    """Find similar feedback in dataset"""
    try:
        data = request.get_json()
        query = data.get('query', '')
        top_k = data.get('top_k', 5)
        
        similar = find_similar_feedback_sbert(query, top_k=top_k)
        
        return jsonify({
            'query': query,
            'similar_count': len(similar),
            'similar_feedback': similar
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/train-model', methods=['POST'])
def retrain_model():
    """
    Retrain SBERT model on current dataset
    Call this if you update your dataset
    """
    try:
        if DATA_DF is None:
            load_data()
        
        if DATA_DF is None:
            return jsonify({'error': 'Dataset not loaded'}), 400
        
        print("🔄 Retraining SBERT model...")
        results = train_sbert_model(DATA_DF)
        save_models("sbert_models.pkl")
        
        return jsonify({
            'success': True,
            'message': 'Model trained successfully',
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/batch-analyze', methods=['POST'])
def batch_analyze():
    """Analyze multiple feedbacks at once"""
    try:
        data = request.get_json()
        feedbacks = data.get('feedbacks', [])
        
        if not feedbacks:
            return jsonify({'error': 'No feedbacks provided'}), 400
        
        results = []
        for feedback in feedbacks:
            analysis = analyze_feedback_detailed(feedback)
            results.append({
                'feedback': feedback,
                'sentiment': analysis['sentiment'],
                'sentiment_confidence': round(analysis['sentiment_confidence'], 3),
                'complaint': analysis['complaint'],
                'complaint_confidence': round(analysis['complaint_confidence'], 3)
            })
        
        return jsonify({
            'success': True,
            'count': len(results),
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== FOR DOCTOR RECOMMENDATION ====================

@app.route('/api/recommend-doctor', methods=['POST'])
def recommend_doctor():
    """
    Recommend best doctor based on feedback analysis
    Uses sentiment + complaint to match with doctor specialties
    """
    try:
        data = request.get_json()
        feedback = data.get('feedback', '')
        
        if not DATA_DF is not None:
            load_data()
        
        # Analyze feedback
        analysis = analyze_feedback_detailed(feedback)
        sentiment = analysis['sentiment']
        complaint = analysis['complaint']
        
        # Filter doctors based on complaint
        doctors = DATA_DF[DATA_DF['complaint_category'].str.contains(complaint, case=False, na=False)]
        
        # Prioritize positive feedback doctors
        if sentiment == 'Positive':
            doctors = doctors.nlargest(5, 'rating_1_to_5')
        else:
            doctors = doctors.nlargest(10, 'rating_1_to_5').head(5)
        
        recommendations = doctors.to_dict('records') if len(doctors) > 0 else []
        
        return jsonify({
            'success': True,
            'feedback_analysis': {
                'sentiment': sentiment,
                'complaint': complaint
            },
            'recommended_doctors': recommendations[:5]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== DATABASE/STATS ====================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get dataset statistics"""
    try:
        if DATA_DF is None:
            load_data()
        
        if DATA_DF is None:
            return jsonify({'error': 'Dataset not loaded'}), 400
        
        stats = {
            'total_feedbacks': len(DATA_DF),
            'sentiment_distribution': DATA_DF['sentiment_label'].value_counts().to_dict(),
            'complaint_distribution': DATA_DF['complaint_category'].value_counts().to_dict(),
            'average_rating': float(DATA_DF['rating_1_to_5'].mean()) if 'rating_1_to_5' in DATA_DF.columns else 0,
            'model_status': get_model_status()
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== STARTUP ====================

if __name__ == '__main__':
    print("🚀 Starting Healthcare Feedback SBERT Application...")
    
    # Load dataset
    if not load_data():
        print("⚠️  Dataset loading failed - app will train on first use")
    else:
        # Train models if not exists
        try:
            train_sbert_model(DATA_DF)
            save_models("sbert_models.pkl")
            print("✅ SBERT Models trained successfully")
        except Exception as e:
            print(f"⚠️  Error during training: {e}")
    
    print("✅ Application ready!")
    print("📊 Available endpoints:")
    print("   POST /api/analyze-feedback - Analyze patient feedback")
    print("   POST /api/predict-sentiment - Predict sentiment only")
    print("   POST /api/predict-complaint - Predict complaint only")
    print("   POST /api/find-similar - Find similar feedback")
    print("   POST /api/batch-analyze - Analyze multiple feedbacks")
    print("   POST /api/recommend-doctor - Get doctor recommendations")
    print("   GET  /api/stats - Get dataset statistics")
    print("\n🌐 Open: http://localhost:5000")
    
    app.run(debug=True, port=5000)

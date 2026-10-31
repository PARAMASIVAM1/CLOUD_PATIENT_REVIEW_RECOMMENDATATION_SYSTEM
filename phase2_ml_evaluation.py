import argparse
import json
import os
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
import torch
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score,
                             precision_recall_fscore_support)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.preprocessing import OneHotEncoder, StandardScaler, MinMaxScaler, LabelEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.utils.class_weight import compute_class_weight
from transformers import AutoModel, AutoTokenizer, logging as hf_logging


warnings.filterwarnings("ignore")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
hf_logging.set_verbosity_error()
tf.get_logger().setLevel("ERROR")


def build_feature_pipeline(text_col, numeric_cols, categorical_cols, numeric_scaler):
    text_pipe = FeatureUnion(
        transformer_list=[
            (
                "word_tfidf",
                TfidfVectorizer(
                    max_features=20000,
                    ngram_range=(1, 2),
                    min_df=2,
                    sublinear_tf=True,
                ),
            ),
            (
                "char_tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=2,
                    max_features=10000,
                ),
            ),
        ]
    )

    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", numeric_scaler),
        ]
    )

    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("text", text_pipe, text_col),
            ("num", numeric_pipe, numeric_cols),
            ("cat", categorical_pipe, categorical_cols),
        ],
        remainder="drop",
    )

    return preprocessor


def evaluate_model(name, model, X_train, X_test, y_train, y_test, cv, preprocessor):
    pipeline = Pipeline(steps=[("prep", preprocessor), ("model", model)])

    pipeline.fit(X_train, y_train)
    y_train_pred = pipeline.predict(X_train)
    y_pred = pipeline.predict(X_test)

    train_acc = accuracy_score(y_train, y_train_pred)
    train_precision, train_recall, train_f1, _ = precision_recall_fscore_support(
        y_train, y_train_pred, average="weighted", zero_division=0
    )

    acc = accuracy_score(y_test, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="weighted", zero_division=0
    )

    cv_scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="accuracy")
    return {
        "model": name,
        "train_accuracy": train_acc,
        "train_precision": train_precision,
        "train_recall": train_recall,
        "train_f1": train_f1,
        "test_accuracy": acc,
        "test_precision": precision,
        "test_recall": recall,
        "test_f1": f1,
        "cv_mean": float(np.mean(cv_scores)),
        "cv_std": float(np.std(cv_scores)),
    }, y_pred, pipeline


def plot_bar(results_df, out_path):
    metrics = ["test_accuracy", "test_precision", "test_recall", "test_f1"]
    ax = results_df.set_index("model")[metrics].plot(kind="bar", figsize=(10, 5))
    ax.set_ylim(0, 1)
    ax.set_title("Model Performance Comparison")
    ax.set_ylabel("Score")
    ax.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_confusion_matrix(y_test, y_pred, out_path, title):
    disp = ConfusionMatrixDisplay.from_predictions(y_test, y_pred)
    disp.ax_.set_title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def _print_results_table(results_df):
    display_cols = [
        "model",
        "train_accuracy",
        "train_precision",
        "train_recall",
        "train_f1",
        "test_accuracy",
        "test_precision",
        "test_recall",
        "test_f1",
        "cv_mean",
        "cv_std",
    ]
    table_df = results_df[display_cols].copy()
    print("\nModel Evaluation Metrics (Tabular)")
    print(table_df.to_string(index=False))


def _print_test_table(results_df):
    display_cols = [
        "model",
        "test_accuracy",
        "test_precision",
        "test_recall",
        "test_f1",
        "cv_mean",
        "cv_std",
    ]
    table_df = results_df[display_cols].copy()
    # Keep NaN out of the console table for models without CV metrics.
    table_df["cv_mean"] = table_df["cv_mean"].fillna("-")
    table_df["cv_std"] = table_df["cv_std"].fillna("-")
    print("\nTest Metrics Only (Tabular)")
    print(table_df.to_string(index=False))


def _compute_metrics(y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )
    return acc, precision, recall, f1


def _compute_class_weight(labels):
    classes = np.unique(labels)
    if len(classes) == 0:
        return None
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=labels)
    return dict(zip(classes, weights))


def _light_dataset_cleanup(df, text_col, target_col, min_class_count=2):
    df[text_col] = df[text_col].astype(str).str.strip()
    df[target_col] = df[target_col].astype(str).str.strip()

    df = df[df[text_col].str.len() > 0]
    df = df.drop_duplicates(subset=[text_col, target_col])

    value_counts = df[target_col].value_counts()
    keep_labels = value_counts[value_counts >= min_class_count].index
    df = df[df[target_col].isin(keep_labels)]
    return df


def _clean_text_basic(series):
    cleaned = series.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    return cleaned


def _filter_low_quality_text(df, text_col, min_text_len=20):
    df = df[df[text_col].str.len() >= min_text_len]

    # Remove very low-information texts (few unique tokens)
    token_counts = df[text_col].str.lower().str.split().apply(lambda x: len(set(x)) if x else 0)
    df = df[token_counts >= 5]

    # Filter generic praise/complaint without details
    generic_patterns = r"\b(good|nice|ok|okay|excellent|bad|average|fine|great|poor)\b$"
    generic_only = df[text_col].str.lower().str.match(generic_patterns)
    df = df[~generic_only]

    return df


def _load_dataset(path):
    if path.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(path)
    return pd.read_csv(path)


def _prepare_text_label(df, text_col, target_col):
    text_series = None
    if "review_english" in df.columns:
        text_series = df["review_english"]
    elif text_col in df.columns:
        text_series = df[text_col]

    label_series = None
    if "sentiment" in df.columns:
        label_series = df["sentiment"]
    elif target_col in df.columns:
        label_series = df[target_col]

    if text_series is None or label_series is None:
        raise ValueError("No usable text/label columns found in dataset.")

    df = df.copy()
    df["final_text"] = text_series
    df["final_label"] = label_series
    return df, "final_text", "final_label"


def _normalize_and_balance(
    df,
    text_col,
    target_col,
    min_text_len=20,
    drop_duplicates=False,
    max_per_class=None,
    upsample=False,
):
    df[text_col] = _clean_text_basic(df[text_col])
    df[target_col] = df[target_col].astype(str).str.strip()

    df = _filter_low_quality_text(df, text_col, min_text_len=min_text_len)
    df = df[df[target_col].isin(["Positive", "Negative", "Neutral"])]

    # Remove obvious leakage like label words in text
    leakage_mask = df[text_col].str.contains(r"\b(positive|negative|neutral)\b", case=False, na=False)
    df = df[~leakage_mask]

    if drop_duplicates:
        df = df.drop_duplicates(subset=[text_col, target_col])

    class_counts = df[target_col].value_counts()
    if class_counts.empty:
        return df

    if upsample:
        max_count = int(class_counts.max())
        if max_per_class is not None:
            max_count = min(max_count, int(max_per_class))

        balanced_parts = []
        for label, group in df.groupby(target_col):
            target_count = max_count
            if len(group) < target_count:
                group = group.sample(target_count, replace=True, random_state=42)
            else:
                group = group.sample(target_count, random_state=42)
            balanced_parts.append(group)
        return pd.concat(balanced_parts, ignore_index=True)

    min_count = int(class_counts.min())
    per_class = min_count
    if max_per_class is not None:
        per_class = min(per_class, int(max_per_class))

    balanced = (
        df.groupby(target_col, group_keys=False)
        .apply(lambda x: x.sample(per_class, random_state=42))
        .reset_index(drop=True)
    )
    return balanced


def _embed_transformer(texts, model_name, batch_size=16):
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        encoded = tokenizer(batch_texts, padding=True, truncation=True, return_tensors="pt")
        with torch.no_grad():
            outputs = model(**encoded)
        batch_emb = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        all_embeddings.append(batch_emb)
    return np.vstack(all_embeddings)


def _keras_cv_score(
    texts,
    labels,
    build_model_fn,
    n_splits=3,
    epochs=3,
    batch_size=32,
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=("accuracy",),
):
    labels = np.asarray(labels)
    class_counts = np.bincount(labels)
    min_class_count = int(class_counts.min()) if len(class_counts) else 0
    if min_class_count < 2:
        return None, None

    n_splits = min(n_splits, min_class_count)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scores = []

    for train_idx, val_idx in skf.split(texts, labels):
        X_train = np.array([texts[i] for i in train_idx], dtype=object)
        X_val = np.array([texts[i] for i in val_idx], dtype=object)
        y_train = labels[train_idx]
        y_val = labels[val_idx]

        vectorizer = tf.keras.layers.TextVectorization(
            max_tokens=5000,
            output_mode="int",
            output_sequence_length=80,
        )
        vectorizer.adapt(X_train)

        model = build_model_fn(vectorizer)
        model.compile(optimizer=optimizer, loss=loss, metrics=list(metrics))
        model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size, verbose=0)
        preds = np.argmax(model.predict(X_val, verbose=0), axis=1)
        scores.append(accuracy_score(y_val, preds))

    return float(np.mean(scores)), float(np.std(scores))


def _keras_mlp_cv_score(
    texts,
    labels,
    n_splits=3,
    epochs=5,
    batch_size=32,
):
    labels = np.asarray(labels)
    class_counts = np.bincount(labels)
    min_class_count = int(class_counts.min()) if len(class_counts) else 0
    if min_class_count < 2:
        return None, None

    n_splits = min(n_splits, min_class_count)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scores = []

    for train_idx, val_idx in skf.split(texts, labels):
        X_train = np.array([texts[i] for i in train_idx], dtype=object)
        X_val = np.array([texts[i] for i in val_idx], dtype=object)
        y_train = labels[train_idx]
        y_val = labels[val_idx]

        vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
        X_train_vec = vectorizer.fit_transform(X_train).toarray()
        X_val_vec = vectorizer.transform(X_val).toarray()

        num_classes = int(len(np.unique(labels)))
        model = tf.keras.Sequential(
            [
                tf.keras.layers.Input(shape=(X_train_vec.shape[1],)),
                tf.keras.layers.Dense(256, activation="relu"),
                tf.keras.layers.Dropout(0.3),
                tf.keras.layers.Dense(128, activation="relu"),
                tf.keras.layers.Dense(num_classes, activation="softmax"),
            ]
        )
        model.compile(
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        model.fit(
            X_train_vec,
            y_train,
            epochs=epochs,
            batch_size=batch_size,
            verbose=0,
            callbacks=[tf.keras.callbacks.EarlyStopping(patience=2, restore_best_weights=True)],
        )

        preds = np.argmax(model.predict(X_val_vec, verbose=0), axis=1)
        scores.append(accuracy_score(y_val, preds))

    return float(np.mean(scores)), float(np.std(scores))


def try_sbert(texts, labels, output_dir):
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.linear_model import LogisticRegression

        model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        embeddings = model.encode(texts, show_progress_bar=False)

        le = LabelEncoder()
        y = le.fit_transform(labels)
        X_train, X_test, y_train, y_test = train_test_split(
            embeddings, y, test_size=0.2, random_state=42, stratify=y
        )
        clf = LogisticRegression(max_iter=2000, solver="saga", n_jobs=-1, class_weight="balanced")
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        train_acc, train_precision, train_recall, train_f1 = _compute_metrics(
            y_train, clf.predict(X_train)
        )
        acc, precision, recall, f1 = _compute_metrics(y_test, preds)

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(clf, embeddings, y, cv=cv, scoring="accuracy")

        plot_confusion_matrix(
            y_test,
            preds,
            output_dir / "confusion_matrix_sbert.png",
            "SBERT Confusion Matrix",
        )

        return {
            "model": "SBERT + Logistic Regression",
            "train_accuracy": train_acc,
            "train_precision": train_precision,
            "train_recall": train_recall,
            "train_f1": train_f1,
            "test_accuracy": acc,
            "test_precision": precision,
            "test_recall": recall,
            "test_f1": f1,
            "cv_mean": float(np.mean(cv_scores)),
            "cv_std": float(np.std(cv_scores)),
        }
    except Exception:
        return {
            "model": "SBERT + Logistic Regression",
            "train_accuracy": None,
            "train_precision": None,
            "train_recall": None,
            "train_f1": None,
            "test_accuracy": None,
            "test_precision": None,
            "test_recall": None,
            "test_f1": None,
            "cv_mean": None,
            "cv_std": None,
        }


def try_bert(texts, labels, output_dir):
    try:
        le = LabelEncoder()
        y = le.fit_transform(labels)

        embeddings = _embed_transformer(texts, "distilbert-base-multilingual-cased")

        X_train_emb, X_test_emb, y_train, y_test = train_test_split(
            embeddings,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y,
        )

        clf = LogisticRegression(max_iter=2000, solver="saga", n_jobs=-1, class_weight="balanced")
        clf.fit(X_train_emb, y_train)
        preds = clf.predict(X_test_emb)

        train_acc, train_precision, train_recall, train_f1 = _compute_metrics(
            y_train, clf.predict(X_train_emb)
        )
        acc, precision, recall, f1 = _compute_metrics(y_test, preds)

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(clf, embeddings, y, cv=cv, scoring="accuracy")

        plot_confusion_matrix(
            y_test,
            preds,
            output_dir / "confusion_matrix_bert.png",
            "BERT Confusion Matrix",
        )

        return {
            "model": "BERT + Logistic Regression",
            "train_accuracy": train_acc,
            "train_precision": train_precision,
            "train_recall": train_recall,
            "train_f1": train_f1,
            "test_accuracy": acc,
            "test_precision": precision,
            "test_recall": recall,
            "test_f1": f1,
            "cv_mean": float(np.mean(cv_scores)),
            "cv_std": float(np.std(cv_scores)),
        }
    except Exception:
        return {
            "model": "BERT + Logistic Regression",
            "train_accuracy": None,
            "train_precision": None,
            "train_recall": None,
            "train_f1": None,
            "test_accuracy": None,
            "test_precision": None,
            "test_recall": None,
            "test_f1": None,
            "cv_mean": None,
            "cv_std": None,
        }


def try_keras_mlp(texts, labels):
    le = LabelEncoder()
    y = le.fit_transform(labels)
    num_classes = len(le.classes_)
    class_weight = _compute_class_weight(y)

    X_train, X_test, y_train, y_test = train_test_split(
        texts, y, test_size=0.2, random_state=42, stratify=y
    )

    vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    X_train_vec = vectorizer.fit_transform(X_train).toarray()
    X_test_vec = vectorizer.transform(X_test).toarray()

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(X_train_vec.shape[1],)),
            tf.keras.layers.Dense(256, activation="relu"),
            tf.keras.layers.Dropout(0.3),
            tf.keras.layers.Dense(128, activation="relu"),
            tf.keras.layers.Dense(num_classes, activation="softmax"),
        ]
    )
    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.fit(
        X_train_vec,
        y_train,
        epochs=20,
        batch_size=32,
        verbose=0,
        validation_split=0.1,
        class_weight=class_weight,
        callbacks=[tf.keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True)],
    )

    train_preds = np.argmax(model.predict(X_train_vec, verbose=0), axis=1)
    test_preds = np.argmax(model.predict(X_test_vec, verbose=0), axis=1)

    train_acc, train_precision, train_recall, train_f1 = _compute_metrics(y_train, train_preds)
    acc, precision, recall, f1 = _compute_metrics(y_test, test_preds)

    cv_mean, cv_std = _keras_mlp_cv_score(
        list(texts),
        y,
        n_splits=3,
        epochs=5,
        batch_size=32,
    )

    return {
        "model": "ANN (Keras MLP)",
        "train_accuracy": train_acc,
        "train_precision": train_precision,
        "train_recall": train_recall,
        "train_f1": train_f1,
        "test_accuracy": acc,
        "test_precision": precision,
        "test_recall": recall,
        "test_f1": f1,
        "cv_mean": cv_mean,
        "cv_std": cv_std,
    }


def try_keras_cnn(texts, labels):
    try:
        le = LabelEncoder()
        y = le.fit_transform(labels)
        num_classes = len(le.classes_)
        class_weight = _compute_class_weight(y)

        X_train, X_test, y_train, y_test = train_test_split(
            texts, y, test_size=0.2, random_state=42, stratify=y
        )
        X_train = np.array(X_train, dtype=object)
        X_test = np.array(X_test, dtype=object)

        def _build_cnn_model(vectorizer):
            return tf.keras.Sequential(
                [
                    vectorizer,
                    tf.keras.layers.Embedding(5000, 128),
                    tf.keras.layers.Conv1D(128, 5, activation="relu"),
                    tf.keras.layers.GlobalMaxPooling1D(),
                    tf.keras.layers.Dense(64, activation="relu"),
                    tf.keras.layers.Dense(num_classes, activation="softmax"),
                ]
            )

        vectorizer = tf.keras.layers.TextVectorization(
            max_tokens=5000,
            output_mode="int",
            output_sequence_length=80,
        )
        vectorizer.adapt(X_train)

        model = _build_cnn_model(vectorizer)
        model.compile(
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        model.fit(
            X_train,
            y_train,
            epochs=20,
            batch_size=32,
            verbose=0,
            validation_split=0.1,
            class_weight=class_weight,
            callbacks=[tf.keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True)],
        )

        train_preds = np.argmax(model.predict(X_train, verbose=0), axis=1)
        test_preds = np.argmax(model.predict(X_test, verbose=0), axis=1)

        train_acc, train_precision, train_recall, train_f1 = _compute_metrics(y_train, train_preds)
        acc, precision, recall, f1 = _compute_metrics(y_test, test_preds)

        cv_mean, cv_std = _keras_cv_score(
            list(texts),
            y,
            _build_cnn_model,
            n_splits=3,
            epochs=3,
            batch_size=32,
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=("accuracy",),
        )

        return {
            "model": "CNN (Keras Conv1D)",
            "train_accuracy": train_acc,
            "train_precision": train_precision,
            "train_recall": train_recall,
            "train_f1": train_f1,
            "test_accuracy": acc,
            "test_precision": precision,
            "test_recall": recall,
            "test_f1": f1,
            "cv_mean": cv_mean,
            "cv_std": cv_std,
        }
    except Exception as exc:
        print(f"[WARN] CNN evaluation failed: {exc}")
        return {
            "model": "CNN (Keras Conv1D)",
            "train_accuracy": None,
            "train_precision": None,
            "train_recall": None,
            "train_f1": None,
            "test_accuracy": None,
            "test_precision": None,
            "test_recall": None,
            "test_f1": None,
            "cv_mean": None,
            "cv_std": None,
        }


def try_roberta(texts, labels, output_dir):
    try:
        le = LabelEncoder()
        y = le.fit_transform(labels)

        embeddings = _embed_transformer(texts, "xlm-roberta-base")

        X_train_emb, X_test_emb, y_train, y_test = train_test_split(
            embeddings,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y,
        )

        clf = LogisticRegression(max_iter=2000, solver="saga", n_jobs=-1, class_weight="balanced")
        clf.fit(X_train_emb, y_train)
        preds = clf.predict(X_test_emb)

        train_acc, train_precision, train_recall, train_f1 = _compute_metrics(
            y_train, clf.predict(X_train_emb)
        )
        acc, precision, recall, f1 = _compute_metrics(y_test, preds)

        plot_confusion_matrix(
            y_test,
            preds,
            output_dir / "confusion_matrix_roberta.png",
            "RoBERTa Confusion Matrix",
        )

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(clf, embeddings, y, cv=cv, scoring="accuracy")

        return {
            "model": "RoBERTa + Logistic Regression",
            "train_accuracy": train_acc,
            "train_precision": train_precision,
            "train_recall": train_recall,
            "train_f1": train_f1,
            "test_accuracy": acc,
            "test_precision": precision,
            "test_recall": recall,
            "test_f1": f1,
            "cv_mean": float(np.mean(cv_scores)),
            "cv_std": float(np.std(cv_scores)),
        }
    except Exception:
        return {
            "model": "RoBERTa + Logistic Regression",
            "train_accuracy": None,
            "train_precision": None,
            "train_recall": None,
            "train_f1": None,
            "test_accuracy": None,
            "test_precision": None,
            "test_recall": None,
            "test_f1": None,
            "cv_mean": None,
            "cv_std": None,
        }


def try_keras_lstm(texts, labels):
    try:
        le = LabelEncoder()
        y = le.fit_transform(labels)
        num_classes = len(le.classes_)
        class_weight = _compute_class_weight(y)

        X_train, X_test, y_train, y_test = train_test_split(
            texts, y, test_size=0.2, random_state=42, stratify=y
        )
        X_train = np.array(X_train, dtype=object)
        X_test = np.array(X_test, dtype=object)

        def _build_lstm_model(vectorizer):
            return tf.keras.Sequential(
                [
                    vectorizer,
                    tf.keras.layers.Embedding(5000, 128),
                    tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(64)),
                    tf.keras.layers.Dense(64, activation="relu"),
                    tf.keras.layers.Dense(num_classes, activation="softmax"),
                ]
            )

        vectorizer = tf.keras.layers.TextVectorization(
            max_tokens=5000,
            output_mode="int",
            output_sequence_length=80,
        )
        vectorizer.adapt(X_train)

        model = _build_lstm_model(vectorizer)
        model.compile(
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        model.fit(
            X_train,
            y_train,
            epochs=20,
            batch_size=32,
            verbose=0,
            validation_split=0.1,
            class_weight=class_weight,
            callbacks=[tf.keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True)],
        )

        train_preds = np.argmax(model.predict(X_train, verbose=0), axis=1)
        test_preds = np.argmax(model.predict(X_test, verbose=0), axis=1)

        train_acc, train_precision, train_recall, train_f1 = _compute_metrics(y_train, train_preds)
        acc, precision, recall, f1 = _compute_metrics(y_test, test_preds)

        cv_mean, cv_std = _keras_cv_score(
            list(texts),
            y,
            _build_lstm_model,
            n_splits=3,
            epochs=3,
            batch_size=32,
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=("accuracy",),
        )

        return {
            "model": "LSTM (Keras)",
            "train_accuracy": train_acc,
            "train_precision": train_precision,
            "train_recall": train_recall,
            "train_f1": train_f1,
            "test_accuracy": acc,
            "test_precision": precision,
            "test_recall": recall,
            "test_f1": f1,
            "cv_mean": cv_mean,
            "cv_std": cv_std,
        }
    except Exception as exc:
        print(f"[WARN] LSTM evaluation failed: {exc}")
        return {
            "model": "LSTM (Keras)",
            "train_accuracy": None,
            "train_precision": None,
            "train_recall": None,
            "train_f1": None,
            "test_accuracy": None,
            "test_precision": None,
            "test_recall": None,
            "test_f1": None,
            "cv_mean": None,
            "cv_std": None,
        }


def try_finetune_transformer(texts, labels, model_name, output_dir):
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
        from torch.utils.data import Dataset

        le = LabelEncoder()
        y = le.fit_transform(labels)

        X_train, X_test, y_train, y_test = train_test_split(
            texts, y, test_size=0.2, random_state=42, stratify=y
        )

        tokenizer = AutoTokenizer.from_pretrained(model_name)

        class TextDataset(Dataset):
            def __init__(self, texts, labels):
                self.encodings = tokenizer(texts, truncation=True, padding=True, max_length=128)
                self.labels = labels

            def __len__(self):
                return len(self.labels)

            def __getitem__(self, idx):
                item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
                item["labels"] = torch.tensor(self.labels[idx])
                return item

        train_dataset = TextDataset(list(X_train), list(y_train))
        test_dataset = TextDataset(list(X_test), list(y_test))

        model = AutoModelForSequenceClassification.from_pretrained(
            model_name, num_labels=len(le.classes_)
        )

        training_args = TrainingArguments(
            output_dir=str(output_dir / "finetune"),
            num_train_epochs=5,
            per_device_train_batch_size=8,
            per_device_eval_batch_size=8,
            logging_strategy="epoch",
            learning_rate=2e-5,
            weight_decay=0.01,
        )

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=test_dataset,
        )

        trainer.train()
        preds = trainer.predict(test_dataset).predictions
        test_preds = np.argmax(preds, axis=1)

        train_preds = trainer.predict(train_dataset).predictions
        train_preds = np.argmax(train_preds, axis=1)

        train_acc, train_precision, train_recall, train_f1 = _compute_metrics(y_train, train_preds)
        acc, precision, recall, f1 = _compute_metrics(y_test, test_preds)

        plot_confusion_matrix(
            y_test,
            test_preds,
            output_dir / "confusion_matrix_finetuned.png",
            f"Finetuned {model_name} Confusion Matrix",
        )

        return {
            "model": f"Finetuned {model_name}",
            "train_accuracy": train_acc,
            "train_precision": train_precision,
            "train_recall": train_recall,
            "train_f1": train_f1,
            "test_accuracy": acc,
            "test_precision": precision,
            "test_recall": recall,
            "test_f1": f1,
            "cv_mean": None,
            "cv_std": None,
        }
    except Exception as exc:
        print(f"[WARN] Finetune failed: {exc}")
        return {
            "model": f"Finetuned {model_name}",
            "train_accuracy": None,
            "train_precision": None,
            "train_recall": None,
            "train_f1": None,
            "test_accuracy": None,
            "test_precision": None,
            "test_recall": None,
            "test_f1": None,
            "cv_mean": None,
            "cv_std": None,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        default=r"c:\Users\Paramasivam\OneDrive\ドキュメント\code Block\paramasivam\Updated_Healthcare_Dataset_v2.xlsx",
    )
    parser.add_argument("--target", default="sentiment")
    parser.add_argument("--text", default="review_english")
    parser.add_argument("--finetune-model", default="xlm-roberta-base")
    parser.add_argument("--save-cleaned", action="store_true")
    parser.add_argument("--best-only", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = root / data_path
    df = _load_dataset(data_path)

    target_col = args.target
    text_col = args.text

    df, text_col, target_col = _prepare_text_label(df, text_col, target_col)
    df = df.dropna(subset=[target_col, text_col])
    df = _normalize_and_balance(
        df,
        text_col,
        target_col,
        min_text_len=15,
        drop_duplicates=True,
        max_per_class=None,
        upsample=False,
    )
    df = _light_dataset_cleanup(df, text_col, target_col, min_class_count=2)

    if args.save_cleaned:
        cleaned_path = root / "phase2_outputs" / "cleaned_dataset.csv"
        cleaned_path.parent.mkdir(exist_ok=True)
        df.to_csv(cleaned_path, index=False)

    numeric_cols = ["experience_years", "consultation_fee", "average_rating"]
    categorical_cols = [
        "specialization",
        "department",
        "qualification",
        "location",
        "body_part",
    ]

    numeric_cols = [c for c in numeric_cols if c in df.columns]
    categorical_cols = [c for c in categorical_cols if c in df.columns]

    X = df[[text_col] + numeric_cols + categorical_cols]
    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    preprocessor = build_feature_pipeline(
        text_col, numeric_cols, categorical_cols, StandardScaler()
    )
    preprocessor_nb = build_feature_pipeline(
        text_col, numeric_cols, categorical_cols, MinMaxScaler()
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    models = [
        (
            "Logistic Regression",
            LogisticRegression(max_iter=2000, solver="saga", n_jobs=-1, class_weight="balanced"),
        ),
        ("Linear SVM", LinearSVC(class_weight="balanced")),
        (
            "Random Forest",
            RandomForestClassifier(
                n_estimators=400,
                random_state=42,
                class_weight="balanced_subsample",
            ),
        ),
        ("Naive Bayes", MultinomialNB()),
        (
            "MLP (Deep Learning)",
            MLPClassifier(
                hidden_layer_sizes=(256, 128),
                max_iter=500,
                random_state=42,
                early_stopping=False,
            ),
        ),
    ]
    if args.best_only:
        models = [
            (
                "Logistic Regression",
                LogisticRegression(max_iter=2000, solver="saga", n_jobs=-1, class_weight="balanced"),
            ),
            (
                "MLP (Deep Learning)",
                MLPClassifier(
                    hidden_layer_sizes=(256, 128),
                    max_iter=500,
                    random_state=42,
                    early_stopping=False,
                ),
            ),
        ]

    results = []
    output_dir = root / "phase2_outputs"
    output_dir.mkdir(exist_ok=True)

    for name, model in models:
        active_preprocessor = preprocessor
        if name == "Naive Bayes":
            active_preprocessor = preprocessor_nb
        res, y_pred, _ = evaluate_model(
            name, model, X_train, X_test, y_train, y_test, cv, active_preprocessor
        )
        results.append(res)
        plot_confusion_matrix(
            y_test, y_pred, output_dir / f"confusion_matrix_{name.replace(' ', '_')}.png", name
        )

    texts = df[text_col].astype(str).tolist()
    labels = y.tolist()

    results.append(try_sbert(texts, labels, output_dir))
    results.append(try_bert(texts, labels, output_dir))
    results.append(try_roberta(texts, labels, output_dir))
    results.append(try_finetune_transformer(texts, labels, args.finetune_model, output_dir))
    results.append(try_keras_mlp(texts, labels))
    results.append(try_keras_cnn(texts, labels))
    results.append(try_keras_lstm(texts, labels))

    results_df = pd.DataFrame(results)
    results_df.to_csv(output_dir / "model_comparison.csv", index=False)
    plot_bar(results_df.fillna(0), output_dir / "model_comparison.png")
    _print_results_table(results_df)
    _print_test_table(results_df)

    processed_path = output_dir / "processed_dataset.csv"
    df.to_csv(processed_path, index=False)

    summary = {
        "target": target_col,
        "text": text_col,
        "rows": int(len(df)),
        "outputs": [
            "model_comparison.csv",
            "model_comparison.png",
            "processed_dataset.csv",
        ],
    }
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

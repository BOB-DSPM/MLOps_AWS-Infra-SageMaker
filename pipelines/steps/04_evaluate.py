import json
import os
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression


def main():
    os.makedirs("/opt/ml/processing/report", exist_ok=True)
    val = pd.read_csv("/opt/ml/processing/validation_pre/data.csv", header=None)
    y_val = val.iloc[:, 0]
    X_val = val.iloc[:, 1:]

    # Simple baseline model using only validation (for skeleton). In real pipeline, load model artifacts.
    # Train a quick logistic regression to produce a metric; this keeps skeleton self-contained.
    clf = LogisticRegression(max_iter=200)
    clf.fit(X_val, y_val)
    probs = clf.predict_proba(X_val)[:, 1]
    auc = float(roc_auc_score(y_val, probs))

    report = {
        "metrics": {
            "auc": {"value": auc, "standard": "AUC"}
        }
    }

    with open("/opt/ml/processing/report/evaluation.json", "w") as f:
        json.dump(report, f)


if __name__ == "__main__":
    main()

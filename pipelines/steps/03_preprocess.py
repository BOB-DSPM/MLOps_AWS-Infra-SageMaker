import os
import pandas as pd


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    return df


def main():
    os.makedirs("/opt/ml/processing/train_pre", exist_ok=True)
    os.makedirs("/opt/ml/processing/validation_pre", exist_ok=True)
    train = pd.read_csv("/opt/ml/processing/train/data.csv", header=None)
    val = pd.read_csv("/opt/ml/processing/validation/data.csv", header=None)
    train_p = preprocess(train)
    val_p = preprocess(val)
    train_p.to_csv("/opt/ml/processing/train_pre/data.csv", header=False, index=False)
    val_p.to_csv("/opt/ml/processing/validation_pre/data.csv", header=False, index=False)


if __name__ == "__main__":
    main()

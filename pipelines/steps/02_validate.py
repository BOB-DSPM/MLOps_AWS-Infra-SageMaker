import os
import pandas as pd


def main():
    os.makedirs("/opt/ml/processing/report", exist_ok=True)
    train = pd.read_csv("/opt/ml/processing/train/data.csv", header=None)
    val = pd.read_csv("/opt/ml/processing/validation/data.csv", header=None)
    assert train.shape[1] >= 2, "train columns < 2"
    assert val.shape[1] == train.shape[1], "schema mismatch"
    assert not train.isna().any().any(), "train contains NA"
    assert not val.isna().any().any(), "validation contains NA"
    with open("/opt/ml/processing/report/summary.txt", "w") as f:
        f.write(f"train={train.shape}, val={val.shape}\n")


if __name__ == "__main__":
    main()

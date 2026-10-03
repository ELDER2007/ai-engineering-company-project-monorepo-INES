"""
Safe snippet for basic pandas cleaning. Copy and adapt for your dataset.
Run: python pandas_clean.py [path-to-file]   (default: data.csv; needs pandas: pip install pandas)

It prints the shape, the column types and counts, never rows of the data: a file can hold
personal data (names, emails) that must not end up on a screen or in a log.

Exit codes: 0 done; 1 pandas is not installed, or the file is missing, empty or cannot be parsed.
"""
import sys

try:
    import pandas as pd
except ImportError:
    raise SystemExit("Error: pandas is not installed. Install it with: pip install pandas") from None


def load(path: str) -> "pd.DataFrame":
    """Load the file (adjust the reader and its kwargs as needed: read_json, read_excel...)."""
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        raise SystemExit(f"Error: file not found: {path}") from None
    except pd.errors.EmptyDataError:
        raise SystemExit(f"Error: the file is empty: {path}") from None
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise SystemExit(f"Error: the file cannot be parsed as CSV ({type(exc).__name__}): {path}") from None
    except OSError as exc:
        raise SystemExit(f"Error: the file cannot be read ({exc.strerror or type(exc).__name__}): {path}") from None


def clean(df: "pd.DataFrame") -> "pd.DataFrame":
    # Drop fully null columns
    df = df.dropna(axis=1, how="all")
    print("df_shape_after_drop_all_null_cols", df.shape)

    # Fill or drop nulls in key columns (customise columns)
    # df = df.dropna(subset=["required_col"])
    # df["optional_col"] = df["optional_col"].fillna(0)

    # Normalise column names (optional)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    print("df_columns", list(df.columns))

    # Deduplicate (optional)
    before = len(df)
    df = df.drop_duplicates()
    print("rows_dropped_duplicates", before - len(df))
    return df


def main(argv: list[str]) -> None:
    df = load(argv[1] if len(argv) > 1 else "data.csv")
    print("df_shape", df.shape)
    print("df_dtypes", df.dtypes)
    df = clean(df)
    # Summary instead of a sample of rows: counts only.
    print("df_null_counts", df.isna().sum().to_dict())


if __name__ == "__main__":
    main(sys.argv)

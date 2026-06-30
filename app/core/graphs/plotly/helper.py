import pandas as pd
from fuzzywuzzy import fuzz
from decimal import Decimal
import math

datetime_column_list = [
    'fiscal month',
    'fiscal year',
    'fiscal half',
    'fiscal quarter',
    'calendar week',
    'calendar month',
    'return date',
    'date',
    'open date',
    'closed date',
    'week',
    'month',
    'quarter',
    'year',
    'event date',
    'departure date',
    'event month',
    'departure month'
]

color_palette = [
    "#0D5265", "#32DAC8", "#7630EA", "#C140FF", "#FF8300", "#FEC901",
    "#01A982", "#00739D", "#6633BC", "#008567",
    "#00E8CF", "#C54E4B", "#00C8FF", "#FC5A5A",
    "#FFEB59", "#8D741C"
]


def get_most_similar_column_names(user_query: str, df: pd.DataFrame, req_cols=1):
    cols = df.columns
    temp_dict = {
        k: (fuzz.ratio(user_query, k) + fuzz.partial_ratio(user_query, k)) / 2
        for k in cols
    }
    temp_dict_list = sorted(
        temp_dict.items(),
        key=lambda x: x[1],
        reverse=True
    )
    main_cols = [c[0] for c in temp_dict_list[:req_cols]]
    rest_cols = list(set(df.columns).difference(set(main_cols)))
    return main_cols, rest_cols


class DataCorrection:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.datetime_columns = []
        self.categorical_columns = []
        self.numerical_columns = []

    def correct_columns_names(self):
        self.df.columns = [
            str(c).replace("_", " ")
            for c in self.df.columns
        ]
        self.df.columns = [
            " ".join(w.capitalize() for w in word.split())
            if len(word.split()) > 1
            else word
            for word in self.df.columns
        ]
        return self.df

    def extract_datatype_based_columns(self):
        """
        Classify dataframe columns without attempting to parse every string
        column as datetime.

        This avoids warnings such as:
        "Could not infer format, so each element will be parsed individually"
        for category columns like DeviceCategory, Browser, LeadTimeBand, etc.
        """
        # Reset lists so repeated calls do not create duplicate entries.
        self.datetime_columns = []
        self.categorical_columns = []
        self.numerical_columns = []

        datetime_names = {
            name.lower()
            for name in datetime_column_list
        }

        for col in self.df.columns:
            dtype_name = str(self.df[col].dtype).lower()
            col_lower = str(col).lower().strip()

            # Native pandas/numpy datetime dtype, including datetime64[us],
            # datetime64[ms], datetime64[ns], and timezone-aware datetimes.
            is_datetime_dtype = (
                dtype_name.startswith("datetime64")
                or "datetime64" in dtype_name
                or dtype_name.startswith("date")
            )

            # Known date columns can be parsed safely with coercion.
            is_known_datetime_name = (
                col_lower in datetime_names
                or col_lower.endswith(" date")
                or col_lower.endswith(" month")
                or col_lower.endswith(" year")
                or col_lower.endswith(" quarter")
                or col_lower.endswith(" week")
            )

            if is_datetime_dtype:
                self.datetime_columns.append(col)

            elif is_known_datetime_name:
                parsed = pd.to_datetime(
                    self.df[col],
                    errors="coerce"
                )

                # Only accept the conversion as datetime when at least one
                # non-null value was parsed, or the original column was empty.
                if parsed.notna().any() or self.df[col].dropna().empty:
                    self.df[col] = parsed
                    self.datetime_columns.append(col)
                else:
                    self.categorical_columns.append(col)

            elif pd.api.types.is_numeric_dtype(self.df[col]):
                self.numerical_columns.append(col)

            elif (
                pd.api.types.is_object_dtype(self.df[col])
                or pd.api.types.is_string_dtype(self.df[col])
                or isinstance(self.df[col].dtype, pd.CategoricalDtype)
                or dtype_name in {"object", "category", "string", "str"}
            ):
                self.categorical_columns.append(col)

            else:
                # Boolean and other unsupported dtypes are safer as categories
                # for the current graph-selection logic.
                self.categorical_columns.append(col)

            print("#" * 20)
            print(col, str(self.df[col].dtype).lower(), type(self.df[col].dtype))
            print("#" * 20)

        return (
            self.numerical_columns,
            self.categorical_columns,
            self.datetime_columns
        )

    def get_quarter(self, x):
        if pd.isna(x):
            return x
        if x.month == 1:
            return "Q1 " + str(x.year)
        if x.month == 4:
            return "Q2 " + str(x.year)
        if x.month == 7:
            return "Q3 " + str(x.year)
        if x.month == 10:
            return "Q4 " + str(x.year)
        return x

    def get_month(self, x):
        if pd.isna(x):
            return x
        month_map = {
            1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
            5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
            9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
        }
        return f"{month_map[x.month]}-{x.year}"

    def correct_data_with_datetime_columns(self):
        """
        Ensure detected datetime columns use pandas datetime dtype.

        Invalid values are converted to NaT rather than raising an exception.
        """
        for col in self.datetime_columns:
            if col not in self.df.columns:
                continue

            if not pd.api.types.is_datetime64_any_dtype(self.df[col]):
                self.df[col] = pd.to_datetime(
                    self.df[col],
                    errors="coerce"
                )

        return self.df

    def correct_categorical_long_context(self):
        return self.df

    def sorting_dataframe(self):
        if self.datetime_columns:
            date_col = self.datetime_columns[0]
            self.df = self.df.sort_values(
                date_col,
                na_position="last"
            )

        elif self.numerical_columns:
            numeric_df = self.df.loc[:, self.numerical_columns].apply(
                pd.to_numeric,
                errors="coerce"
            )

            self.df["dummy"] = numeric_df.fillna(0).sum(axis=1)
            self.df = self.df.sort_values(
                "dummy",
                ascending=False
            )
            self.df = self.df.drop("dummy", axis=1)

        return self.df

    def handle_large_decimal_values(self, table_json: list) -> list:
        new_table_json = []

        for row in table_json:
            new_row = {}

            for key, value in row.items():
                if isinstance(value, Decimal):
                    value = round(float(value), 1)

                elif isinstance(value, float):
                    if math.isnan(value):
                        value = None
                    else:
                        value = round(value, 1)

                new_row[key] = value

            new_table_json.append(new_row)

        return new_table_json

    def process_dataframe(self) -> pd.DataFrame:
        table_json = self.df.to_dict(orient="records")
        processed_json = self.handle_large_decimal_values(table_json)
        self.df = pd.DataFrame(processed_json)

        # Keep decimal/rate columns as float. Do not force every float column
        # to Int64 because conversion rates and average values need decimals.
        for col in self.df.select_dtypes(include=["number"]).columns:
            self.df[col] = pd.to_numeric(
                self.df[col],
                errors="coerce"
            )

        return self.df


def get_bargap(num_unique: int, orientation="v"):
    if orientation == "v":
        if num_unique < 3:
            return 0.8
        if num_unique < 5:
            return 0.6
        if num_unique < 10:
            return 0.5
        return None

    if num_unique < 3:
        return 0.6
    if num_unique < 5:
        return 0.5
    return None


def get_dticks(df, d_col):
    if d_col not in df.columns:
        return "M6"

    unique_count = df[d_col].nunique(dropna=True)
    d_col_lower = d_col.lower()

    if "month" in d_col_lower:
        if unique_count <= 20:
            return "M2"
        if unique_count <= 40:
            return "M3"
        return "M6"

    if "quarter" in d_col_lower:
        return "M3"

    if "date" in d_col_lower:
        if unique_count <= 20:
            return "M1"
        if unique_count <= 40:
            return "M2"
        return "M3"

    return "M6"

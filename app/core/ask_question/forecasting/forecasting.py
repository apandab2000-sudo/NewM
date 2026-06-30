from scipy.fft import fft
import numpy as np
import pandas as pd
from datetime import timedelta
import re
import difflib
import warnings
from fuzzywuzzy import fuzz
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.logger import get_logger

with warnings.catch_warnings():
    warnings.filterwarnings('ignore', category=FutureWarning)
    warnings.filterwarnings('ignore', category=UserWarning)
    warnings.filterwarnings('ignore', message=".*behavior of DataFrame concatenation.*")

from app.core.graphs.plotly.helper import (
    DataCorrection
    # correct_data_with_datetime_columns,
    # correct_data,
    # extract_datatype_based_columns,
    # sorting_dataframe
)

logger = get_logger(__name__)

# Minimum fuzzy-match score used to decide whether a free-text query is forecast-related.
FORECAST_FUZZY_THRESHOLD = 80

# Default to one future period when the user does not specify a forecast horizon.
DEFAULT_FORECAST_STEPS = 1

# Legacy feature engineering settings retained for helper functions used by older forecast paths.
LAG_WINDOW_FRACTION = 0.5
ROLLING_MEAN_WINDOW = 3

# Day-difference tolerances used to infer the time grain of the source series.
DAILY_INTERVAL_DAYS = 1
WEEKLY_INTERVAL_DAYS = range(6, 9)
MONTHLY_INTERVAL_DAYS = range(28, 32)
QUARTERLY_INTERVAL_DAYS = range(85, 95)
YEARLY_INTERVAL_DAYS = range(350, 370)

# Season lengths for additive seasonal models.
MONTHS_PER_SEASON = 12
QUARTERS_PER_SEASON = 4
WEEKS_PER_SEASON = 52
DAYS_PER_SEASON = 365

# Require at least two complete cycles before enabling seasonal modeling.
MIN_SEASONAL_CYCLES = 2

number_mappings = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six":6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
}


def create_lag_features(data: pd.DataFrame, target_feature: str):
    lag_steps = int(len(data) * LAG_WINDOW_FRACTION)
    for i in range(1, lag_steps + 1):
        data[f'lag_{i}'] = data[target_feature].shift(i)
    return data


def create_rolling_mean(data: pd.DataFrame, target_feature: str):
    data['rolling_mean'] = data[target_feature].rolling(window=ROLLING_MEAN_WINDOW).mean().shift(1)
    return data


def apply_fourier_transform(data, target_feature: str):
    values = data[target_feature].values
    fourier_transform = fft(values)
    data['fourier_transform'] = np.abs(fourier_transform)
    data['fourier_transform'] = data['fourier_transform'].shift(1)
    return data


class FutureValues:
    def __init__(self, table: list[dict], user_query: str):
        self.df = pd.DataFrame(table)
        self.previous_user_query = user_query
        self.base_datetime_for_prediction = ["week", "day", "month", "quarter", "year"]
        self.date_feature = None
        self.num_feature = None
        self.cat_feature = None
        self.timedelta_unit = None
        self.forecasting = None
        self.seasonal_condition = None
        self.seasonal_periods = None
        self.token_usage_dict = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0
        }
        self.data_corrector = DataCorrection(self.df)

    # Function-1: Check whether the question asked by the user is related to forecasting or not
    def check_forecasting_related(self, asked_question: str):
        forecasting_phrases = [
            "forecast", "prediction", "project", "estimate future",
            "trend analysis", "time series", "demand planning",
            "future values", "sales forecast", "weather forecast"
        ]

        for phrase in forecasting_phrases:
            if fuzz.partial_ratio(asked_question.lower(), phrase) >= FORECAST_FUZZY_THRESHOLD:
            # print("The question is related to forecasting.")
                self.forecasting = 'Yes'

        time_unit_pattern = r"\b\d+\s+(day|month|year|quarter)s?\b"
        if re.search(time_unit_pattern, asked_question.lower()):
        # print("The question contains time units likely related to forecasting.")
            self.forecasting = 'Yes'

        relative_time_phrases = [
            "next", "last", "previous", "past", "coming", "upcoming", "following",
            "this quarter", "this month", "this year", "this week"
        ]
        for phrase in relative_time_phrases:
            if re.search(rf"\b{phrase}\b", asked_question.lower()):
            # print("The question contains relative time expressions possibly related to forecasting.")
                self.forecasting = 'Yes'
            
        if not self.forecasting:
            return False
        return True
    
    # Function-2: to get the number of forecasting required
    def num_forecast(self, question: str):
        try:
            num_predictions = int([i for i in question.split(" ") if i.isdigit()][0])
        except (IndexError, ValueError):
            num_predictions = DEFAULT_FORECAST_STEPS
        return num_predictions
    
    # Function-3: to get the time unit mentioned in the question
    def find_time_unit(self, question: str):
        words_in_question = question.lower().split()
            
        matched_units = []
        for word in words_in_question:
            match = difflib.get_close_matches(word, self.base_datetime_for_prediction, n = 1, cutoff = 0.8)
            if match:
                matched_units.append(match[0])
            
        return list(set(matched_units))
    
    # Function-4: preprocessing the data with different helper functions
    def process_df(self):
    # print(self.df.info())
        if sum([True for i in self.df.columns.tolist() if "year" in i.lower() or "date" in i.lower()]) == 0:
            logger.debug("Year/date information not found in forecast dataframe columns")
            try:
                year_information_in_query = int(re.findall(r"\d{4}", self.previous_user_query)[0])
                logger.debug("Extracted year from previous user query for forecasting")
            except Exception as e:
                logger.debug("Could not extract year from previous user query for forecasting: %s", repr(e))
                year_information_in_query = None

            if year_information_in_query:
                self.df["Year"] = year_information_in_query

        logger.debug("Forecast dataframe before preprocessing: shape=%s columns=%s", self.df.shape, list(self.df.columns))

        self.df = self.data_corrector.process_dataframe()
        self.df = self.data_corrector.correct_data_with_datetime_columns()
        self.df = self.data_corrector.sorting_dataframe()
        logger.debug("Forecast dataframe after preprocessing: shape=%s columns=%s", self.df.shape, list(self.df.columns))

    # Function-5: Classifying the columns based on datatypes
    def datatype_based_columns(self):
        num_col, other_col, date_col = self.data_corrector.extract_datatype_based_columns()
        logger.debug(
            "Forecast column classification: date=%s numeric=%s categorical=%s",
            date_col,
            num_col,
            other_col,
        )
        self.date_feature = date_col[0]
        self.num_feature = num_col[0]

        if len(other_col) > 0:
            self.cat_feature = other_col[0]
        return date_col, num_col, other_col
    
    # Function-6: whether the forecasting is possible nor not
    def check_fit_for_prediction(self, asked_question: str):
        datetime_feature_mentioned_in_question = self.find_time_unit(asked_question)
        self.df[self.date_feature] = pd.to_datetime(self.df[self.date_feature])
        try:
            if self.cat_feature:
                temp = self.df.copy()
                temp = temp.sort_values([self.cat_feature, self.date_feature])
                temp["shifted_date"] = temp.groupby(self.cat_feature)[self.date_feature].shift(1)
                temp["date_diff"] = temp["shifted_date"] - temp[self.date_feature]
                date_diff_in_table = abs(temp["date_diff"].median().days)
            else:
                temp = self.df.copy()
                temp["shifted_date"] = temp[self.date_feature].shift(1)
                temp["date_diff"] = temp["shifted_date"] - temp[self.date_feature]
                date_diff_in_table = abs(temp["date_diff"].median().days)
        except Exception as e:
            logger.debug("Forecast date interval detection failed: %s", repr(e))
            return False

        logger.debug("Forecast detected date interval in days: %s", date_diff_in_table)

        if len(datetime_feature_mentioned_in_question) != 0:
            feature_mentioned = datetime_feature_mentioned_in_question[0]
            logger.debug("Forecast time unit mentioned in query: %s", feature_mentioned)

        if date_diff_in_table in MONTHLY_INTERVAL_DAYS and feature_mentioned == "month":
            self.timedelta_unit = pd.DateOffset(months=1)
            self.seasonal_condition = 'add'
            self.seasonal_periods = MONTHS_PER_SEASON
        elif date_diff_in_table in QUARTERLY_INTERVAL_DAYS and feature_mentioned == "quarter":
            self.timedelta_unit = pd.DateOffset(months=3)
            self.seasonal_condition = 'add'
            self.seasonal_periods = QUARTERS_PER_SEASON
        elif date_diff_in_table in YEARLY_INTERVAL_DAYS and feature_mentioned == "year":
            self.timedelta_unit = pd.DateOffset(years=1)
            self.seasonal_condition = None
            self.seasonal_periods = None
        elif date_diff_in_table in WEEKLY_INTERVAL_DAYS and feature_mentioned == "week":
            self.timedelta_unit = timedelta(weeks=1)
            self.seasonal_condition = 'add'
            self.seasonal_periods = WEEKS_PER_SEASON
        elif date_diff_in_table == DAILY_INTERVAL_DAYS and feature_mentioned == "day":
            self.timedelta_unit = timedelta(days=1)
            self.seasonal_condition = 'add'
            self.seasonal_periods = DAYS_PER_SEASON
        else:
            if date_diff_in_table in MONTHLY_INTERVAL_DAYS:
                self.timedelta_unit = pd.DateOffset(months=1)
                self.seasonal_condition = 'add'
                self.seasonal_periods = MONTHS_PER_SEASON
            elif date_diff_in_table in QUARTERLY_INTERVAL_DAYS:
                self.timedelta_unit = pd.DateOffset(months=3)
                self.seasonal_condition = 'add'
                self.seasonal_periods = QUARTERS_PER_SEASON
            elif date_diff_in_table in YEARLY_INTERVAL_DAYS:
                self.timedelta_unit = pd.DateOffset(years=1)
                self.seasonal_condition = None
                self.seasonal_periods = None
            elif date_diff_in_table in WEEKLY_INTERVAL_DAYS:
                self.timedelta_unit = timedelta(weeks=1)
                self.seasonal_condition = 'add'
                self.seasonal_periods = WEEKS_PER_SEASON
            else:
                self.timedelta_unit = timedelta(days=1)
                self.seasonal_condition = 'add'
                self.seasonal_periods = DAYS_PER_SEASON

        if self.seasonal_periods and self.df.shape[0] < MIN_SEASONAL_CYCLES * self.seasonal_periods:
            logger.debug("Not enough forecast data for seasonal modeling. Disabling seasonality.")
            self.seasonal_condition = None
            self.seasonal_periods = None

        if not self.timedelta_unit:
            return False  # forecasting is impossible due to invalid information given by user
        return True
    
    # Function-7: to create the future dates
    def create_future_values(self, data: pd.DataFrame, num_future_values: int):
        last_date = data[self.date_feature].max()
        future_dates = [last_date + self.timedelta_unit*i for i in range(1, num_future_values + 1)]
        return future_dates

    # FUnction-8: to create the predictions:
    def make_predictions(self, num_predictions: int):
        if self.cat_feature:
            unique_values = self.df[self.cat_feature].unique()
            # updated_df = pd.DataFrame(columns = self.df.columns)
            updated_df = pd.DataFrame(columns=self.df.columns.tolist() + ['is_forecasted'])

            for v in unique_values:
                # temp = self.df[self.df[self.cat_feature] == v]
                temp = self.df[self.df[self.cat_feature] == v].copy()
                temp['is_forecasted'] = False  # Mark original values
                if temp.shape[0] == 1:
                    # forecasted_values = [temp[self.num_feature].iloc[0]] * num_predictions
                    rep_value = temp[self.num_feature].iloc[0]
                    forecasted_values = pd.Series([rep_value] * num_predictions, dtype=temp[self.num_feature].dtype).reset_index(drop=True)
                else:
                    if self.seasonal_periods and temp.shape[0] < MIN_SEASONAL_CYCLES * self.seasonal_periods:
                        self.seasonal_condition = None
                        self.seasonal_periods = None
                    model = ExponentialSmoothing(temp[self.num_feature],
                                                seasonal_periods=self.seasonal_periods,
                                                trend='add', seasonal=self.seasonal_condition).fit()
                    forecasted_values = model.forecast(steps=num_predictions)
                    forecasted_values = forecasted_values.reset_index(drop=True)
                # forecasted_values = model.forecast(steps = num_predictions)
                # forecasted_values = forecasted_values.reset_index(drop = True)
                future_dates = self.create_future_values(temp, num_predictions)
                # temp_future_df = pd.DataFrame(columns = self.df.columns)
                temp_future_df = pd.DataFrame(columns=self.df.columns.tolist() + ['is_forecasted'])
                temp_future_df[self.date_feature] = future_dates
                temp_future_df[self.cat_feature] = v
                temp_future_df[self.num_feature] = forecasted_values
                temp_future_df['is_forecasted'] = True  # Mark predicted values
                temp = pd.concat([temp, temp_future_df], ignore_index = True)

                updated_df = pd.concat([updated_df, temp], axis = 0)

        else:
            if self.df.shape[0] == 1:
                # forecasted_values = [self.df[self.num_feature].iloc[0]] * num_predictions
                rep_value = self.df[self.num_feature].iloc[0]
                forecasted_values = pd.Series([rep_value] * num_predictions, dtype=self.df[self.num_feature].dtype).reset_index(drop=True)
            else:
                if self.seasonal_periods and self.df.shape[0] < MIN_SEASONAL_CYCLES * self.seasonal_periods:
                    self.seasonal_condition = None
                    self.seasonal_periods = None
                model = ExponentialSmoothing(self.df[self.num_feature], 
                                            seasonal_periods = self.seasonal_periods, 
                                            trend = 'add', seasonal = self.seasonal_condition).fit()
                forecasted_values = model.forecast(steps = num_predictions)
                forecasted_values = forecasted_values.reset_index(drop = True)
            future_dates = self.create_future_values(self.df, num_predictions)
            original_df = self.df.copy()
            original_df['is_forecasted'] = False  # Mark original values
            # temp = pd.DataFrame(columns = self.df.columns)
            temp = pd.DataFrame(columns=self.df.columns.tolist() + ['is_forecasted'])
            temp[self.date_feature] = future_dates
            temp[self.num_feature] = forecasted_values
            temp['is_forecasted'] = True  # Mark predicted values

            updated_df = pd.concat([original_df, temp], axis = 0)

        return updated_df
    
# @staticmethod
#---------------------------------------------------------------------------------------------------------------
# Main function to work on the data and give the prediction:
def predict_future_values(table: list[dict], user_query: str, asked_question: str):
    fv = FutureValues(table = table, user_query = user_query)
    fv.process_df()
    date_col, num_col, cat_col = fv.datatype_based_columns()

    if len(cat_col) > 1 or len(date_col) != 1 or len(num_col) != 1:
        return pd.DataFrame()

    prediction_fit_check = fv.check_fit_for_prediction(asked_question)
    logger.debug("Forecast prediction fit check: %s", prediction_fit_check)
    if not prediction_fit_check:
        return pd.DataFrame()

    logger.debug("Forecast timedelta unit: %s", fv.timedelta_unit)

    if not fv.timedelta_unit:
        return pd.DataFrame()

    num_predictions = fv.num_forecast(asked_question)

    future_value_df = fv.make_predictions(num_predictions)
    return future_value_df




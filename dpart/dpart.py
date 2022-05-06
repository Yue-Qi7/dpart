import numpy as np
import pandas as pd
from typing import Union, Dict
from logging import getLogger
from sklearn.preprocessing import OrdinalEncoder, MinMaxScaler
from diffprivlib.utils import PrivacyLeakWarning

from dpart.utils.kahn import kahn_sort
from dpart.methods import ProbabilityTensor


logger = getLogger("dpart")


class dpart:
    DEFAULT_METHOD = ProbabilityTensor

    def __init__(
        self,
        visit_order: list = None,
        methods: dict = None,
        bounds: dict = None,
        epsilon: Union[Dict, float] = 1.0,
        prediction_matrix: dict = None,
    ):

        # Privact budget
        self._epsilon = epsilon
        self.matrix_budget = 0
        if prediction_matrix == "infer":
            if epsilon is not None:
                self.matrix_budget = self._epsilon / 2
            else:
                self.matrix_budget = None

        # visit order
        self.prediction_matrix = prediction_matrix
        self.visit_order = visit_order

        if prediction_matrix is not None:
            if visit_order is not None:
                logger.warning("visit_order will be ignored as a dependency matrix has been provided")

        # method dict
        if methods is None:
            methods = {}
        self.methods = methods
        self.encoders = None

        # bound dict
        if bounds is None:
            bounds = {}
        self.bounds = bounds
        self.dtypes = None
        self.root = None
        self.columns = None

    def root_column(self, df: pd.DataFrame) -> str:
        root_col = "__ROOT__"
        idx = 0
        while root_col in df.columns:
            root_col = f"__ROOT_{idx}__"
            idx += 1
        return root_col

    def normalise(self, df: pd.DataFrame) -> pd.DataFrame:
        self.encoders = {}
        df = df.copy()
        for col, series in df.items():
            if series.dtype.kind in "OSb":
                t_dtype = "category"
                if col not in self.bounds:
                    PrivacyLeakWarning(f"List of categories not sepecified for column '{col}'")
                    self.bounds[col] = list(series.value_counts().index)
                self.encoders[col] = OrdinalEncoder(categories=self.bounds[col])
            else:
                t_dtype = "float"
                if col not in self.bounds:
                    PrivacyLeakWarning(f"upper and lower bounds not specified for column '{col}'")
                    self.bounds[col] = (series.min(), series.max())
                self.encoders[col] = MinMaxScaler(feature_range=self.bounds[col])

            df[col] = pd.Series(self.encoders[col].fit_transform(df[[col]]).squeeze(), name=col, index=df.index, dtype=t_dtype)

        return df

    def fit(self, df: pd.DataFrame):
        # Capture dtypes
        self.dtypes = df.dtypes
        self.columns = df.columns
        # extract visit order
        if self.visit_order is None:
            logger.info("extract visit order")
            self.visit_order = list(df.columns)
            logger.debug(f"extracted visit order: {self.visit_order}")

        # extract_bounds
        for column in self.visit_order:
            if df[column].dtype.kind in "Mmfui":
                if column not in self.bounds:
                    logger.warning(f"Bounds not provided for column {column}")
                    self.bounds[column] = (df[column].min(), df[column].max())
                    logger.debug(
                        f"Extracted bounds for {column}: {self.bounds[column]}"
                    )

        # reorder and introduce initial columns
        self.root = self.root_column(df)
        t_df = self.normalise(df).reindex(columns=self.visit_order)
        t_df.insert(0, column=self.root, value=0)

        # build methods
        for idx, target in enumerate(self.visit_order):
            if self.prediction_matrix is not None:
                X_columns = self.prediction_matrix.get(target, [])
            else:
                X_columns = t_df.columns[: idx + 1]
            X = t_df[X_columns]
            y = t_df[target]

            if target not in self.methods:
                logger.warning(
                    f"target {target} has no specified method will use default {self.DEFAULT_METHOD.__name__}"
                )
                self.methods[target] = self.DEFAULT_METHOD()

            if self._epsilon is not None:
                self.methods[target].set_epsilon(self._epsilon / len(self.visit_order))

            print(
                f"Fit target: {target} | sampler used: {self.methods[target].__class__.__name__}"
            )

            t_X, t_y = self.methods[target].preprocess(X=X, y=y)
            self.methods[target].fit(X=t_X, y=t_y)

    def denormalise(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in df.columns:
            df[col] = self.encoders[col].inverse_transform(df[[col]]).squeeze()

            if self.dtypes[col].kind in "ui":
                df[col] = df[col].round().astype(int).astype(self.dtypes[col])
            else:
                df[col] = df[col].astype(self.dtypes[col])
        return df

    def sample(self, n_records: int) -> pd.DataFrame:
        df = pd.DataFrame({self.root: 0}, index=np.arange(n_records))
        for target in self.visit_order:
            if self.prediction_matrix is not None:
                X_columns = self.prediction_matrix.get(target, [])
            else:
                X_columns = list(df.columns)
            logger.info(f"Sample target {target}")
            logger.debug(f"Sample target {target} - preprocess feature matrix")
            t_X = self.methods[target].preprocess_X(df[X_columns])
            logger.debug(f"Sample target {target} - Sample values")
            t_y = self.methods[target].sample(X=t_X)
            logger.debug(f"Sample target {target} - post process sampled values")
            y = self.methods[target].postprocess_y(y=t_y)
            logger.debug(f"Sample target {target} - Update feature matrix")
            df.insert(loc=df.shape[1], column=target, value=y)

        logger.info("denormalise sampled data")
        i_df = self.denormalise(df=df.drop(self.root, axis=1)).reindex(
            columns=self.columns
        )
        return i_df

    @property
    def epsilon(self):
        budgets = [method.epsilon for _, method in self.methods.items()]

        if pd.isnull(budgets).any():
            return None
        else:
            return sum(budgets)

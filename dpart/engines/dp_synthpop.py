"""
This file is under the following license and copyright.
MIT License
Copyright (c) 2022 dpart

The following modifications were made to the file:
    - The differential private synthpop class was modified to include more arguments.
    - The type hints were updated.
"""

from typing import Dict, Union, List
from dpart.dpart import dpart
from dpart.methods import LogisticRegression, LinearRegression


class DPSynthpop(dpart):
    default_numerical = LinearRegression
    default_categorical = LogisticRegression

    def __init__(
        self,
        methods: dict = None,
        epsilon: Union[float, Dict[str, Union[float, Dict[str, float]]]] = None,
        bounds: Dict[str, List] = None,
        visit_order: List[str] = None,
        prediction_matrix: Union[str, Dict[str, List[str]]] = None,
        n_parents: int = None,
    ):
        super().__init__(
            methods=methods,
            epsilon=epsilon,
            bounds=bounds,
            visit_order=visit_order,
            prediction_matrix=prediction_matrix,
            n_parents=n_parents,
        )

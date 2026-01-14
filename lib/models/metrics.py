"""
This module contains the models for the metrics.

Metrics are KPIs that are tracked for a given date.

This is an abstract model that can be used to track any metric, whether that's patient lab results, patient health tracking KPIs, clinic management KPIs, etc.
"""

from typing import Any, Dict, List, Optional, Tuple


class Metric:
    def __init__(
        self,
        metric_name: str,
        metric_value: str,
        metric_unit: str,
        range: Optional[Tuple[float, float]] = None,
    ):
        self.metric_name = metric_name
        self.metric_value = metric_value
        self.metric_unit = metric_unit
        self.range = range

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "metric_unit": self.metric_unit,
            "range": self.range,
        }

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the metrics table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE metrics SCHEMAFULL;
            DEFINE FIELD metric_name ON metrics TYPE string;
            DEFINE FIELD metric_value ON Metrics TYPE string;
            DEFINE FIELD metric_unit ON metrics TYPE string;
            DEFINE FIELD range ON metrics TYPE option<array<float, 2>>;
            DEFINE FIELD created_at ON metrics TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON metrics TYPE datetime VALUE time::now();
        """


class MetricSet:
    def __init__(self, user_id: str, date: str, metrics: List[Metric]):
        self.user_id = user_id
        self.date = date
        self.metrics = metrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "date": self.date,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the Encounter table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """

            DEFINE FIELD created_at ON encounter TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON encounter TYPE datetime VALUE time::now();
        """

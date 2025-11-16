from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    Collection,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
)

from amt_nano.db.surreal import DbController
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
)
from pydantic.json_schema import SkipJsonSchema
from surrealdb.data.types.record_id import RecordID
from surrealdb.data.types.table import Table

from lib.logger import Logger
from settings import DEBUG, logger

ExcludedField = SkipJsonSchema[
    Annotated[Any, Field(default=None, exclude=True), AfterValidator(lambda s: None)]
]


class Model(BaseModel, ABC):
    """Base Model class. All child classes should have all optional fields for
    compatibility with the Service classes.

    Args:
        BaseModel (_type_): _description_
        ABC (_type_): _description_
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: Optional[str] = Field(default=None)
    logger: Logger = Field(repr=False, exclude=True, default=logger, init=False)
    debug: bool = Field(repr=False, exclude=True, default=DEBUG, init=False)

    @classmethod
    @abstractmethod
    def table_name(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def table_schema(cls) -> str:
        pass


T = TypeVar("T", bound=Model)
TOrCollectionT = TypeVar("TOrCollectionT", bound=Model | Collection[Model])


@dataclass
class Result:
    success: bool
    message: str


@dataclass
class OperationResult(Result, Generic[TOrCollectionT]):
    success: bool
    message: str
    obj: Optional[TOrCollectionT]

    @staticmethod
    def from_result(result: Result, obj: Optional[TOrCollectionT]):
        return OperationResult(result.success, result.message, obj)


class Service(ABC, Generic[T]):
    db: DbController
    model: Type[T]
    logger: Logger
    debug: bool

    def connect(self) -> None:
        """
        Connect to the database
        """
        try:
            self.db.connect()
        except Exception as e:
            self.logger.error(f"Error connecting to database: {e}")
            raise e

    def close(self) -> None:
        """
        Close the database connection
        """
        try:
            self.db.close()
        except Exception as e:
            self.logger.error(f"Error closing connection to database: {e}")
            raise e

    @abstractmethod
    def create(self, obj: T) -> OperationResult[T]:
        pass

    @abstractmethod
    def update(self, id: str, obj: T) -> OperationResult[T]:
        pass

    @abstractmethod
    def delete(self, id: str) -> OperationResult[T]:
        pass

    @abstractmethod
    def get_by_id(self, id: str) -> OperationResult[T]:
        pass

    @abstractmethod
    def get_all(self) -> OperationResult[List[T]]:
        pass


class SurrealTableService(Service[T]):
    def create(self, obj: T) -> OperationResult[T]:
        try:
            self.connect()
            result = self.db.create(self.model.table_name(), obj.model_dump())

            if isinstance(result, dict) and result["id"]:
                new_obj = self.model.model_validate(result)
                new_obj.id = str(result["id"])
                self.logger.info(f"Created {self.model.table_name()} '{result}")
                return OperationResult(
                    True, f"{self.model.table_name()} created successfully", new_obj
                )
            elif "already exists" in result:
                self.logger.warning(f"Entry {self.model.table_name} already exists")
                return OperationResult(
                    False, f"{self.model.table_name()} already exists", None
                )
            else:
                return OperationResult(
                    False, f"Failed to create {self.model.table_name()}", None
                )
        except Exception as e:
            self.logger.error(f"Error creating {self.model.table_name()}: {e}")
            return OperationResult(
                False, f"Error creating {self.model.table_name()}: {str(e)}", None
            )
        finally:
            self.close()

    def update(self, id: str, obj: T) -> OperationResult[T]:
        try:
            to_update = obj.model_dump(exclude_unset=True)
            to_update.pop("id", None)

            self.connect()
            result = self.db.update(RecordID(self.model.table_name(), id), to_update)

            if isinstance(result, dict) and result["id"]:
                new_obj = self.model.model_validate(result)
                new_obj.id = str(result["id"])
                self.logger.info(f"Updated {id} to {to_update}")
                return OperationResult(
                    True,
                    f"Successfully updated entry in {self.model.table_name()}",
                    new_obj,
                )
            else:
                return OperationResult(
                    False, f"Failed to create entry in {self.model.table_name()}", None
                )

        except Exception as e:
            self.logger.error(f"Error updating {id}: {e}")
            return OperationResult(False, f"Failed to update {id}", None)

    def delete(self, id: str) -> OperationResult[T]:
        try:
            self.connect()
            result = self.db.delete(RecordID(self.model.table_name(), id))

            if isinstance(result, dict) and result["id"]:
                deleted_obj = self.model.model_validate(result)
                deleted_obj.id = str(result["id"])
                self.logger.info(f"Deleted {result}.")
                return OperationResult(
                    True,
                    f"Successfully deleted entry in {self.model.table_name()}",
                    deleted_obj,
                )
            else:
                return OperationResult(
                    False, f"Failed to deleted entry in {self.model.table_name()}", None
                )

        except Exception as e:
            self.logger.error(f"Error updating {id}: {e}")
            return OperationResult(False, f"Failed to update {id}", None)

    def get_by_id(self, id: str) -> OperationResult[T]:
        try:
            self.connect()
            result = self.db.select(RecordID(self.model.table_name(), id))

            if isinstance(result, dict):
                obj = self.model.model_validate(result)
                obj.id = str(result["id"])
                return OperationResult(
                    True, f"got entry in {self.model.table_name()} successfully", obj
                )
            else:
                self.logger.error(
                    f"Failed to query for {id} in table {self.model.table_name()}."
                )
                return OperationResult(
                    False, f"entry in {self.model.table_name()} not found.", None
                )
        except Exception as e:
            self.logger.error(f"Error getting entry in {self.model.table_name()}: {e}")
            return OperationResult(
                False,
                f"Error getting entry in {self.model.table_name()}: {str(e)}",
                None,
            )
        finally:
            self.close()

    def get_all(self) -> OperationResult[List[T]]:
        try:
            self.connect()
            result = self.db.select_many(Table(self.model.table_name()))

            if isinstance(result, list):
                parsed_objs: List[T] = []
                for obj_dict in result:
                    new_obj = self.model.model_validate(obj_dict)
                    new_obj.id = str(obj_dict["id"])
                    parsed_objs.append(new_obj)
                return OperationResult(
                    True,
                    f"got all entries in {self.model.table_name()} successfully",
                    parsed_objs,
                )
            else:
                self.logger.error(
                    f"Failed to query for all entries in {self.model.table_name()}."
                )
                return OperationResult(
                    False,
                    f"Failed to query for all entries in {self.model.table_name()}.",
                    None,
                )
        except Exception as e:
            self.logger.error(
                f"Error getting all entries in {self.model.table_name()}: {e}"
            )
            return OperationResult(
                False,
                f"Error getting all entries in {self.model.table_name()}: {str(e)}",
                None,
            )
        finally:
            self.close()

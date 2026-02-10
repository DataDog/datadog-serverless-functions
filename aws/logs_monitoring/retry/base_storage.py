from abc import ABC, abstractmethod


class BaseStorage(ABC):
    @abstractmethod
    def get_data(self, prefix) -> dict:
        """Retrieve stored data for a given prefix. Returns {key: data}."""
        ...

    @abstractmethod
    def store_data(self, prefix, data) -> None:
        """Store data under the given prefix."""
        ...

    @abstractmethod
    def delete_data(self, key) -> None:
        """Delete stored data by key."""
        ...

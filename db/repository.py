# stub for data persistence (SQLite/ORM)
class GreenhouseRepository:
    def __init__(self, db_path: str):
        # TODO: connect to SQLite or another DB
        pass

    def save(self, name: str, perimeter: list, materials: dict):
        # TODO: implement persistence
        pass

    def load(self, name: str) -> dict:
        # TODO: implement retrieval
        return {}

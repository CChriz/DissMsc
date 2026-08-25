"""User model."""


class User:
    def __init__(self, entity_id, name, email):
        self.id = entity_id
        self.name = name
        self.email = email

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email}

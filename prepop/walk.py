"""A tool for applying a piece of logic to an arbitrary python data structure
of nested lists and dictionaries. Example usage:

    accounting = Department(address="45 Elm St. West", ...)
    data = {"staff": [{"id": 12, "name": "John", "department": accounting}]}

    @walks_on_trees
    def resolve_department_addresses(value):
        if isinstance(value, Department):
            return TraversalTerminator(value.address)

    resolve_department_addresses(data)
    #=> {"staff": [{"id": 12, "name": "John", "department": "45 Elm St. West"}]}
"""


class TraversalTerminator:
    def __init__(self, value):
        self.value = value


def walks_on_trees(fn):
    def wrapper(value):
        out = fn(value)
        if isinstance(out, TraversalTerminator):
            return out.value
        if isinstance(value, list):
            return [wrapper(v) for v in value]
        if isinstance(value, dict):
            return {k: wrapper(v) for k, v in value.items()}

        return value

    return wrapper

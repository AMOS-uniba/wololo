from scalyca import colour as c


def format_boolean(condition, yes: str = 'yes', no: str = ' no') -> str:
    return c.ok(yes) if condition else c.err(no)


from flask import abort, request


def json_body(*names):
    """Return the listed fields from the request's JSON body, in order.

    Aborts with a 400 if the body is missing, isn't an object, or leaves any of
    the fields out.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, description="expected a JSON object body")
    missing = [name for name in names if name not in body]
    if missing:
        abort(400, description=f"missing fields: {', '.join(missing)}")
    return [body[name] for name in names]

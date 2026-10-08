def run_with_resource(resource, action):
    try:
        result = action(resource)
    except BaseException:
        try:
            resource.close()
        except BaseException:
            pass
        raise
    resource.close()
    return result

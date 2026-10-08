def run_with_resource(resource, action):
    try:
        return action(resource)
    finally:
        resource.close()

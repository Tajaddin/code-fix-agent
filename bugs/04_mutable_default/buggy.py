def append_id(item, log=[]):
    """Append item to the log list and return the log.

    Each fresh call should start from an empty log unless one is passed in.
    """
    log.append(item)
    return log

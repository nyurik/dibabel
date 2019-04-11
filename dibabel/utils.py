from collections import defaultdict


def list_to_dict_of_lists(items, key, value=None):
    result = defaultdict(list)
    for item in items:
        k = key(item)
        if k:
            if value: item = value(item)
            result[k].append(item)
    return result

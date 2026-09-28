def reduce_lens(outs):
    return [len(o) if hasattr(o, "__len__") else 1 for o in outs]


def combine_lens(a, b):
    if not a or not b:
        return a or b
    return [x + y for x, y in zip(a, b)]


def empty_lens():
    return []

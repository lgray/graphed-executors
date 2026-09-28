import numpy as np


def reduce_sum(outs):
    return [float(np.sum(np.asarray(o))) for o in outs]


def combine(a, b):
    return [x + y for x, y in zip(a, b)]


def empty():
    return []
